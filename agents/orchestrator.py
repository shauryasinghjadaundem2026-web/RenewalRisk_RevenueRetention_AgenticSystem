"""
Decision Router / Orchestrator (+ Action & Audit Agent)
========================================================
The conductor of the multi-agent system. For every live, at-risk account it:

  1. Reads the risk score + drivers from the Risk Scoring Agent.
  2. Asks the Reasoning/Options Agent for the ranked retention-option menu.
  3. Asks the Policy Agent (RAG) which playbook clause governs this account.
  4. Applies the routing rule:
       - Escalate to a human  (HITL)   -- high risk + high value, Enterprise
         tier, or the best option needs approval (big discount / high cost).
       - Act autonomously               -- everything else, bounded by the
         playbook's autonomous-authority limits.
  5. Writes a full, replayable audit record for every decision, whether
     autonomous or escalated.

This module has no UI of its own -- it emits `dashboard_data.json`, which
the leadership dashboard renders.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline import build_account_table
from risk_model import train_and_score, NUMERIC_FEATURES, BOOL_FEATURES, CATEGORICAL_FEATURES
from roi_engine import generate_options, compute_benchmarks
from policy_rag import PolicyRetriever

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
HIGH_VALUE_ARR = 15000          # Playbook Clause 4
ESCALATE_RISK_SCORE = 70        # Playbook Clause 1
AUTONOMOUS_MAX_COST = 1000      # Playbook Clause 1/2
ENTERPRISE_ALWAYS_ESCALATES = True  # Playbook Clause 1


def route_account(risk_score, arr_amount, plan_tier, best_option):
    """Returns (route, reason) where route in {'human_escalation','autonomous'}."""
    reasons = []
    escalate = False
    if risk_score >= ESCALATE_RISK_SCORE and arr_amount >= HIGH_VALUE_ARR:
        escalate = True
        reasons.append(f"risk score {risk_score:.0f} >= {ESCALATE_RISK_SCORE} and ARR ${arr_amount:,.0f} >= ${HIGH_VALUE_ARR:,.0f}")
    if ENTERPRISE_ALWAYS_ESCALATES and plan_tier == "Enterprise" and risk_score >= 40:
        escalate = True
        reasons.append("Enterprise plan tier with Medium+ risk score")
    if best_option.get("requires_approval"):
        escalate = True
        reasons.append(f"recommended option '{best_option['label']}' requires approval")
    if best_option["cost"] > AUTONOMOUS_MAX_COST:
        escalate = True
        reasons.append(f"option cost ${best_option['cost']:,.0f} exceeds autonomous limit ${AUTONOMOUS_MAX_COST:,.0f}")
    if escalate:
        return "human_escalation", "; ".join(reasons)
    return "autonomous", "within autonomous authority (Playbook Clause 2)"


def value_tier(arr_amount):
    return "High value" if arr_amount >= HIGH_VALUE_ARR else "Standard value"


def risk_tier(score):
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def run():
    live, metrics, full_df = train_and_score()
    benchmarks = compute_benchmarks(full_df)
    retriever = PolicyRetriever()

    feat_cols = NUMERIC_FEATURES + BOOL_FEATURES + CATEGORICAL_FEATURES
    from risk_model import _pipeline  # reuse trained shape
    # retrain pipeline exactly as risk_model does, to get the same fitted object
    # (kept simple/explicit rather than re-exporting internal state)
    from sklearn.model_selection import train_test_split
    model_df = full_df.copy()
    for c in BOOL_FEATURES:
        model_df[c] = model_df[c].astype(bool).astype(int)
    X = model_df[feat_cols]
    y = model_df["churn_flag"].astype(int)
    pipe = _pipeline()
    pipe.fit(X, y)

    decisions = []
    autonomous_log = []
    escalation_queue = []

    for _, row in live.iterrows():
        arr = float(row["arr_amount"])
        score = float(row["risk_score"])
        options, p0 = generate_options(row, pipe, feat_cols, benchmarks)
        best = options[0]
        route, reason = route_account(score, arr, row["plan_tier"], best)

        query = (
            f"{'enterprise ' if row['plan_tier']=='Enterprise' else ''}"
            f"{'high risk ' if score>=70 else 'low medium risk '}"
            f"{'high value account' if arr>=HIGH_VALUE_ARR else 'standard value account'} "
            f"{best['label']} option cost {best['cost']}"
        )
        clause = retriever.retrieve(query, k=1)[0]

        decision = {
            "account_id": row["account_id"],
            "account_name": row["account_name"],
            "industry": row["industry"],
            "country": row["country"],
            "plan_tier": row["plan_tier"],
            "arr_amount": round(arr, 2),
            "mrr_amount": round(float(row["mrr_amount"]), 2),
            "risk_score": round(score, 1),
            "risk_tier": risk_tier(score),
            "value_tier": value_tier(arr),
            "risk_drivers": row["risk_drivers"],
            "days_since_last_ticket": None if pd.isna(row["days_since_last_ticket"]) else int(row["days_since_last_ticket"]),
            "days_since_last_usage": None if pd.isna(row["days_since_last_usage"]) else int(row["days_since_last_usage"]),
            "usage_trend_pct": round(float(row["usage_trend_pct"]), 3),
            "avg_satisfaction": None if pd.isna(row["avg_satisfaction"]) else round(float(row["avg_satisfaction"]), 2),
            "options": [
                {**o, "cost": round(o["cost"], 2), "revenue_saved": round(o["revenue_saved"], 2),
                 "net_benefit": round(o["net_benefit"], 2),
                 "roi": None if o["roi"] is None else round(o["roi"], 2),
                 "uplift_prob": round(o["uplift_prob"], 4)}
                for o in options
            ],
            "recommended_option": best["option"],
            "route": route,
            "route_reason": reason,
            "policy_clause": clause["title"],
            "policy_clause_text": clause["text"],
            "decision_ts": datetime.now(timezone.utc).isoformat(),
        }
        decisions.append(decision)
        if route == "human_escalation":
            escalation_queue.append(decision)
        else:
            autonomous_log.append(decision)

    # --- macro / portfolio aggregates for the dashboard ------------------------
    live_scored = live.copy()
    live_scored["risk_tier"] = live_scored["risk_score"].apply(risk_tier)

    macro = {
        "total_active_accounts": int(len(live)),
        "total_arr_active": float(live["arr_amount"].sum()),
        "arr_at_risk_high": float(live[live["risk_score"] >= 70]["arr_amount"].sum()),
        "arr_at_risk_medium": float(live[(live["risk_score"] >= 40) & (live["risk_score"] < 70)]["arr_amount"].sum()),
        "n_high_risk": int((live["risk_score"] >= 70).sum()),
        "n_medium_risk": int(((live["risk_score"] >= 40) & (live["risk_score"] < 70)).sum()),
        "n_low_risk": int((live["risk_score"] < 40).sum()),
        "n_escalations": len(escalation_queue),
        "n_autonomous": len(autonomous_log),
        "total_autonomous_cost": float(sum(d["options"][[o["option"] for o in d["options"]].index(d["recommended_option"])]["cost"] for d in autonomous_log)),
        "total_autonomous_revenue_saved": float(sum(d["options"][[o["option"] for o in d["options"]].index(d["recommended_option"])]["revenue_saved"] for d in autonomous_log)),
        "total_escalation_arr": float(sum(d["arr_amount"] for d in escalation_queue)),
        "historical_base_churn_rate": metrics["base_churn_rate"],
        "model_auc_holdout": metrics["auc_logreg_holdout"],
        "as_of": metrics["as_of"],
    }
    macro["total_autonomous_net_benefit"] = macro["total_autonomous_revenue_saved"] - macro["total_autonomous_cost"]

    churn_by_industry = (
        full_df.groupby("industry")["churn_flag"].mean().sort_values(ascending=False).round(3).to_dict()
    )
    churn_by_plan = full_df.groupby("plan_tier")["churn_flag"].mean().round(3).to_dict()
    churn_by_country = full_df.groupby("country")["churn_flag"].mean().round(3).to_dict()

    churn_events = pd.read_excel(Path(__file__).resolve().parent.parent / "data" / "ravenstack_churn_events.xlsx")
    reason_counts = churn_events["reason_code"].value_counts().to_dict()

    churn_events["month"] = churn_events["churn_date"].dt.to_period("M").astype(str)
    monthly_churn = churn_events.groupby("month").size().sort_index()
    monthly_churn_trend = [{"month": m, "churn_events": int(v)} for m, v in monthly_churn.items()]

    risk_distribution = [
        {"bucket": b, "count": int(c)}
        for b, c in pd.cut(live["risk_score"], bins=[0, 20, 40, 60, 80, 100],
                            labels=["0-20", "20-40", "40-60", "60-80", "80-100"]).value_counts().sort_index().items()
    ]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "macro": macro,
        "churn_by_industry": churn_by_industry,
        "churn_by_plan": churn_by_plan,
        "churn_by_country": churn_by_country,
        "churn_reason_counts": reason_counts,
        "monthly_churn_trend": monthly_churn_trend,
        "risk_distribution": risk_distribution,
        "escalation_queue": sorted(escalation_queue, key=lambda d: (-d["risk_score"], -d["arr_amount"])),
        "autonomous_log": sorted(autonomous_log, key=lambda d: -d["risk_score"]),
        "all_decisions_count": len(decisions),
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    # Named distinctly from the repo-root dashboard-data.json (the dashboards'
    # own, smaller read file) so the two are never confused for one another.
    with open(OUTPUT_DIR / "dashboard_data_full.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    with open(OUTPUT_DIR / "audit_log.json", "w") as f:
        json.dump(decisions, f, indent=2, default=str)

    return output


if __name__ == "__main__":
    out = run()
    m = out["macro"]
    print(f"Active accounts: {m['total_active_accounts']}  |  Total ARR: ${m['total_arr_active']:,.0f}")
    print(f"High risk: {m['n_high_risk']} (${m['arr_at_risk_high']:,.0f} ARR)  |  Medium risk: {m['n_medium_risk']}")
    print(f"-> Human escalations: {m['n_escalations']}  |  Autonomous actions: {m['n_autonomous']}")
    print(f"Autonomous net benefit: ${m['total_autonomous_net_benefit']:,.0f} "
          f"(saved ${m['total_autonomous_revenue_saved']:,.0f} at a cost of ${m['total_autonomous_cost']:,.0f})")
    print(f"Model AUC (holdout): {m['model_auc_holdout']:.3f}  base churn rate: {m['historical_base_churn_rate']:.1%}")

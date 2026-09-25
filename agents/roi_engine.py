"""
Reasoning & Options Agent
=========================
For a given at-risk account, generates the retention-option menu, and for
each option estimates cost, expected revenue saved, and ROI -- the numbers
senior leadership (or the autonomous router) needs to pick the best option.

Methodology (kept deliberately transparent -- every number here should be
explainable to a human reviewer):

1. Baseline churn probability p0 = the trained risk model's prediction for
   the account as it stands today.
2. For each intervention, we build a *counterfactual* version of the
   account's features reflecting what that intervention plausibly changes
   (e.g. CSM outreach -> satisfaction improves, escalation drops), re-run
   the SAME trained model, and read the new probability p1. The estimated
   uplift is p0 - p1. This is a model-based simulation, not a randomized
   experiment -- it is only as good as the trained model, and is flagged
   as such everywhere it surfaces.
3. The exception is the discount option, where RavenStack has no discount
   history to learn from. That uplift instead comes from the elasticity
   assumption in Retention Playbook Clause 5 (externally benchmarked, not
   fitted on this data) -- kept clearly separate from the model-simulated
   options.
4. cost and revenue_saved are both annualized dollar figures so options are
   comparable; ROI = (revenue_saved - cost) / cost.
"""
import copy
import numpy as np
import pandas as pd

# cost assumptions -- mirror Retention Playbook Clause 3
OPTION_COSTS = {
    "csm_outreach": 450,
    "executive_call": 1200,
    "feature_enablement": 300,
    "discount": None,  # computed per-account as arr * discount_pct
    "monitor": 0,
}
DISCOUNT_PCT_AUTONOMOUS = 0.10   # ceiling the agent can offer without approval (Clause 2)
DISCOUNT_PCT_ESCALATED = 0.20    # a richer offer a human can approve (Clause 1 territory)
DISCOUNT_ELASTICITY_PP_PER_PCT = 0.006  # Clause 5: 0.6pp churn-prob reduction per 1% discount
DISCOUNT_UPLIFT_CAP = 0.20


def _predict(pipe, feat_cols, row_df):
    return float(pipe.predict_proba(row_df[feat_cols])[:, 1][0])


def _counterfactual(df_row, overrides):
    r = df_row.copy()
    for k, v in overrides.items():
        r[k] = v
    return r


def generate_options(account_row, pipe, feat_cols, benchmarks):
    """
    account_row: pandas Series for one live account (must include all feat_cols
                 plus arr_amount, plan_tier).
    benchmarks: dict of reference "healthy account" values, e.g.
                {'avg_satisfaction_good': 4.6, 'distinct_features_used_good': 30, ...}
    Returns: list of option dicts, sorted by net_benefit desc.
    """
    row_df = pd.DataFrame([account_row])
    p0 = _predict(pipe, feat_cols, row_df)
    arr = float(account_row["arr_amount"])
    options = []

    # --- Monitor / no action -------------------------------------------------
    options.append({
        "option": "monitor",
        "label": "Monitor / no action",
        "cost": 0.0,
        "uplift_prob": 0.0,
        "revenue_saved": 0.0,
        "net_benefit": 0.0,
        "roi": 0.0,
        "basis": "baseline",
    })

    # --- CSM outreach (model-simulated) --------------------------------------
    cf = _counterfactual(account_row, {
        "avg_satisfaction": max(account_row["avg_satisfaction"], benchmarks["avg_satisfaction_good"]),
        "escalation_rate": 0.0,
        "days_since_last_ticket": min(account_row["days_since_last_ticket"], 7),
    })
    p1 = _predict(pipe, feat_cols, pd.DataFrame([cf]))
    uplift = max(p0 - p1, 0.0)
    cost = OPTION_COSTS["csm_outreach"]
    revenue_saved = arr * uplift
    options.append({
        "option": "csm_outreach",
        "label": "Proactive CSM outreach + success plan",
        "cost": cost,
        "uplift_prob": uplift,
        "revenue_saved": revenue_saved,
        "net_benefit": revenue_saved - cost,
        "roi": (revenue_saved - cost) / cost if cost else None,
        "basis": "model-simulated (satisfaction ↑, escalation ↓, faster follow-up)",
    })

    # --- Executive relationship call (model-simulated, deeper touch) --------
    cf = _counterfactual(account_row, {
        "avg_satisfaction": benchmarks["avg_satisfaction_max"],
        "escalation_rate": 0.0,
        "days_since_last_ticket": min(account_row["days_since_last_ticket"], 3),
        "distinct_features_used": max(account_row["distinct_features_used"], benchmarks["distinct_features_used_good"]),
    })
    p1 = _predict(pipe, feat_cols, pd.DataFrame([cf]))
    uplift = max(p0 - p1, 0.0)
    cost = OPTION_COSTS["executive_call"]
    revenue_saved = arr * uplift
    options.append({
        "option": "executive_call",
        "label": "Executive relationship call",
        "cost": cost,
        "uplift_prob": uplift,
        "revenue_saved": revenue_saved,
        "net_benefit": revenue_saved - cost,
        "roi": (revenue_saved - cost) / cost if cost else None,
        "basis": "model-simulated (deep touch: satisfaction, escalation, feature adoption)",
    })

    # --- Feature enablement / onboarding refresh (model-simulated) ----------
    cf = _counterfactual(account_row, {
        "distinct_features_used": max(account_row["distinct_features_used"], benchmarks["distinct_features_used_good"]),
        "usage_trend_pct": max(account_row["usage_trend_pct"], 0.0),
        "days_since_last_usage": min(account_row["days_since_last_usage"], 7),
    })
    p1 = _predict(pipe, feat_cols, pd.DataFrame([cf]))
    uplift = max(p0 - p1, 0.0)
    cost = OPTION_COSTS["feature_enablement"]
    revenue_saved = arr * uplift
    options.append({
        "option": "feature_enablement",
        "label": "Feature enablement / onboarding refresh",
        "cost": cost,
        "uplift_prob": uplift,
        "revenue_saved": revenue_saved,
        "net_benefit": revenue_saved - cost,
        "roi": (revenue_saved - cost) / cost if cost else None,
        "basis": "model-simulated (feature adoption ↑, usage trend flattened)",
    })

    # --- Loyalty discount (playbook elasticity assumption, NOT model-fit) ---
    for tag, pct in [("discount10", DISCOUNT_PCT_AUTONOMOUS), ("discount20", DISCOUNT_PCT_ESCALATED)]:
        uplift = min(pct * 100 * DISCOUNT_ELASTICITY_PP_PER_PCT, DISCOUNT_UPLIFT_CAP)
        cost = arr * pct
        revenue_saved = arr * uplift
        options.append({
            "option": tag,
            "label": f"Loyalty discount ({int(pct*100)}% of ARR)",
            "cost": cost,
            "uplift_prob": uplift,
            "revenue_saved": revenue_saved,
            "net_benefit": revenue_saved - cost,
            "roi": (revenue_saved - cost) / cost if cost else None,
            "basis": "playbook elasticity assumption (Clause 5, externally benchmarked)",
            "requires_approval": pct > DISCOUNT_PCT_AUTONOMOUS,
        })

    options.sort(key=lambda o: o["net_benefit"], reverse=True)
    return options, p0


def compute_benchmarks(df):
    retained = df[df["churn_flag"] == False]  # noqa: E712
    return {
        "avg_satisfaction_good": float(retained["avg_satisfaction"].quantile(0.75)),
        "avg_satisfaction_max": float(retained["avg_satisfaction"].max()),
        "distinct_features_used_good": float(retained["distinct_features_used"].quantile(0.75)),
    }

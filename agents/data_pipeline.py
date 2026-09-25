"""
Signal Ingestion Agent
======================
Loads the RavenStack B2B SaaS source tables (accounts, subscriptions,
churn_events, support_tickets, feature_usage), joins them into a single
account-level analysis table, and engineers the micro-signal features
that the Risk Scoring Agent consumes.

This is Agent #1 in the orchestrator pipeline: it owns "what is happening"
(the signals), not "what it means" (that's the Risk Agent) or "what to do
about it" (the Reasoning/ROI Agent).
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_raw():
    accounts = pd.read_excel(DATA_DIR / "ravenstack_accounts.xlsx")
    subs = pd.read_excel(DATA_DIR / "ravenstack_subscriptions.xlsx")
    churn = pd.read_excel(DATA_DIR / "ravenstack_churn_events.xlsx")
    tickets = pd.read_excel(DATA_DIR / "ravenstack_support_tickets.xlsx")
    usage = pd.read_excel(DATA_DIR / "ravenstack_feature_usage.xlsx")
    return accounts, subs, churn, tickets, usage


def build_account_table(as_of=None):
    """
    Returns one row per account with:
      - firmographics (industry, country, plan tier, seats)
      - current subscription economics (mrr, arr, billing_frequency, auto_renew)
      - contract signal history (upgrade/downgrade counts, trial history)
      - support-health signals (ticket volume, escalation rate, avg CSAT,
        avg resolution time, days since last ticket)
      - usage-health signals (event volume, error rate, 30d usage trend)
      - churn outcome (label, used for model training/backtest only)
      - churn context (reason_code, refund) for accounts that did churn
    """
    accounts, subs, churn, tickets, usage = _load_raw()
    as_of = as_of or max(
        subs["start_date"].max(), tickets["submitted_at"].max(), usage["usage_date"].max()
    )

    # --- current / most-recent subscription per account -------------------
    subs = subs.sort_values("start_date")
    cur_sub = subs.groupby("account_id").tail(1).set_index("account_id")
    sub_hist = subs.groupby("account_id").agg(
        n_subscriptions=("subscription_id", "count"),
        ever_upgraded=("upgrade_flag", "max"),
        ever_downgraded=("downgrade_flag", "max"),
        ever_trial=("is_trial", "max"),
        total_arr_ever=("arr_amount", "sum"),
    )

    # --- support-health signals --------------------------------------------
    t = tickets.copy()
    sup = t.groupby("account_id").agg(
        ticket_count=("ticket_id", "count"),
        escalation_rate=("escalation_flag", "mean"),
        avg_satisfaction=("satisfaction_score", "mean"),
        avg_resolution_hours=("resolution_time_hours", "mean"),
        avg_first_response_min=("first_response_time_minutes", "mean"),
        last_ticket_date=("submitted_at", "max"),
    )
    sup["days_since_last_ticket"] = (as_of - sup["last_ticket_date"]).dt.days

    # --- usage-health signals (joined via subscription_id -> account_id) --
    sub_to_acct = subs.set_index("subscription_id")["account_id"]
    u = usage.copy()
    u["account_id"] = u["subscription_id"].map(sub_to_acct)
    u = u.dropna(subset=["account_id"])
    window_recent = as_of - pd.Timedelta(days=30)
    window_prior = as_of - pd.Timedelta(days=60)
    recent = u[u["usage_date"] >= window_recent].groupby("account_id")["usage_count"].sum()
    prior = u[(u["usage_date"] >= window_prior) & (u["usage_date"] < window_recent)].groupby(
        "account_id"
    )["usage_count"].sum()
    usage_agg = u.groupby("account_id").agg(
        usage_events=("usage_id", "count"),
        total_usage_count=("usage_count", "sum"),
        total_errors=("error_count", "sum"),
        distinct_features_used=("feature_name", "nunique"),
        last_usage_date=("usage_date", "max"),
    )
    usage_agg["error_rate"] = usage_agg["total_errors"] / usage_agg["total_usage_count"].clip(lower=1)
    usage_agg["days_since_last_usage"] = (as_of - usage_agg["last_usage_date"]).dt.days
    usage_trend = pd.DataFrame({"usage_recent_30d": recent, "usage_prior_30d": prior}).fillna(0)
    usage_trend["usage_trend_pct"] = np.where(
        usage_trend["usage_prior_30d"] > 0,
        (usage_trend["usage_recent_30d"] - usage_trend["usage_prior_30d"])
        / usage_trend["usage_prior_30d"],
        0.0,
    )

    # --- churn outcome + context --------------------------------------------
    churn_ctx = churn.sort_values("churn_date").groupby("account_id").tail(1).set_index("account_id")

    # --- assemble ------------------------------------------------------------
    df = accounts.set_index("account_id").copy()
    df["tenure_days"] = (as_of - df["signup_date"]).dt.days

    df = df.join(cur_sub[[
        "mrr_amount", "arr_amount", "billing_frequency", "auto_renew_flag",
        "start_date", "end_date", "plan_tier",
    ]].rename(columns={"plan_tier": "current_plan_tier", "start_date": "sub_start", "end_date": "sub_end"}))
    df = df.join(sub_hist)
    df = df.join(sup)
    df = df.join(usage_agg[[
        "usage_events", "total_usage_count", "error_rate",
        "distinct_features_used", "days_since_last_usage",
    ]])
    df = df.join(usage_trend[["usage_trend_pct"]])
    df = df.join(churn_ctx[["reason_code", "refund_amount_usd"]].rename(
        columns={"reason_code": "churn_reason_code", "refund_amount_usd": "churn_refund_usd"}
    ))

    # sensible fill-ins for accounts with no tickets/usage on record
    df["ticket_count"] = df["ticket_count"].fillna(0)
    df["escalation_rate"] = df["escalation_rate"].fillna(0)
    df["avg_satisfaction"] = df["avg_satisfaction"].fillna(df["avg_satisfaction"].median())
    df["avg_resolution_hours"] = df["avg_resolution_hours"].fillna(df["avg_resolution_hours"].median())
    df["avg_first_response_min"] = df["avg_first_response_min"].fillna(df["avg_first_response_min"].median())
    df["days_since_last_ticket"] = df["days_since_last_ticket"].fillna(9999)
    df["n_subscriptions"] = df["n_subscriptions"].fillna(1)
    df["usage_events"] = df["usage_events"].fillna(0)
    df["error_rate"] = df["error_rate"].fillna(0)
    df["distinct_features_used"] = df["distinct_features_used"].fillna(0)
    df["days_since_last_usage"] = df["days_since_last_usage"].fillna(9999)
    df["usage_trend_pct"] = df["usage_trend_pct"].fillna(0)
    df["mrr_amount"] = df["mrr_amount"].fillna(0)
    df["arr_amount"] = df["arr_amount"].fillna(df["mrr_amount"] * 12)
    df["ever_upgraded"] = df["ever_upgraded"].fillna(False)
    df["ever_downgraded"] = df["ever_downgraded"].fillna(False)
    df["auto_renew_flag"] = df["auto_renew_flag"].fillna(False)

    df["is_churned"] = df["churn_flag"].fillna(False) | df.index.isin(churn_ctx.index)
    df["days_to_renewal"] = np.where(
        df["sub_end"].notna(), (df["sub_end"] - as_of).dt.days, np.nan
    )

    df = df.reset_index().rename(columns={"index": "account_id"})
    return df, as_of


if __name__ == "__main__":
    df, as_of = build_account_table()
    print(f"as_of={as_of.date()}  accounts={len(df)}  churned={df['is_churned'].sum()}")
    print(df.head(3).T)

"""
Risk Scoring Agent
==================
Turns raw signals (from the Signal Ingestion Agent) into a calibrated,
explainable Renewal Risk Score (0-100) per account.

Ground truth: `accounts.churn_flag` — whether the account has, at any
point, fully churned (22% base rate in the RavenStack book of business,
in line with typical enterprise SaaS annual attrition). We train on the
full historical population (390 retained / 110 churned) and then score
the *currently active, not-yet-churned* accounts — i.e. this is a live
prospective risk score, not a backward-looking label.

Leakage discipline: any field that is only observable *because* an
account churned (churn_reason_code, churn_refund_usd, subscription
end_date/days_to_renewal, is_churned) is excluded from the feature set.
Only signals that exist while the account is still a live customer are
used.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

from data_pipeline import build_account_table

NUMERIC_FEATURES = [
    "tenure_days", "seats", "mrr_amount", "arr_amount",
    "n_subscriptions", "ticket_count", "escalation_rate",
    "avg_satisfaction", "avg_resolution_hours", "avg_first_response_min",
    "days_since_last_ticket", "usage_events", "error_rate",
    "distinct_features_used", "days_since_last_usage", "usage_trend_pct",
]
BOOL_FEATURES = ["is_trial", "ever_upgraded", "ever_downgraded", "ever_trial", "auto_renew_flag"]
CATEGORICAL_FEATURES = ["industry", "country", "plan_tier", "billing_frequency", "referral_source"]
TARGET = "churn_flag"


def _pipeline():
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("bool", "passthrough", BOOL_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))])


def train_and_score():
    df, as_of = build_account_table()
    feat_cols = NUMERIC_FEATURES + BOOL_FEATURES + CATEGORICAL_FEATURES
    model_df = df.copy()
    for c in BOOL_FEATURES:
        model_df[c] = model_df[c].astype(bool).astype(int)

    X = model_df[feat_cols]
    y = model_df[TARGET].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    pipe = _pipeline()
    pipe.fit(X_train, y_train)
    auc_test = roc_auc_score(y_test, pipe.predict_proba(X_test)[:, 1])

    # benchmark against gradient boosting to confirm logistic reg isn't leaving
    # a lot of signal on the table (we keep logistic reg in production for
    # its transparent, per-feature explainability -- important for a
    # decision that a human or an autonomous agent has to justify)
    gb_pre = ColumnTransformer([
        ("num", "passthrough", NUMERIC_FEATURES),
        ("bool", "passthrough", BOOL_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    gb = Pipeline([("pre", gb_pre), ("clf", GradientBoostingClassifier(random_state=42))])
    gb.fit(X_train, y_train)
    auc_gb = roc_auc_score(y_test, gb.predict_proba(X_test)[:, 1])

    # refit logistic reg on full history for deployment, then score the
    # live (not-yet-churned) book of business
    pipe.fit(X, y)
    live = model_df[model_df[TARGET] == False].copy()  # noqa: E712
    live_X = live[feat_cols]
    live["risk_score"] = pipe.predict_proba(live_X)[:, 1] * 100

    # --- explainability: per-account top risk drivers -----------------------
    clf = pipe.named_steps["clf"]
    pre = pipe.named_steps["pre"]
    feature_names = (
        NUMERIC_FEATURES + BOOL_FEATURES
        + list(pre.named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES))
    )
    coefs = clf.coef_[0]
    transformed_live = pre.transform(live_X)
    if hasattr(transformed_live, "toarray"):
        transformed_live = transformed_live.toarray()
    contributions = transformed_live * coefs  # per-account, per-feature log-odds contribution

    HUMAN_LABELS = {
        "avg_satisfaction": "low support satisfaction",
        "escalation_rate": "high support-ticket escalation rate",
        "avg_resolution_hours": "slow ticket resolution",
        "avg_first_response_min": "slow first response time",
        "days_since_last_ticket": "long gap since last support contact",
        "usage_trend_pct": "declining product usage",
        "error_rate": "elevated in-product error rate",
        "days_since_last_usage": "product usage has gone stale",
        "distinct_features_used": "narrow feature adoption",
        "tenure_days": "account tenure",
        "seats": "seat count",
        "mrr_amount": "monthly recurring revenue",
        "arr_amount": "annual contract value",
        "n_subscriptions": "renewal-cycle history",
        "ticket_count": "support ticket volume",
        "usage_events": "product usage volume",
        "auto_renew_flag": "auto-renew not enabled",
        "ever_downgraded": "history of downgrading",
        "ever_upgraded": "history of upgrading",
        "ever_trial": "converted from trial",
        "is_trial": "still on trial",
    }

    def top_drivers(row_idx, n=3):
        row = contributions[row_idx]
        order = np.argsort(-row)[:n]
        drivers = []
        for i in order:
            if row[i] <= 0:
                continue
            fname = feature_names[i]
            label = HUMAN_LABELS.get(fname, fname.replace("_", " "))
            for pretty_cat in CATEGORICAL_FEATURES:
                if fname.startswith(pretty_cat + "_"):
                    label = f"{pretty_cat}={fname[len(pretty_cat) + 1:]}"
            drivers.append(label)
        return drivers

    live = live.reset_index(drop=True)
    live["risk_drivers"] = [top_drivers(i) for i in range(len(live))]

    metrics = {
        "as_of": str(as_of.date()),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "base_churn_rate": float(y.mean()),
        "auc_logreg_holdout": float(auc_test),
        "auc_gbm_holdout": float(auc_gb),
        "n_live_accounts_scored": int(len(live)),
    }
    return live, metrics, df


if __name__ == "__main__":
    live, metrics, df = train_and_score()
    print(metrics)
    print(live[["account_id", "account_name", "risk_score", "risk_drivers"]].sort_values(
        "risk_score", ascending=False
    ).head(10).to_string())

---
name: renewal-risk-feature-engineering
description: Use this skill whenever you are joining raw CRM, billing, support or usage tables into a feature set for a churn or renewal-risk model. It defines the leakage-safe "as-of" join pattern that keeps holdout metrics honest. Trigger this any time a churn/risk model's accuracy looks suspiciously high, when a new source table is being added to an existing risk model, or when someone asks "why did our churn model stop working in production" — that gap is almost always leakage that training data didn't have.
---

# Leakage-safe feature engineering for renewal-risk models

## Why this matters

A renewal-risk model is scored on accounts that **haven't churned yet**. If
any feature in training was only observable *because* an account already
churned, the model learns to read the outcome instead of predicting it. It
will look excellent on a random holdout split (because churned accounts in
the holdout still carry those tell-tale fields) and then fail silently in
production, where live accounts never have them. This is the single most
common way a churn model quietly stops working after launch, and it's
invisible unless you specifically check for it.

## The as-of snapshot pattern

Pick a single "as-of" date and freeze every input feature at that moment —
never later. Concretely: for a churn-events table, an active account has no
churn record at all as of that date, and a historically-churned account
(used for training labels) has one. The feature table you build must look
identical in *shape* for both — same columns, same fill logic — and differ
only in the columns that were legitimately knowable before the outcome.

```python
# as_of is fixed once, not "today" recomputed per account
def build_account_table(as_of=None):
    as_of = as_of or churn_events["event_date"].max()
    ...
```

## The test that catches leakage

Before trusting any feature, ask: **is this column populated for every
account that already churned, but null or meaningless for every account
that's still active?** If yes, it's leakage. Common offenders in a
subscription/CRM context:

- Churn reason / cancellation reason codes
- Refund amount or refund flag
- Subscription end date (as opposed to subscription *start* date or
  contract length, which are fine)
- "Days to churn" or any field computed relative to a churn event
- Final invoice status, downgrade-then-cancel sequences

Fields that are **not** leakage even though they sound related: contract
length, renewal date (a future scheduled date, not an outcome), plan tier,
historical usage trend up to the as-of date, past support ticket volume.
The line is causal direction — was this knowable *before* the outcome, or
does it only exist *because of* the outcome?

## Sanity checks to run every time

1. **Suspiciously high AUC.** If holdout AUC is above ~0.85–0.9 on a
   realistic churn base rate (most B2B SaaS books churn 10–30% annually),
   stop and audit your feature list before celebrating — this is the
   single strongest smell test for leakage.
2. **Null-pattern check.** For each candidate feature, compare the null
   rate among churned vs. still-active accounts. A feature that's ~100%
   populated for churned accounts and ~0% populated for active ones is
   leaking the label, not predicting it.
3. **Fill missing values deliberately, not by dropping rows.** A support
   or usage metric that's null because an account is new (no ticket
   history yet) should be imputed with a sensible default (e.g. the
   population median, or a "no data" indicator feature) — silently
   dropping those rows biases the training set toward established
   accounts and will make the model perform worse exactly on the
   new-account segment where risk teams need it most.

```python
df["avg_first_response_min"] = df["avg_first_response_min"].fillna(
    df["avg_first_response_min"].median()
)
df["n_subscriptions"] = df["n_subscriptions"].fillna(1)
```

## Worked example from this repo

`agents/data_pipeline.py` joins five RavenStack tables (accounts,
subscriptions, churn events, support tickets, feature usage) into one
account-level table. `agents/risk_model.py` explicitly separates
`NUMERIC_FEATURES` / `BOOL_FEATURES` / `CATEGORICAL_FEATURES` (used for
scoring live accounts) from the churn-event fields (used only to build the
training label). Read those two files together as the reference
implementation of this pattern before extending the feature set.

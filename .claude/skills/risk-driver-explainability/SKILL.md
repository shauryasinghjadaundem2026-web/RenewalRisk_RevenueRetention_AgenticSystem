---
name: risk-driver-explainability
description: Use this skill whenever a trained risk, churn, fraud or scoring model needs to explain WHY a specific record got its score, in plain language a business user can act on — not raw feature names and coefficients. Trigger this when building "top reasons" or "risk drivers" output for a dashboard, when a stakeholder asks "why is this account flagged," or when a model's output needs to justify itself to a non-technical reviewer.
---

# Turning model coefficients into plain-language "why" explanations

## Why this matters

A risk score without a reason is not actionable. "This account is 84/100"
tells a reviewer nothing about what to *do*. "High support-ticket
escalation rate, elevated in-product error rate, product usage has gone
stale" tells them exactly which retention lever to pull. The gap between
those two is almost pure formatting and labeling work, not modeling work —
which is exactly why it's worth doing well and consistently rather than
skipping it because "the model is a black box."

## The method (for linear / coefficient-based models)

For a fitted logistic regression (or any linear model) scored on a
standardized feature matrix, each feature's **contribution** to one
record's score is:

```
contribution_i = coefficient_i * standardized_value_i
```

To get the top drivers for one specific account:

1. Compute `contribution_i` for every feature, for that one record.
2. Rank by **absolute value** of contribution (a strongly protective
   factor is just as informative as a strongly risky one — show both if
   the audience benefits from knowing what's going *right*, otherwise
   filter to positive/risk-increasing contributions only).
3. Take the top 2–4 — more than that stops being scannable.
4. Map each raw feature name through a human-label dictionary before
   showing it to anyone. Never surface a raw column name like
   `avg_first_response_min_z` — surface "slow support response times."

```python
HUMAN_LABELS = {
    "support_escalation_rate": "high support-ticket escalation rate",
    "product_error_rate": "elevated in-product error rate",
    "usage_trend": "product usage has gone stale",
    # ... one entry per feature that could plausibly be a top driver
}
```

## Writing good labels

- Describe the **direction that increases risk**, since that's almost
  always what gets surfaced. "Usage trend" is a bad label because it's
  directionless; "product usage has gone stale" is unambiguous.
- Keep each label to 3–6 words. These get read in a table row or a chip,
  not a paragraph.
- Write them once, in one dictionary, and keep every feature that could
  ever be a top driver represented — a missing mapping means a raw column
  name leaks into the UI, which erodes trust in the whole system fast.
- Don't editorialize beyond the direction. "High support-ticket
  escalation rate" is a fact; "customer seems unhappy" is an inference the
  model didn't actually make.

## Caveats

- **Correlated features double-count.** If "days since last login" and
  "usage trend" are highly correlated, both may show up as top drivers for
  the same underlying reason. This is usually fine for a human reader (it
  reinforces the same story) but don't present them as independent causes
  in a headline number.
- **One-hot categorical features** should be aggregated back to their
  parent category before ranking — "industry_healthtech = 1" contributing
  a large coefficient should be reported as "industry: HealthTech," not as
  a mysterious dummy variable.
- **Tree-based / non-linear models** need a different technique (SHAP or
  permutation importance) since there's no single coefficient per feature
  — the labeling and top-N presentation logic above still applies once you
  have per-record contribution values from either method.

## Worked example from this repo

`agents/risk_model.py`'s `HUMAN_LABELS` dictionary and the driver-extraction
logic in `train_and_score()` are the reference implementation: every live
account gets its top-3 drivers computed this way and surfaced directly in
the dashboard's escalation queue and account explorer.

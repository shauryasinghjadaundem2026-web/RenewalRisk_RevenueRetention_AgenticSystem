---
name: retention-roi-simulation
description: Use this skill whenever an agent must rank interventions (discounts, outreach, feature enablement, win-back offers, etc.) by cost and revenue impact instead of by a risk score alone, and whenever a revenue-impact number needs to be honestly labeled as either a model-based simulation or an externally sourced assumption. Trigger this for retention offers, churn-prevention intervention ranking, discount-approval logic, or any "which option should we pick" cost/benefit agent decision.
---

# Cost/ROI simulation for retention (or any intervention-ranking) agent

## Why this matters

A risk score tells you *who* is at risk. It says nothing about *what to do*
or whether doing it is worth the cost. An agent that recommends the same
"executive call" for every at-risk account regardless of ARR or of what's
actually driving the risk is not reasoning — it's pattern-matching a
template. Ranking real options by cost, revenue saved and ROI is what turns
a risk score into a decision a business can defend.

## The two kinds of revenue-impact estimate — and why you must label which is which

There are two honest ways to estimate what an intervention is worth, and
conflating them is the single most common way this kind of system loses
credibility with the people who have to sign off on it:

**1. Model-based counterfactual simulation** — for interventions that
change something your trained model already uses as a feature (CSM
outreach reduces support friction, feature enablement improves usage
trend, an executive call may lift satisfaction score):

```
1. Take the account's current feature vector.
2. Perturb only the feature(s) the intervention is known to move,
   by a documented, reasonable amount.
3. Re-score the perturbed vector with the SAME trained model.
4. delta_risk = original_risk - perturbed_risk
5. revenue_saved = delta_risk * account_ARR  (scaled appropriately)
```

This is grounded in the fitted model — it's not a randomized trial, but
it's not a guess either. Label it as **"fitted"** / **"model simulation."**

**2. Externally benchmarked assumption** — for interventions your dataset
has no history of (e.g. a discount program that's never been run before,
so there's no internal elasticity to fit). Use a conservative, sourced,
external benchmark, document exactly where it came from, and cap it so a
single assumption can't produce an absurd result. Label it as
**"assumed"** / **"externally benchmarked, not fitted"** — everywhere it
surfaces: in the code, in the UI, in any document describing the system.

Never let an assumed number look identical to a fitted one in the output.
The moment someone can't tell which numbers are backed by the model and
which are a documented guess, the whole system's credibility rests on
nobody checking — which is exactly when it should be checked.

## Building the option table

For each candidate option, compute:

| Field | Meaning |
|---|---|
| `cost` | From a single, versioned cost catalogue — not re-derived per call |
| `revenue_saved` | Via method 1 or 2 above, always tagged with its basis |
| `net_benefit` | `revenue_saved - cost` |
| `roi` | `net_benefit / cost` (define behavior for the zero-cost "do nothing" option explicitly — treat it as a baseline, not infinite ROI) |
| `basis` | `"fitted"` or `"assumed"` — never omit this field |

Rank by `net_benefit`, not by `roi` alone — ROI can make a trivially cheap,
trivially small-impact option look artificially attractive (a $10 action
that saves $50 has huge ROI but may not be the right recommendation for a
$200K account).

## Keep the cost catalogue in one place

Maintain costs (CSM hours, exec time, tooling spend, discount % → $)
as a single reviewed table, not inline magic numbers scattered through the
scoring code. Reference it by name/clause wherever it's used, and note
when it was last reviewed — costs drift, and a stale cost table quietly
skews every downstream recommendation.

## Worked example from this repo

`agents/roi_engine.py`'s `generate_options()` implements both estimation
paths: CSM outreach / executive call / feature enablement use model-based
counterfactual simulation (see `compute_benchmarks()` for the healthy-
account reference values perturbations are drawn toward); discount tiers
use the externally benchmarked elasticity assumption documented in
`policy/retention_playbook.md` Clause 5, explicitly flagged everywhere it
surfaces as assumed rather than fitted.

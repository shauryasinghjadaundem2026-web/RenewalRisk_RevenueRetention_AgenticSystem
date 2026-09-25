# Renewal & Retention Playbook (v1.0)
*Approved reference policy for the autonomous Renewal Risk & Revenue Retention Agent.
Owner: Revenue Operations. Last reviewed: 2026-09-23.*

## Clause 1 — Human-in-the-loop escalation thresholds
Any account meeting **any** of the following conditions must be routed to a
human decision-maker and may **not** be actioned autonomously:
- Renewal Risk Score >= 70 **and** Annual Contract Value (ARR) >= $15,000, OR
- Plan Tier = "Enterprise" **and** Renewal Risk Score >= 40 (Enterprise
  accounts get a lower bar, but a purely low-risk Enterprise account does
  not need to consume a human reviewer's time), OR
- Any proposed retention option requires a discount greater than 10% of ARR, OR
- Any proposed retention option costs more than $1,000 to execute.

## Clause 2 — Autonomous action authority (Low/Medium risk, within bounds)
For accounts that do not trigger Clause 1, the agent may act without human
sign-off, subject to:
- Maximum autonomous discount: 10% of ARR, single use per renewal cycle.
- Maximum autonomous outreach spend: $1,000 (covers CSM time, onboarding
  refresh sessions, in-app nudges).
- Every autonomous action must be logged with account, signals, chosen
  option, cost, expected revenue impact, and the policy clause it satisfies.
- Autonomous actions are reviewed in aggregate by RevOps weekly; any account
  that re-enters the risk queue within 60 days of an autonomous action is
  auto-escalated to a human on the next pass (no second autonomous attempt).

## Clause 3 — Retention option catalogue & cost assumptions
These are the finance-approved cost/effort assumptions used by the ROI
engine. Discount cost is computed directly from account ARR; all other
costs are fully-loaded time-cost estimates, reviewed quarterly.
| Option | Typical cost | When to use |
|---|---|---|
| Loyalty discount (renewal-term price reduction) | ARR x discount% | Price-sensitive signals, competitor mentions, budget-driven risk |
| Proactive CSM outreach + success plan | ~$450 (3 CSM hours) | Support friction, satisfaction dip, missed touchpoints |
| Executive relationship call | ~$1,200 (senior AE/CSM + exec prep) | High-ARR or strategic accounts showing relationship risk |
| Feature enablement / onboarding refresh | ~$300 (solutions engineer session) | Usage decline, narrow feature adoption, under-utilization |
| Monitor / no action | $0 | Low risk score, no material signal |

## Clause 4 — Value tiering
- **High value**: ARR >= $15,000 (approx. top quartile of the active book).
- **Standard value**: ARR < $15,000.
High-value accounts get a lower escalation bar (see Clause 1) because the
downside of a wrong autonomous call is larger.

## Clause 5 — Discount elasticity assumption
In the absence of controlled discount experiments in this book of business,
the agent uses a conservative, externally-benchmarked SaaS elasticity
assumption: **each 1 percentage point of discount reduces annualized churn
probability by 0.6 percentage points, capped at a 20-point total
reduction.** This assumption is flagged as *externally sourced, not fitted
on internal data* everywhere it is surfaced, and must be replaced with an
internal A/B-tested figure once available.

## Clause 6 — Reactivation guardrail
Accounts with `is_reactivation = true` in their churn history are treated as
elevated risk regardless of score (past churn-and-return pattern) and are
capped at one further autonomous retention attempt before mandatory
escalation.

## Clause 7 — Audit & override
Every decision (autonomous or human-approved) is logged with a full
reasoning trace and the policy clause it relied on. A human may override any
recommendation; overrides are logged and feed the quarterly policy review.

# Architecture — Renewal Risk & Revenue Retention Agent

## 1. Executive summary

This system watches a live book of B2B SaaS accounts, scores each one's
renewal risk, works out what (if anything) is worth doing about it in
cost/ROI terms, and either does it autonomously or hands it to a human —
depending on how much is at stake. Every step is logged, so any decision
can be replayed and audited later.

On the current snapshot of the RavenStack dataset: 390 live accounts,
$11.56M active ARR. The router sends 76 accounts (19% of the book, $2.44M
ARR) to human escalation and handles 314 autonomously, for an estimated
$70,050 net benefit this cycle ($84,450 revenue saved at $14,400 cost).

**Agent = Model + Harness.**

- **Model** — the trained reasoning core: a logistic regression risk
  classifier (holdout AUC 0.61, benchmarked against gradient boosting) plus
  a counterfactual simulation engine that re-scores "what happens if we
  intervene" scenarios using that same trained model.
- **Harness** — everything wrapped around the model: the six-agent
  pipeline, tool calling into five Python modules, RAG retrieval over the
  policy playbook, guardrails bounding autonomous action, and the audit log
  that makes every decision replayable.

## 2. System overview — the six-agent pipeline

```
Signal        Risk         Reasoning     Policy        Decision      Action &
Ingestion --> Scoring  --> & ROI    -->  Agent    -->  Router   -->  Audit
Agent         Agent        Agent         (RAG)         Agent         Agent
```

| # | Agent | File | Job |
|---|---|---|---|
| 1 | Signal Ingestion | `agents/data_pipeline.py` | Joins accounts, subscriptions, churn events, support tickets and product usage into one account-level feature table — the micro-signals. |
| 2 | Risk Scoring | `agents/risk_model.py` | Scores every live (non-churned) account 0–100 on renewal risk; extracts the top-3 human-readable risk drivers per account. |
| 3 | Reasoning & ROI | `agents/roi_engine.py` | Generates a menu of retention options per account and ranks them by cost, revenue saved, net benefit and ROI — not risk score alone. |
| 4 | Policy (RAG) | `agents/policy_rag.py` | Retrieves the exact playbook clause that governs the recommendation, so every decision is grounded in a citable policy, not improvised. |
| 5 | Decision Router | `agents/orchestrator.py` | Checks the account and the recommended option against the escalation guardrails and routes it: human review, or cleared for autonomous action. |
| 6 | Action & Audit | `agents/orchestrator.py` | Executes the cleared action, or records the human's decision once made, and writes the full reasoning trace to the audit log. |

Each agent is a plain Python function/module — a deliberate choice over a
heavier agent framework, so the whole pipeline is inspectable, testable and
replayable end to end with `python3 agents/orchestrator.py`.

## 3. Data & signals

Source: the RavenStack B2B SaaS dataset (500 accounts, ~5,000 subscription
cycles, ~600 churn events, support tickets, feature usage), sourced from a
public GitHub repository as a real substitute for Kaggle (unreachable from
the original build environment — see the README's "Why this data source"
section).

Five tables are joined into one account-level table per account, as of a
fixed snapshot date:

- **Accounts** — plan tier, industry, country, ARR.
- **Subscriptions** — active/churned state, contract history.
- **Churn events** — historical churn outcomes and reasons (used only for
  training labels and driver analysis on already-churned accounts; any
  field only observable *because* an account already churned is excluded
  from the live feature set to prevent leakage).
- **Support tickets** — volume, escalation rate, average first-response
  time, satisfaction.
- **Feature/product usage** — usage trend, days since last login, days
  since last ticket.

## 4. Risk scoring methodology

- **Model**: `sklearn` `Pipeline` — a `ColumnTransformer` (numeric scaling +
  one-hot categoricals) feeding a `LogisticRegression` with
  `class_weight="balanced"` (the base churn rate is ~22%, so class balance
  matters).
- **Validation**: 75/25 stratified train/holdout split. Holdout AUC ≈ 0.61.
  Benchmarked against a `GradientBoostingClassifier` (AUC ≈ 0.57) — logistic
  regression was kept for its transparency (linear coefficients map
  directly to human-readable drivers) at no real cost in discrimination.
- **Leakage safety**: any field that only exists because an account already
  churned (churn reason, refund flag, subscription end-date) is excluded
  from the feature set used to score *live* accounts.
- **Explainability**: for each live account, the model's coefficient
  contributions are ranked and the top 3 are mapped through a
  human-readable label dictionary (`HUMAN_LABELS` in `risk_model.py`) —
  e.g. "high support-ticket escalation rate" rather than a raw feature
  name and coefficient.
- **Refit**: after holdout validation, the model is refit on the full
  historical dataset before scoring the live population, to use all
  available signal for the numbers that actually drive decisions.

## 5. Reasoning & ROI engine

For each live account, `roi_engine.py` generates up to five retention
options (monitor / no action, proactive CSM outreach, executive
relationship call, feature enablement, and one or two discount tiers), and
for each one computes:

- **Cost** — from the finance-approved cost catalogue (Playbook Clause 3).
- **Revenue saved** — via one of two methods, and the system is explicit
  about which:
  - *Model-based counterfactual simulation* for CSM outreach, executive
    call and feature enablement: the intervention's typical effect on the
    relevant input features (e.g. usage trend improves, ticket escalation
    drops) is applied, and the same trained risk model re-scores the
    account under that hypothetical. This is a simulation grounded in the
    fitted model, not a randomized trial.
  - *Externally benchmarked assumption* for discounts (Playbook Clause 5):
    0.6 percentage points of annualized churn-probability reduction per 1
    point of discount, capped at 20 points — because the dataset has no
    internal discount history to fit elasticity on. This is flagged
    everywhere it surfaces as *assumed*, not fitted.
- **Net benefit** = revenue saved − cost. **ROI** = net benefit / cost
  (or treated as infinite/undefined for the zero-cost "monitor" option).

Options are ranked by net benefit, and the top-ranked option becomes the
recommendation the Decision Router and the human reviewer see.

## 6. Policy retrieval (RAG)

`policy_rag.py` implements retrieval-augmented grounding over
`policy/retention_playbook.md` (the 7-clause guardrail document):

- The playbook is split into clauses on `## ` headers.
- Each clause is vectorised with `TfidfVectorizer` (`scikit-learn`).
- A query built from the account's situation (risk tier, value tier,
  recommended option, discount size) is vectorised the same way, and
  `cosine_similarity` retrieves the single most relevant clause.
- That clause is attached to the decision record, so the dashboard and the
  audit log can always show *which specific rule* authorised or bounded
  the recommendation.

This is TF-IDF + cosine similarity rather than an embeddings/vector-DB
stack — a deliberate choice for a document this small (7 clauses): it is
fully deterministic, needs no external service, and is trivially
swappable for a real vector store if the policy document grows.

## 7. Human-in-the-loop workflow

`orchestrator.py`'s Decision Router evaluates every account against
Playbook Clause 1 (see `policy/retention_playbook.md`). Any account that
trips a threshold — high risk *and* high ARR, Enterprise tier at moderate
risk, or any option requiring a discount over 10% or spend over $1,000 —
is routed to the **Escalation queue** instead of being actioned
automatically.

In the dashboard, an escalated account shows its full option table (cost,
revenue saved, net benefit, ROI for every option, not just the
recommended one) so a reviewer can compare alternatives on their own
terms, then approve the recommendation, approve a different option, or
reject and monitor only. The **Agent console** tab is the same
review surface presented as a live, step-by-step replay: pick any account
(escalated or autonomous) and it walks through all six agents in order —
signals in, risk score, ranked options, the retrieved policy clause, the
routing decision, and the same Approve/Reject controls — over the
pipeline's own pre-computed output, client-side, with no server calls.
The console and the Escalation queue tab read and write the same decision
state, so a reviewer can approve an account in either view and see it
reflected in both. A **Run all** control in the console cycles through
every account currently in the (optionally filtered) queue list
automatically, replaying each one's six steps in turn — a fast way to
sanity-check the whole Review or Autonomous queue rather than one account
at a time; clicking it again mid-run stops it. Every decision — human or
autonomous — is written to the audit log with who decided, when, and
which policy clause applied (Playbook Clause 7).

The **Overview** tab has its own live entry point at the portfolio level:
**Replay agent cycle** animates a scan through all 390 live accounts,
ticking the KPI tiles, the "$X of $Y ARR shows elevated renewal risk"
headline and a progress bar up account by account as it re-derives the
same totals the batch pipeline computed (total ARR, ARR at risk,
escalation count and ARR, autonomous net benefit) — the same live-run
impression as the Agent console, but for the whole book at once rather
than one account. Below it, **Largest accounts awaiting a decision** and
**Agent pipeline this cycle** give an at-a-glance summary of the highest-
stakes open decisions and what each of the six agents did this pass,
without leaving the Overview tab.

This is the system's central design commitment: **the model never gets to
unilaterally decide what happens to a high-stakes account** — it can only
prepare the best possible case for a human to decide on quickly.

## 8. Guardrails

Enforced by the Decision Router (Playbook Clauses 1–2, 6):

- Escalate if risk ≥ 70 and ARR ≥ $15,000, or Enterprise tier and risk ≥ 40.
- Escalate any option with a discount over 10% of ARR or a cost over $1,000.
- Autonomous authority is capped at a 10%-of-ARR discount and $1,000 spend,
  used at most once per renewal cycle per account.
- An account that re-enters the risk queue within 60 days of an autonomous
  action is auto-escalated on the next pass — no second unsupervised
  attempt at the same account.
- Reactivated accounts (previously churned and returned) are treated as
  elevated risk regardless of score, and capped at one further autonomous
  attempt.

## 9. Tool calling & skills

The orchestrator calls each agent's module as a discrete, logged function —
there is no hidden state between steps. The reasoning patterns that make
the output trustworthy rather than just plausible-sounding are written up
as real Claude Skills in `.claude/skills/` (loadable `SKILL.md` files, not
just prose in this document):

| Skill | Pattern |
|---|---|
| `renewal-risk-feature-engineering` | Leakage-safe joins — the as-of snapshot pattern |
| `risk-driver-explainability` | Coefficient contributions → plain-language driver labels |
| `retention-roi-simulation` | Cost/ROI ranking with fitted-vs-assumed labeling |
| `policy-clause-grounding` | TF-IDF retrieval for citable policy grounding |
| `hitl-escalation-guardrails` | The autonomous-vs-human-review boundary |

None of this reasoning is hidden inside a black-box call — it's ordinary,
readable Python in `agents/`, and the skill for each pattern explains *why*
it's built that way, so the reasoning survives being copied into a
different project even after the original code is gone.

## 10. Results snapshot (current data)

- 390 live accounts scored, $11.56M active ARR.
- 26 accounts at ≥70 risk score ($739K ARR).
- 76 accounts (19%) escalated to human review, $2.44M ARR.
- 314 accounts (81%) handled autonomously.
- Autonomous actions this cycle: $84,450 revenue saved at $14,400 cost =
  $70,050 net benefit.
- Model holdout AUC 0.61 against a 22% base churn rate (positive, modest
  lift — treat scores as triage, not certainty).

## 11. Limitations & next steps

- Discount elasticity is an externally benchmarked assumption, not fitted
  on internal experiment data — replace with an A/B-tested figure.
- Not wired to a live CRM/billing feed; runs as a batch pipeline today.
- TF-IDF retrieval is adequate for a 7-clause playbook; a larger policy
  library would benefit from embeddings + a real vector store.
- The standalone dashboard's human-in-the-loop decisions are stored in
  browser memory only (no backend) — see the README for how to wire
  `writeDecision()` to a real datastore for production use.

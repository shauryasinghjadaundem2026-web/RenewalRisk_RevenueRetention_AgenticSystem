# Renewal Risk & Revenue Retention Agent

A multi-agent, human-in-the-loop system that scores renewal risk across a
B2B SaaS book of business, reasons about retention options in cost/ROI
terms, grounds every decision in a policy playbook (RAG), and routes each
account to either a human reviewer or an autonomous action — logging every
decision it makes.

**Agent = Model + Harness.** The *model* is a trained risk-scoring
classifier plus a counterfactual simulation engine. The *harness* is the
six-agent pipeline, tool calling, RAG retrieval, guardrails, Claude Skills
and an audit log wrapped around it. See [`ARCHITECTURE.md`](./ARCHITECTURE.md)
for the full design write-up.

## See it without installing anything

Open **`index.html`** directly in a browser (double-click it, or drag it
into a tab). The account data is embedded in the file, so it needs no
server, no build step and no network access — it works the same on any
laptop, offline, straight from a USB stick or a GitHub download. **This is
the one to open if you just want to see the dashboard.**

It opens on the **Overview** tab and immediately runs a live **"Replay
agent cycle"** — a fast animated scan through all 390 live accounts, with
the KPI tiles, the headline ("$X of $Y ARR shows elevated renewal risk")
and the progress bar ticking up account by account until every account is
scored and routed. Click **Replay agent cycle** any time to watch it run
again. Below that, **Largest accounts awaiting a decision** lists the
highest-ARR accounts still needing a human call (with a live decision
status and a link straight to the full Escalation queue), and **Agent
pipeline this cycle** summarizes what each of the six agents actually did
this pass (accounts ingested, the risk-tier split, options costed per
account, policy clauses cited, how the router split the book, and how many
decisions were logged).

Go to the **Agent console** tab, pick any account from the queue on the
left, and click **Run agents**. It replays the six-agent pipeline live for
that account — signals, risk score, ranked retention options, the exact
policy clause retrieved, the routing decision, and either a working
Approve/Reject panel (for an escalated account) or the automatically
executed action (for an autonomous one). This is the same walkthrough
shown in the demo video and the hosted Claude artifact — running entirely
client-side here, over the pipeline's own pre-computed output, so it needs
no backend either. Click **Run all** instead to cycle through every
account currently in the (optionally filtered) queue list automatically,
one after another — a quick way to eyeball the whole Review or Autonomous
queue rather than one account at a time; it doubles as a **Stop** button
while it's running.

### Running `dashboard.html` instead

`dashboard.html` is the same UI, but it loads its data from
`dashboard-data.json` with `fetch()` instead of embedding it — that only
works when the page is served over `http(s)`, not opened directly as a
`file://` path (browsers block a page from `fetch()`-ing a local file for
security reasons, so double-clicking `dashboard.html` will show "Data
failed to load"). To run it:

```bash
# from inside this folder
python3 -m http.server 8000
# then open http://localhost:8000/dashboard.html in a browser
```

Any other static server works too (`npx serve`, VS Code's "Live Server"
extension, or just pushing the repo to GitHub Pages). Use `dashboard.html`
over `index.html` when you want to edit `dashboard-data.json` and see the
change on refresh, without regenerating anything. `index.html` is
generated *from* `dashboard.html` by `tools/build_index.py` — see below.

## Run the pipeline yourself

```bash
pip install -r requirements.txt
python3 agents/orchestrator.py          # 1. score accounts, route, write output/
python3 tools/build_dashboard_data.py   # 2. build dashboard-data.json from that output
python3 tools/build_index.py            # 3. rebuild the standalone index.html
```

Step 1 reads the raw data in `data/`, joins it, scores every live account,
generates retention options, retrieves the governing policy clause, routes
each account to human review or autonomous action, and writes:

- `output/dashboard_data_full.json` — full detail for every account
- `output/audit_log.json` — every decision made, replayable

Step 2 derives `dashboard-data.json` from that full output (the file the
dashboards actually read — it adds a couple of convenience fields the
tables use, but keeps every account's full option table, policy clause
text and routing reason, so the Agent console can replay any of them).
Step 3 re-embeds that data into `index.html`. Run all three whenever the
underlying data or model changes; if you only edited `dashboard.html`
itself, step 3 alone is enough.

## Repository layout

| Path | What it is |
|---|---|
| `agents/data_pipeline.py` | Signal Ingestion Agent — joins accounts, subscriptions, churn events, support tickets and product usage into one account-level table |
| `agents/risk_model.py` | Risk Scoring Agent — logistic regression renewal-risk score (0–100) + top drivers per account, leakage-safe |
| `agents/roi_engine.py` | Reasoning & ROI Agent — generates and ranks retention options by cost, revenue saved, ROI |
| `agents/policy_rag.py` | Policy Agent — TF-IDF retrieval over `policy/retention_playbook.md`; every decision cites a clause |
| `agents/orchestrator.py` | Decision Router + Audit Agent — routes each account (human vs. autonomous) per the playbook and logs the full trace |
| `policy/retention_playbook.md` | The 7-clause guardrail policy the agents are bound by |
| `data/*.xlsx` | Raw RavenStack B2B SaaS dataset (accounts, subscriptions, churn, tickets, usage) |
| `dashboard-data.json` | Pre-built data snapshot the dashboards read — full per-account detail (signals, options, policy clause text, routing reason) for every account, so the Agent console can replay any of them |
| `index.html` | Standalone dashboard — data embedded, no server needed |
| `dashboard.html` | Same dashboard, loads data via `fetch()` — for serving over http(s) |
| `tools/build_dashboard_data.py` | Builds `dashboard-data.json` from `output/dashboard_data_full.json` |
| `tools/build_index.py` | Regenerates `index.html` from `dashboard.html` + `dashboard-data.json` |
| `output/` | Full pipeline output (regenerated by `orchestrator.py`) |
| `ARCHITECTURE.md` | Full system design write-up |
| `CLAUDE.md` | Repo map and conventions, for an AI coding assistant picking this project back up |
| `skills/` | Claude Skills — the reasoning patterns this agent relies on, written up as `SKILL.md` files (see below) |
| `.claude/skills/` | Identical copy of `skills/`, at the path Claude Code auto-loads skills from |

## Claude Skills

This repo ships its "Skills" layer as real, loadable [Claude Skills](./skills/)
— not just a bullet list in a diagram. **Look in the `skills/` folder** (it's
duplicated at `.claude/skills/` too, since that's the path Claude Code
actually auto-loads from, and dotfolders don't show up in Finder/Explorer
by default — if you don't see `.claude` after unzipping, that's why; it's
there, just hidden). Open this repo in Claude Code and they trigger
automatically when the task matches; each one also reads fine as
standalone documentation of a pattern worth reusing elsewhere:

- **`renewal-risk-feature-engineering`** — the leakage-safe "as-of" join pattern for churn/risk models
- **`risk-driver-explainability`** — turning model coefficients into plain-language "why" output
- **`retention-roi-simulation`** — ranking interventions by cost/ROI, with fitted-vs-assumed labeling
- **`policy-clause-grounding`** — lightweight RAG (TF-IDF, no vector DB) for citing the policy clause behind a decision
- **`hitl-escalation-guardrails`** — designing the autonomous-vs-human-review boundary

See [`skills/README.md`](./skills/README.md) for details. If you ever edit
one, copy the change into both `skills/` and `.claude/skills/` — they're
meant to stay identical.

## Why this data source

The brief called for a real dataset. Kaggle's API was not reachable from
the environment this was originally built in, so this pipeline uses
**RavenStack**, a structured B2B SaaS dataset (accounts, subscriptions,
churn events, support tickets, feature usage) built for renewal-risk /
survival analysis, sourced from a public GitHub repository
(`PrathamMehta1011/B2B-SaaS-Customer-Churn-Survival-Analysis`). It is real,
not synthetic — swap in your own export from Kaggle, your CRM, or your
billing system by matching the five table schemas documented in
`agents/data_pipeline.py`.

## Honesty notes

- Holdout AUC ≈ 0.61 on a 22% base churn rate — a real, positive lift over
  chance, but modest. Treat scores as triage, not certainty.
- CSM outreach, executive call and feature-enablement uplift are **model
  counterfactual simulations** (perturb the features the intervention
  changes, re-score with the same trained model) — not a randomized trial.
- Discount uplift is an **externally benchmarked assumption** (Playbook
  Clause 5), because RavenStack has no discount history to fit on. Replace
  with an internal A/B-tested figure once you have one.
- Any field only observable because an account already churned (churn
  reason, refund, subscription end-date) is excluded from model features
  to avoid leakage.

## Human-in-the-loop

Every account above the escalation guardrail (see `policy/retention_playbook.md`,
Clause 1) shows up in both the **Agent console** (as a live, step-by-step
run) and the **Escalation queue** tab (as a static list you can filter and
sort) with its full option table — cost, revenue saved, net benefit, ROI —
so a reviewer can approve the recommendation, pick an alternative, or
reject and monitor only. The two views share the same decision state: approve
an account in the console and the queue tab shows the same decision
immediately, and vice versa. Decisions made in `index.html` / `dashboard.html`
are stored in the browser's memory for that session (labelled "local
only") since the standalone page has no backend; wire `writeDecision()` in
the dashboard's script to your own datastore or API to persist them for a
real deployment.

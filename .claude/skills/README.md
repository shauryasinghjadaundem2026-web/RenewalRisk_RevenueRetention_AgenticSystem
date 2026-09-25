# Claude Skills

These are the "Skills" layer from the architecture diagram, written up as
real [Claude Skills](https://www.anthropic.com/news/skills) — each is a
`SKILL.md` that Claude (in Claude Code or Cowork) loads automatically when
its description matches the task at hand.

They're not tied to this one dataset. Each one documents a reusable
pattern this agent depends on, so it can be applied to a different churn
model, a different policy document, or a different retention program:

| Skill | Pattern it captures |
|---|---|
| `renewal-risk-feature-engineering` | Leakage-safe joins for a churn/risk model — the "as-of" snapshot pattern |
| `risk-driver-explainability` | Turning model coefficients into plain-language "why this account is flagged" output |
| `retention-roi-simulation` | Ranking interventions by cost/ROI, and honestly labeling fitted vs. assumed revenue-impact numbers |
| `policy-clause-grounding` | Lightweight RAG (TF-IDF, no vector DB) for citing the exact policy clause behind a decision |
| `hitl-escalation-guardrails` | Designing the autonomous-vs-human-review boundary for an agent that spends money or takes real actions |

If you open this repo in Claude Code, these load automatically from
`.claude/skills/` — a byte-for-byte copy of this folder kept at that path
because that's where Claude Code looks, and dotfolders don't show up in
Finder/Explorer by default. This `skills/` folder is the plainly-visible
copy, meant for people browsing the repo. If you edit a skill, update both
copies.

Ask Claude Code to extend the risk model, add a retention option, or
change the escalation policy, and the relevant skill kicks in on its own.
They also work as standalone documentation: each one explains *why* the
pattern matters, not just what to type, so they're worth reading even
without Claude in the loop.

To reuse one of these in a different project, copy its folder into that
project's own `.claude/skills/`.

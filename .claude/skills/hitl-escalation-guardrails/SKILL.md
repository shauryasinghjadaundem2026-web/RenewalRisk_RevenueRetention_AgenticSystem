---
name: hitl-escalation-guardrails
description: Use this skill when designing the boundary between autonomous agent action and mandatory human review — the guardrails that decide which cases an agent may act on alone versus which must go to a person. Trigger this when building any agent that spends money, offers discounts, contacts customers, or takes other real-world actions with cost or risk, when asked for a defensible human-in-the-loop policy, or when tuning an escalation queue that's come out too large or too small.
---

# Designing human-in-the-loop escalation guardrails

## Why this matters

An agent that can act on everything autonomously is a liability the moment
it's wrong about something expensive. An agent that escalates everything
to a human defeats the point of building it. The guardrail layer is what
lets an agent handle the high-volume, low-stakes majority of cases on its
own while making sure the cases where being wrong is costly always get a
person's judgment first. Getting this boundary right — and being able to
explain *why* it's drawn where it is — is usually more important to
whether stakeholders trust the system than the accuracy of the underlying
model.

## Core principle: escalate on stakes × uncertainty, not risk alone

A high-risk, low-value account and a low-risk, high-value account are not
the same problem. Escalation should be a function of **what's at stake if
the agent is wrong** (account value, size of the proposed spend/discount)
combined with **how uncertain the recommendation is** (risk score, model
confidence, whether the case matches a pattern the model was trained on).
A threshold on risk score alone either escalates too many low-value
accounts (wasting reviewer time) or lets a high-value account slip through
autonomously (the actual failure mode you're trying to prevent).

## What a solid guardrail policy specifies

1. **Escalation thresholds, compound rather than single.** e.g. "risk ≥ 70
   AND ARR ≥ $15K" OR "Enterprise tier AND risk ≥ 40" catches both the
   generically risky and the strategically important, without escalating
   every Enterprise account regardless of actual risk.
2. **Hard caps on autonomous spend/discount.** A ceiling the agent may
   never cross without a human, independent of risk score — this is your
   backstop against a model that's confidently wrong.
3. **A "no second unsupervised attempt" rule.** If an autonomous action
   didn't work (the account re-enters the risk queue within some window),
   don't let the agent try again on its own — escalate on the next pass.
   Autonomy for a first attempt is reasonable; autonomy for a repeated
   failure is not.
4. **An explicit override path.** A human can always override any
   recommendation, autonomous or not, and every override is logged and
   feeds the next policy review — the guardrails should make the agent's
   default behavior safe, not make the human's judgment subordinate to it.
5. **Full audit logging**, for autonomous actions and human decisions
   alike: what was decided, by what/whom, and which policy clause
   justified it (see the `policy-clause-grounding` skill).
6. **A human-readable home for the thresholds.** Keep them in a policy
   document a non-engineer can read and approve, not as magic numbers
   buried in application code — the whole point of a guardrail is that
   someone other than the engineer who wrote it can review and sign off on
   where the line is drawn.

## Tuning an escalation queue that's the wrong size

If the queue is too large (reviewers are drowning, most escalations turn
out fine on inspection): don't just raise a single threshold blindly — you
may be escalating a whole segment that doesn't need it. Look for a
compound condition to add instead. For example: an "Enterprise tier always
escalates" rule will flood the queue with low-risk Enterprise accounts;
adding a risk floor ("Enterprise AND risk ≥ 40") keeps the strategic
safety net while cutting the noise — in this repo's own build, that single
change cut escalations from 131 to 76 without changing the underlying risk
model at all.

If the queue is too small (autonomous actions are going wrong that
should've been reviewed): check whether the guardrail is keyed to the
right stakes variable — often a spend/discount cap that's too generous, or
a risk threshold that doesn't account for account value, is the actual
gap, not the model's accuracy.

## Worked example from this repo

`policy/retention_playbook.md` Clauses 1–2 and 6 define the guardrails;
`agents/orchestrator.py`'s Decision Router enforces them and
`agents/policy_rag.py` attaches the governing clause to every decision.
`ARCHITECTURE.md` §8 documents the specific thresholds in use.

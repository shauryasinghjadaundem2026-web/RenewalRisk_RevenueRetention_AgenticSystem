---
name: policy-clause-grounding
description: Use this skill whenever an autonomous agent's decisions need to be grounded in and cite a specific clause of a written policy, playbook, SOP or compliance document — a lightweight retrieval-augmented-generation (RAG) pattern for small, static policy documents that doesn't need a vector database. Trigger this when building guardrails that must be auditable, when a decision needs to show "which rule authorized this," or when asked to add RAG to an agent but the knowledge base is small (a playbook, a handbook chapter, a short SOP — tens of sections, not thousands of documents).
---

# Grounding agent decisions in a policy document (lightweight RAG)

## Why this matters

An agent that takes autonomous action needs to be able to answer "which
rule said you could do that?" — not just "the model was confident." Citing
the specific clause that authorized a decision is what makes an autonomous
action auditable after the fact, and it's what lets a non-engineer reviewer
(compliance, RevOps, legal) approve the *policy* once instead of having to
trust every individual decision the agent makes.

## When TF-IDF + cosine similarity is the right tool

Skip the vector database and embeddings pipeline when your knowledge base
is: static (changes rarely, reviewed by humans when it does), small
(tens of sections, not thousands of documents), and each section is
genuinely self-contained (a clause that stands alone, not a paragraph that
depends on surrounding context to mean anything). A retention playbook, an
escalation policy, an internal SOP chapter — all of these fit. TF-IDF is
fully deterministic, needs no external service or API key, costs nothing
per query, and is trivial to unit-test.

Graduate to embeddings + a real vector store when the corpus grows past
that (hundreds+ of documents), when sections aren't self-contained, or
when queries need to match on meaning rather than shared vocabulary (TF-IDF
only catches lexical overlap — "reduce the discount" won't match a clause
about "loyalty pricing" unless they share words).

## The pattern

1. **Split the document into self-contained units.** One `##` header =
   one retrievable clause. Each clause should make sense read in
   isolation — if a clause says "as above," restructure it so it doesn't.

2. **Vectorize once, at load time**, not per query:
   ```python
   vectorizer = TfidfVectorizer()
   clause_vectors = vectorizer.fit_transform(clause_texts)
   ```

3. **Build the query from the decision's own structured attributes**,
   not free-form text — this is the detail that makes retrieval reliable.
   A query like `"high risk enterprise discount"` built from
   `f"{risk_tier} {value_tier} {recommended_option} discount"` retrieves
   far more consistently than trying to paraphrase the situation in prose.

4. **Retrieve top-1 (or top-k) by cosine similarity** and attach the
   clause's full text — or at minimum its identifying header — to the
   decision record. Never just log "policy applied"; log *which* policy.

5. **Test retrieval with a small golden set.** For 5–10 known scenarios,
   assert the retriever returns the clause a human would pick for that
   scenario. This catches phrasing drift (e.g. renaming a clause header)
   before it silently breaks citations in production.

## Worked example from this repo

`agents/policy_rag.py`'s `PolicyRetriever` class implements exactly this:
`load_clauses()` splits `policy/retention_playbook.md` on `## ` headers,
`TfidfVectorizer` + `cosine_similarity` retrieve the governing clause for
each account's situation, and the returned clause is attached to every
escalation and every autonomous-action record shown in the dashboard and
written to the audit log.

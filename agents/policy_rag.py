"""
Policy Agent (RAG layer)
========================
Retrieval-augmented grounding over the Retention Playbook. Every routing
decision the orchestrator makes (escalate vs. act autonomously, how much
discount is permitted, what an option costs) must cite the specific policy
clause it relied on -- this module is what fetches that clause.

Implementation note: the playbook is a handful of short clauses, so a full
vector DB is overkill. We use TF-IDF + cosine similarity (scikit-learn) as
a lightweight, fully-local retriever. The interface is the same shape a
production system would use with an embedding index, so swapping in a real
vector store later is a drop-in change (see ARCHITECTURE notes).
"""
import re
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PLAYBOOK_PATH = Path(__file__).resolve().parent.parent / "policy" / "retention_playbook.md"


def load_clauses():
    text = PLAYBOOK_PATH.read_text()
    chunks = re.split(r"\n(?=## )", text)
    clauses = []
    for c in chunks:
        c = c.strip()
        if not c.startswith("## "):
            continue
        title = c.splitlines()[0].replace("## ", "").strip()
        clauses.append({"title": title, "text": c})
    return clauses


class PolicyRetriever:
    def __init__(self):
        self.clauses = load_clauses()
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in self.clauses])

    def retrieve(self, query, k=1):
        qv = self.vectorizer.transform([query])
        sims = cosine_similarity(qv, self.matrix)[0]
        order = sims.argsort()[::-1][:k]
        return [
            {"title": self.clauses[i]["title"], "score": float(sims[i]), "text": self.clauses[i]["text"]}
            for i in order
        ]


if __name__ == "__main__":
    r = PolicyRetriever()
    for q in [
        "high risk enterprise account discount above 10 percent",
        "low risk account autonomous CSM outreach cost",
        "reactivation churn history repeat customer",
    ]:
        hit = r.retrieve(q, k=1)[0]
        print(f"Q: {q}\n  -> {hit['title']} (sim={hit['score']:.2f})\n")

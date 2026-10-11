"""Retrieval-only eval: for golden cases that must cite a provision, is that provision in the top-k?

No LLM needed. Compares dense-only, BM25-only, hybrid, and hybrid+rerank.
Run:  python -m evals.retrieval_eval
"""

from __future__ import annotations

import json
from pathlib import Path

from app.rag.retriever import RRF_K, Retriever
from app.rules.engine import assess
from app.rules.models import ClaimFacts

GOLDEN = Path(__file__).parent / "datasets" / "golden.jsonl"


def recall(r: Retriever, cases: list[dict], mode: str, k: int) -> float:
    hits = 0
    for c in cases:
        q = c["turns"][0]
        if mode == "anchored":
            # Upper bound for the agent: citations from the rules engine run on the gold facts
            # (assumes the agent classified the claim correctly; end-to-end accuracy is measured separately).
            facts = ClaimFacts(**c["facts"])
            a = assess(facts)
            regime = {"reg_e": "E", "reg_z": "Z"}.get(a.regime.value)
            anchored = [h.citation for h in r.by_citation(a.citations)]
            cites = anchored + [h.citation for h in r.search(q, regime=regime, k=k, rerank=True)]
        elif mode == "dense":
            cites = [r.chunks[i]["citation"] for i in r.dense(q, k)]
        elif mode == "bm25":
            cites = [r.chunks[i]["citation"] for i in r.sparse(q, k)]
        else:
            cites = [h.citation for h in r.search(q, k=k, rerank=(mode == "hybrid+rerank"))]
        hits += all(any(ci.startswith(m) for ci in cites) for m in c["expected"]["must_cite"])
    return hits / len(cases)


def main() -> None:
    cases = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines()]
    cases = [c for c in cases if c["expected"].get("must_cite")]
    r = Retriever()
    print(f"{len(cases)} cases with required citations; RRF k={RRF_K}")
    for k in (5, 10):
        row = {m: recall(r, cases, m, k) for m in ("dense", "bm25", "hybrid", "hybrid+rerank", "anchored")}
        print(f"recall@{k}: " + "  ".join(f"{m}={v:.2f}" for m, v in row.items()))


if __name__ == "__main__":
    main()

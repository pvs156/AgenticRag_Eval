"""Hybrid retrieval: dense (bge-small via fastembed, stored in Qdrant) + BM25, fused with reciprocal rank
fusion, then an optional cross-encoder rerank. Everything runs locally on CPU at no cost."""

from __future__ import annotations

import atexit
import json
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi

from app.config import ROOT, Settings, get_settings

CHUNKS = ROOT / "corpus" / "processed" / "chunks.jsonl"
MANIFEST = ROOT / "corpus" / "processed" / "manifest.json"
RRF_K = 60


@dataclass
class Hit:
    chunk: dict
    score: float

    @property
    def citation(self) -> str:
        return self.chunk["citation"]


_TOKEN = re.compile(r"\d+\.\d+(?:\([a-z0-9]+\))*|\$?\d+|[a-z]+")


def tokenize(text: str) -> list[str]:
    """Lowercase words plus legal citations like 1005.11(c)(2) kept as single tokens."""
    return _TOKEN.findall(text.lower())


class Retriever:
    def __init__(self, settings: Settings | None = None, chunks_path: Path = CHUNKS):
        self.s = settings or get_settings()
        self.chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line]
        self.version = json.loads(MANIFEST.read_text())["corpus_version"] if MANIFEST.exists() else "dev"
        self.collection = f"corpus_{self.version}"
        self._bm25 = BM25Okapi([tokenize(c["heading"] + " " + c["text"]) for c in self.chunks])

    # ------------------------------------------------------------------ lazy heavy objects

    @cached_property
    def embedder(self):
        from fastembed import TextEmbedding

        return TextEmbedding(self.s.embed_model, cache_dir=str(self.s.cache_dir / "fastembed"))

    @cached_property
    def reranker(self):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        return TextCrossEncoder(self.s.rerank_model, cache_dir=str(self.s.cache_dir / "fastembed"))

    @cached_property
    def qdrant(self) -> QdrantClient:
        if self.s.qdrant_url:
            client = QdrantClient(url=self.s.qdrant_url)
        else:
            client = QdrantClient(path=str(self.s.cache_dir / "qdrant"))
        atexit.register(client.close)  # close cleanly instead of in __del__ during interpreter shutdown
        self._ensure_index(client)
        return client

    def _ensure_index(self, client: QdrantClient) -> None:
        if client.collection_exists(self.collection):
            if client.count(self.collection).count == len(self.chunks):
                return
            client.delete_collection(self.collection)
        texts = [f"{c['heading']}\n{c['text']}" for c in self.chunks]
        vectors = list(self.embedder.embed(texts))
        client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE),
        )
        client.upsert(
            self.collection,
            points=[
                models.PointStruct(id=i, vector=v.tolist(), payload={"i": i, "regime": c["regime"]})
                for i, (c, v) in enumerate(zip(self.chunks, vectors, strict=True))
            ],
        )

    # ------------------------------------------------------------------ search

    def dense(self, query: str, k: int, regime: str | None = None) -> list[int]:
        vec = next(iter(self.embedder.query_embed(query))).tolist()
        flt = (
            models.Filter(must=[models.FieldCondition(key="regime", match=models.MatchValue(value=regime))])
            if regime
            else None
        )
        res = self.qdrant.query_points(self.collection, query=vec, limit=k, query_filter=flt)
        return [p.payload["i"] for p in res.points]

    def sparse(self, query: str, k: int, regime: str | None = None) -> list[int]:
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        order = [i for i in order if scores[i] > 0 and (regime is None or self.chunks[i]["regime"] == regime)]
        return order[:k]

    def search(
        self, query: str, regime: str | None = None, k: int | None = None, rerank: bool | None = None
    ) -> list[Hit]:
        """regime: "E" | "Z" | None. Returns the top `context_k` hits."""
        k_retrieve = self.s.retrieve_k
        k_out = k or self.s.context_k
        fused: dict[int, float] = {}
        for ranking in (self.dense(query, k_retrieve, regime), self.sparse(query, k_retrieve, regime)):
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        candidates = sorted(fused, key=lambda i: -fused[i])[:k_retrieve]
        if not candidates:
            return []
        if rerank if rerank is not None else self.s.enable_rerank:
            docs = [f"{self.chunks[i]['heading']}\n{self.chunks[i]['text']}" for i in candidates]
            scores = list(self.reranker.rerank(query, docs))
            ranked = sorted(zip(candidates, scores, strict=True), key=lambda x: -x[1])
            return [Hit(self.chunks[i], float(s)) for i, s in ranked[:k_out]]
        return [Hit(self.chunks[i], fused[i]) for i in candidates[:k_out]]

    def by_citation(self, prefixes: list[str], limit_per_prefix: int = 2) -> list[Hit]:
        """Fetch regulation chunks whose citation starts with each prefix (e.g. '12 CFR 1005.11(c)').

        Used by the agent after the rules engine has identified the governing provisions, so the answer is
        anchored on the right text even when the customer's wording shares no words with the regulation.
        """
        out: list[Hit] = []
        seen: set[str] = set()
        for p in prefixes:
            matches = [c for c in self.chunks if c["kind"] == "regulation" and c["citation"].startswith(p)]
            for c in matches[:limit_per_prefix]:
                if c["chunk_id"] not in seen:
                    seen.add(c["chunk_id"])
                    out.append(Hit(c, 1.0))
        return out


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever

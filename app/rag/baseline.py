"""Naive RAG baseline: retrieve with the customer's own words, then generate. No rules engine, no
classification, no verification, no retries. It exists to measure what the agentic design adds."""

from __future__ import annotations

from datetime import date

from app.llm.client import LLM, make_generator
from app.rag.retriever import Retriever, get_retriever
from app.schemas import AssistantReply, SourceRef

SYSTEM = """You help bank customers with card and account disputes. Today is {today}.
Answer using ONLY the regulation excerpts provided. Cite the excerpt citation in square brackets,
for example [12 CFR 1005.11(c)]. If the excerpts do not answer the question, say so.
Keep the answer under 200 words."""


def answer(question: str, today: date, llm: LLM | None = None, retriever: Retriever | None = None) -> AssistantReply:
    llm = llm or make_generator()
    retriever = retriever or get_retriever()
    hits = retriever.search(question)
    context = "\n\n".join(f"[{h.citation}] {h.chunk['heading']}\n{h.chunk['text']}" for h in hits)
    text = llm.chat(
        [
            {"role": "system", "content": SYSTEM.format(today=today.isoformat())},
            {"role": "user", "content": f"Regulation excerpts:\n{context}\n\nCustomer: {question}"},
        ],
        name="baseline.generate",
        max_tokens=600,
    )
    return AssistantReply(
        reply=text,
        sources=[
            SourceRef(citation=h.citation, heading=h.chunk["heading"], url=h.chunk["url"], as_of=h.chunk["as_of"])
            for h in hits
        ],
        system="baseline",
        corpus_version=retriever.version,
    )

import json
from pathlib import Path

import pytest

from app.rag.ingest import pack, split_by_numbers, split_section

CHUNKS = Path(__file__).resolve().parents[2] / "corpus" / "processed" / "chunks.jsonl"


def test_split_section_does_not_confuse_roman_i_with_letter_i():
    paras = ["(a) Alpha", "(i) roman one", "(ii) roman two", "(b) Beta", "(c) Gamma", "(i) roman under c"]
    groups = split_section(paras)
    assert [g[0] for g in groups] == ["a", "b", "c"]
    assert groups[2][1] == ["(c) Gamma", "(i) roman under c"]


def test_split_by_numbers_reads_inline_first_number():
    paras = ["(c) Time limits—(1) Ten-day period text", "(2) Forty-five day text", "(i) sub", "(3) Ext"]
    parts = split_by_numbers("c", paras)
    assert [p[0] for p in parts] == ["(c)(1)", "(c)(2)", "(c)(3)"]
    assert parts[1][1] == ["(2) Forty-five day text", "(i) sub"]


def test_pack_respects_word_limit():
    paras = ["word " * 200, "word " * 200, "word " * 10]
    assert len(pack(paras)) == 2


@pytest.mark.skipif(not CHUNKS.exists(), reason="run `python -m app.rag.ingest` first")
def test_corpus_has_key_provisions_with_provenance():
    chunks = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines()]
    citations = {c["citation"] for c in chunks}
    for needed in [
        "12 CFR 1005.2(m)",
        "12 CFR 1005.6(b)(1)",
        "12 CFR 1005.11(b)",
        "12 CFR 1005.11(c)(2)",
        "12 CFR 1026.12(b)(1)",
        "12 CFR 1026.13(a)",
        "12 CFR 1026.13(c)",
    ]:
        assert needed in citations, needed
    for c in chunks:
        assert c["text"].strip() and c["url"].startswith("https://www.ecfr.gov/") and c["as_of"]
        assert len(c["text"].split()) <= 400
    assert "§" in "".join(c["text"] for c in chunks), "UTF-8 section symbols preserved"

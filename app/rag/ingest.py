"""Fetch primary regulation text from the eCFR API and chunk it by legal structure.

Usage:  python -m app.rag.ingest            (fetch if not cached, then chunk)
        python -m app.rag.ingest --refresh  (re-download)

Outputs:
  corpus/raw/<source_id>.xml          raw eCFR XML (cached)
  corpus/processed/chunks.jsonl       one chunk per line, with provenance
  corpus/processed/manifest.json      corpus version (hash of all chunks) and per-source hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "corpus"
ECFR_FULL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-12.xml"
MAX_WORDS = 350  # split a paragraph group further when it exceeds this


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    regime: str  # E | Z
    kind: str  # regulation | interpretation
    citation: str  # human-readable legal citation
    heading: str
    text: str
    url: str
    as_of: str
    retrieved_at: str


# --------------------------------------------------------------------------- fetch


def ecfr_url(as_of: str, ecfr: dict) -> str:
    return ECFR_FULL.format(date=as_of) + "?" + urlencode(ecfr)


def public_url(ecfr: dict) -> str:
    """Browser-friendly eCFR link for citations shown to users."""
    if "section" in ecfr:
        return f"https://www.ecfr.gov/current/title-12/section-{ecfr['section']}"
    return f"https://www.ecfr.gov/current/title-12/part-{ecfr['part']}"


def fetch(source: dict, as_of: str, refresh: bool) -> Path:
    path = CORPUS / "raw" / f"{source['id']}.xml"
    if path.exists() and not refresh:
        return path
    # eCFR requires a compression-capable client; httpx sends Accept-Encoding by default.
    r = httpx.get(ecfr_url(as_of, source["ecfr"]), timeout=60, follow_redirects=True)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


# --------------------------------------------------------------------------- text helpers


def text_of(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def words(s: str) -> int:
    return len(s.split())


_LEAD = re.compile(r"^\((?P<tok>[a-z]+|\d+)\)")


def lead_token(p: str) -> str | None:
    m = _LEAD.match(p)
    return m.group("tok") if m else None


# --------------------------------------------------------------------------- regulation sections


def split_section(paras: list[str]) -> list[tuple[str, list[str]]]:
    """Group paragraphs into top-level (a), (b), ... units.

    Roman numerals like (i) are ambiguous with the letter (i); a paragraph only opens a new
    top-level unit when its letter is the next expected one.
    """
    groups: list[tuple[str, list[str]]] = []
    expected = "a"
    current: tuple[str, list[str]] | None = None
    for p in paras:
        tok = lead_token(p)
        if tok == expected:
            current = (tok, [p])
            groups.append(current)
            expected = chr(ord(expected) + 1)
        elif current is None:
            current = ("", [p])
            groups.append(current)
        else:
            current[1].append(p)
    return groups


def split_by_numbers(label: str, paras: list[str]) -> list[tuple[str, list[str]]]:
    """Split a long top-level unit at second-level (1), (2), ... boundaries.

    The first paragraph often reads "(c) Heading—(1) ...", so numbering starts there.
    """
    parts: list[tuple[str, list[str]]] = []
    expected = 1
    for i, p in enumerate(paras):
        inner = re.match(r"^\([a-z]\)[^()]*?—\((\d+)\)", p) if i == 0 else None
        tok = inner.group(1) if inner else lead_token(p)
        if tok == str(expected):
            parts.append((f"({label})({tok})", [p]))
            expected += 1
        elif not parts:
            parts.append((f"({label})", [p]))
        else:
            parts[-1][1].append(p)
    return parts


def chunk_section(source: dict, root: ET.Element, meta: dict) -> list[Chunk]:
    section = source["ecfr"]["section"]
    head = text_of(root.find("HEAD"))
    paras = [text_of(p) for p in root.iter("P")]
    out: list[Chunk] = []
    for label, group in split_section(paras):
        body = "\n".join(group)
        pieces = (
            split_by_numbers(label, group)
            if words(body) > MAX_WORDS and label
            else [(f"({label})" if label else "", group)]
        )
        for sub, sub_paras in pieces:
            citation = f"12 CFR {section}{sub}"
            out.append(make_chunk(source, meta, citation, head, "\n".join(sub_paras)))
    return out


# --------------------------------------------------------------------------- official interpretations


def chunk_interpretations(source: dict, root: ET.Element, meta: dict) -> list[Chunk]:
    """Supplement I: HD1 = section, HD2/HD3 = paragraph headings, P = numbered comments."""
    keep = set(source.get("keep_sections", []))
    part = source["ecfr"]["part"]
    out: list[Chunk] = []
    section: str | None = None
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        if section in keep and buf:
            for piece in pack(buf):
                citation = f"12 CFR Part {part}, Supp. I, {heading}"
                out.append(make_chunk(source, meta, citation, f"Official interpretation: {heading}", piece))
        buf.clear()

    # Heading levels differ between supplements (Reg E: section in HD1; Reg Z: Subpart in HD1,
    # section in HD2), so classify headings by their text instead of their tag.
    for el in root.iter():
        if el.tag.startswith("HD"):
            flush()
            label = text_of(el)
            m = re.match(r"Section (\d+\.\d+)", label)
            if m:
                section = m.group(1)
            elif re.match(r"(Subpart|Appendix|Appendices|Supplement)\b", label):
                section = None
            heading = label
        elif el.tag == "P":
            buf.append(text_of(el))
    flush()
    return out


def pack(paras: list[str]) -> list[str]:
    """Pack consecutive paragraphs into pieces of at most MAX_WORDS (a single long one stays whole)."""
    pieces: list[list[str]] = [[]]
    for p in paras:
        if pieces[-1] and words("\n".join(pieces[-1] + [p])) > MAX_WORDS:
            pieces.append([])
        pieces[-1].append(p)
    return ["\n".join(x) for x in pieces if x]


# --------------------------------------------------------------------------- assembly


def make_chunk(source: dict, meta: dict, citation: str, heading: str, text: str) -> Chunk:
    digest = hashlib.sha256(f"{source['id']}|{citation}|{text}".encode()).hexdigest()[:12]
    return Chunk(
        chunk_id=f"{source['id']}:{digest}",
        source_id=source["id"],
        regime=source["regime"],
        kind=source["kind"],
        citation=citation,
        heading=heading,
        text=text,
        url=public_url(source["ecfr"]),
        as_of=meta["as_of"],
        retrieved_at=meta["retrieved_at"],
    )


def build(refresh: bool = False) -> dict:
    cfg = yaml.safe_load((CORPUS / "sources.yaml").read_text(encoding="utf-8"))
    as_of = cfg["as_of"]
    (CORPUS / "raw").mkdir(parents=True, exist_ok=True)
    (CORPUS / "processed").mkdir(parents=True, exist_ok=True)
    chunks: list[Chunk] = []
    per_source: dict[str, dict] = {}
    for src in cfg["sources"]:
        if src.get("status") != "primary":
            continue  # provenance gate: secondary sources are never indexed
        path = fetch(src, as_of, refresh)
        raw = path.read_bytes()
        meta = {
            "as_of": as_of,
            "retrieved_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat(),
        }
        root = ET.fromstring(raw)
        made = (
            chunk_interpretations(src, root, meta)
            if src["kind"] == "interpretation"
            else chunk_section(src, root, meta)
        )
        chunks.extend(made)
        per_source[src["id"]] = {"sha256": hashlib.sha256(raw).hexdigest(), "chunks": len(made)}

    lines = [json.dumps(asdict(c), ensure_ascii=False) for c in chunks]
    (CORPUS / "processed" / "chunks.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    version = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:12]
    manifest = {"corpus_version": version, "as_of": as_of, "chunks": len(chunks), "sources": per_source}
    (CORPUS / "processed" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download from eCFR")
    print(json.dumps(build(ap.parse_args().refresh), indent=2))


if __name__ == "__main__":
    main()

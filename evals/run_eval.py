"""Run a system over the golden set, score it, and write a run file.

  python -m evals.run_eval --system baseline --suite full
  python -m evals.run_eval --system agent --suite smoke --judge     (adds DeepEval judge metrics)

Run files land in evals/runs/<system>-<suite>-<git sha or timestamp>.json and are what the CI gate compares
against evals/baseline.json.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import time
from datetime import UTC, date, datetime
from pathlib import Path

from app.config import get_settings
from app.schemas import AssistantReply
from evals.scorers.deterministic import score

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evals" / "datasets" / "golden.jsonl"
HELDOUT = ROOT / "evals" / "datasets" / "heldout.jsonl"
RUNS = ROOT / "evals" / "runs"

# Smoke suite: at least one case per category and behavior; small enough for every pull request.
SMOKE = ["U01", "U02", "U03", "U09", "M01", "M02", "M04", "S01", "S02", "S04", "A01", "A03", "P01", "P03", "P06"]


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def load_cases(suite: str, ids: list[str] | None = None) -> list[dict]:
    path = HELDOUT if suite == "heldout" else GOLDEN
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if ids:
        return [c for c in cases if c["id"] in ids]
    return [c for c in cases if c["id"] in SMOKE] if suite == "smoke" else cases


def run_system(system: str, case: dict) -> AssistantReply:
    today = date.fromisoformat(case["today"])
    if system == "baseline":
        from app.rag.baseline import answer

        return answer(case["turns"][0], today=today)
    from app.agent.graph import run_turns

    return run_turns(case["turns"], today=today)


def aggregate(rows: list[dict]) -> dict[str, float]:
    metrics: dict[str, list[float]] = {}
    for row in rows:
        for k, v in row["scores"].items():
            if v is not None:
                metrics.setdefault(k, []).append(v)
    out = {k: round(statistics.mean(v), 4) for k, v in metrics.items()}
    out["error_rate"] = round(sum(r["error"] is not None for r in rows) / len(rows), 4)
    lat = [r["latency_s"] for r in rows if r["error"] is None]
    out["latency_p50_s"] = round(statistics.median(lat), 2) if lat else 0.0
    out["latency_p95_s"] = round(sorted(lat)[max(0, math.ceil(len(lat) * 0.95) - 1)], 2) if lat else 0.0  # nearest rank
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["baseline", "agent"], default="agent")
    ap.add_argument("--suite", choices=["smoke", "full", "heldout"], default="smoke")
    ap.add_argument("--ids", nargs="*", help="run only these case ids")
    ap.add_argument("--judge", action="store_true", help="also run DeepEval judge metrics")
    ap.add_argument("--out", type=Path, help="explicit run file path")
    args = ap.parse_args()

    s = get_settings()
    cases = load_cases(args.suite, args.ids)
    rows = []
    for i, case in enumerate(cases, 1):
        start = time.perf_counter()
        try:
            reply = run_system(args.system, case)
            err = None
        except Exception as e:  # a crash counts against the system, it doesn't abort the run
            reply, err = AssistantReply(reply=""), f"{type(e).__name__}: {e}"
        latency = time.perf_counter() - start
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "behavior": case["behavior"],
                "reply": reply.model_dump(mode="json"),
                "scores": score(case, reply),
                "latency_s": round(latency, 2),
                "error": err,
            }
        )
        print(f"[{i}/{len(cases)}] {case['id']} {latency:5.1f}s {'ERROR ' + err if err else ''}", flush=True)

    if args.judge:
        from evals.scorers.judge import judge_rows

        judge_rows(cases, rows)

    summary = aggregate(rows)
    run = {
        "system": args.system,
        "suite": args.suite,
        "git_sha": git_sha(),
        "created_at": datetime.now(UTC).isoformat(),
        "model": s.llm_model,
        "llm_base_url": s.llm_base_url,
        "corpus_version": rows[0]["reply"].get("corpus_version") if rows else "",
        "n_cases": len(rows),
        "metrics": summary,
        "cases": rows,
    }
    RUNS.mkdir(parents=True, exist_ok=True)
    out = args.out or RUNS / f"{args.system}-{args.suite}-{run['git_sha']}.json"
    out.write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"run file: {out}")


if __name__ == "__main__":
    main()

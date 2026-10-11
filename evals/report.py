"""Build a Markdown comparison table from run files (numbers come straight from the runs).

python -m evals.report evals/runs/baseline-full-*.json evals/runs/agent-full-v2.json ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ORDER = [
    "deadline_recall",
    "no_wrong_dates",
    "must_cite_recall",
    "citation_validity",
    "handoff_when_needed",
    "asks_for_missing",
    "flags_unsettled",
    "declines_out_of_scope",
    "no_outcome_promise",
    "pii_not_echoed",
    "first_draft_passed",
    "used_safe_fallback",
    "faithfulness",
    "answer_relevancy",
    "policy_compliance",
    "error_rate",
    "latency_p50_s",
    "latency_p95_s",
]


def label(run: dict, path: Path) -> str:
    return f"{run['system']} / {run['suite']}<br><sub>{path.stem}</sub>"


def table(paths: list[Path]) -> str:
    runs = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in paths]
    names = [m for m in ORDER if any(m in r["metrics"] for _, r in runs)]
    lines = ["| metric | " + " | ".join(label(r, p) for p, r in runs) + " |", "|---|" + "---|" * len(runs)]
    for m in names:
        cells = []
        for _, r in runs:
            v = r["metrics"].get(m)
            cells.append("" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v)))
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines.append("| cases | " + " | ".join(str(r["n_cases"]) for _, r in runs) + " |")
    lines.append("| model | " + " | ".join(r["model"] for _, r in runs) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(table([Path(p) for p in sys.argv[1:]]))

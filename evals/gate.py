"""Release gate: compare a run file against absolute floors and the committed baseline.

  python -m evals.gate evals/runs/agent-smoke-abc123.json
Exit code 0 = pass, 1 = fail. Prints a Markdown table (CI posts it as the job summary).

Rules per metric (evals/thresholds.yaml):
  min:      the metric must be >= this value
  max:      the metric must be <= this value
  max_drop: the metric may not fall more than this below evals/baseline.json (same suite)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
THRESHOLDS = ROOT / "thresholds.yaml"
BASELINE = ROOT / "baseline.json"


def _is_local(run: dict) -> bool:
    url = run.get("llm_base_url", "")
    return "localhost" in url or "127.0.0.1" in url


def evaluate(run: dict, thresholds: dict, baseline: dict | None) -> tuple[bool, list[list[str]]]:
    rows, ok = [], True
    base_metrics = (baseline or {}).get(run["suite"], {})
    for name, rule in thresholds["metrics"].items():
        value = run["metrics"].get(name)
        if rule.get("hosted_only") and _is_local(run):
            rows.append(
                [
                    name,
                    "n/a" if value is None else f"{value:.3f}",
                    "",
                    json.dumps(rule),
                    "skipped (local CPU model; latency is gated on the hosted model only)",
                ]
            )
            continue
        if value is None:
            rows.append([name, "n/a", "", "", "skipped (no applicable cases)"])
            continue
        problems = []
        if "min" in rule and value < rule["min"]:
            problems.append(f"< min {rule['min']}")
        if "max" in rule and value > rule["max"]:
            problems.append(f"> max {rule['max']}")
        base = base_metrics.get(name)
        if base is not None and "max_drop" in rule and value < base - rule["max_drop"]:
            problems.append(f"dropped {base - value:.3f} vs baseline (allowed {rule['max_drop']})")
        ok &= not problems
        rows.append(
            [
                name,
                f"{value:.3f}",
                "" if base is None else f"{base:.3f}",
                json.dumps(rule),
                "FAIL: " + "; ".join(problems) if problems else "pass",
            ]
        )
    return ok, rows


def main() -> None:
    run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None
    ok, rows = evaluate(run, thresholds, baseline)
    print(
        f"### Eval gate: {'PASS' if ok else 'FAIL'}  ({run['system']}, suite={run['suite']}, "
        f"{run['n_cases']} cases, model={run['model']}, sha={run['git_sha']})\n"
    )
    print("| metric | value | baseline | rule | result |\n|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

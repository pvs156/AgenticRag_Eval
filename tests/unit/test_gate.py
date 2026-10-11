from evals.gate import evaluate

TH = {
    "metrics": {
        "deadline_recall": {"min": 0.9, "max_drop": 0.05},
        "error_rate": {"max": 0.0},
        "faithfulness": {"min": 0.7},
    }
}


def run(**metrics):
    return {"suite": "smoke", "metrics": metrics}


def test_pass():
    ok, _ = evaluate(run(deadline_recall=0.95, error_rate=0.0), TH, {"smoke": {"deadline_recall": 0.96}})
    assert ok


def test_absolute_floor_fails():
    ok, rows = evaluate(run(deadline_recall=0.85, error_rate=0.0), TH, None)
    assert not ok and rows[0][4].startswith("FAIL")


def test_regression_vs_baseline_fails_even_above_floor():
    ok, rows = evaluate(run(deadline_recall=0.91, error_rate=0.0), TH, {"smoke": {"deadline_recall": 1.0}})
    assert not ok and "dropped" in rows[0][4]


def test_missing_metric_is_skipped_not_failed():
    ok, rows = evaluate(run(deadline_recall=1.0, error_rate=0.0), TH, None)
    assert ok and rows[2][4].startswith("skipped")


def test_latency_rule_skipped_for_local_model_only():
    th = {"metrics": {"latency_p95_s": {"max": 60, "hosted_only": True}}}
    local = {"suite": "smoke", "llm_base_url": "http://localhost:11434/v1", "metrics": {"latency_p95_s": 117.0}}
    hosted = {**local, "llm_base_url": "https://api.groq.com/openai/v1"}
    assert evaluate(local, th, None)[0] is True
    assert evaluate(hosted, th, None)[0] is False

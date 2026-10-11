"""Prometheus metrics exposed at /metrics and scraped by Prometheus; Grafana dashboards read these."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("assistant_requests_total", "Chat turns handled", ["claim_type", "outcome"])
ERRORS = Counter("assistant_errors_total", "Unhandled errors", ["stage"])
LATENCY = Histogram(
    "assistant_turn_latency_seconds",
    "End-to-end latency of a chat turn",
    buckets=(0.5, 1, 2, 4, 8, 15, 30, 60, 120),
)
NODE_LATENCY = Histogram(
    "assistant_node_latency_seconds",
    "Latency per agent node",
    ["node"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30),
)
RETRIES = Counter("assistant_retries_total", "Self-healing retries", ["cause"])
ABSTAINS = Counter("assistant_abstain_total", "Turns that ended in abstention", ["reason"])
HANDOFFS = Counter("assistant_handoff_total", "Turns that offered a human handoff", ["reason"])
GUARDRAIL = Counter("assistant_guardrail_events_total", "Guardrail interventions", ["kind"])
LLM_TOKENS = Counter("llm_tokens_total", "LLM tokens", ["tier", "direction"])
LLM_COST = Counter("llm_cost_usd_total", "LLM spend in USD", ["tier"])
LLM_LATENCY = Histogram(
    "llm_call_latency_seconds", "LLM call latency", ["tier"], buckets=(0.25, 0.5, 1, 2, 4, 8, 15, 30, 60, 120)
)
ONLINE_SCORE = Histogram(
    "assistant_online_score",
    "Sampled online evaluation scores (0-1)",
    ["metric"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
FEEDBACK = Counter("assistant_feedback_total", "User feedback", ["rating"])
JUDGE_ERRORS = Counter("judge_errors_total", "Online judge failures")
CORPUS_AGE_DAYS = Gauge("corpus_age_days", "Days since the regulation corpus as-of date")

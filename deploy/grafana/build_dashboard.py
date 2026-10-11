"""Generate the Grafana dashboard JSON (kept as code so panels are reviewable in diffs).

python deploy/grafana/build_dashboard.py
"""

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
panels: list[dict] = []
_id = 0


def _next_id() -> int:
    global _id
    _id += 1
    return _id


def stat(title, expr, x, unit="none", thresholds=None, decimals=2, w=4):
    panels.append(
        {
            "id": _next_id(),
            "type": "stat",
            "title": title,
            "datasource": DS,
            "gridPos": {"h": 4, "w": w, "x": x, "y": 0},
            "targets": [{"expr": expr, "refId": "A", "datasource": DS}],
            "fieldConfig": {
                "defaults": {
                    "unit": unit,
                    "decimals": decimals,
                    "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "green", "value": None}]},
                },
                "overrides": [],
            },
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "area"},
        }
    )


def series(title, targets, x, y, w=12, h=8, unit="none"):
    panels.append(
        {
            "id": _next_id(),
            "type": "timeseries",
            "title": title,
            "datasource": DS,
            "gridPos": {"h": h, "w": w, "x": x, "y": y},
            "targets": [
                {"expr": e, "legendFormat": leg, "refId": chr(65 + i), "datasource": DS}
                for i, (e, leg) in enumerate(targets)
            ],
            "fieldConfig": {"defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 8}}, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
        }
    )


def row(title, y):
    panels.append(
        {
            "id": _next_id(),
            "type": "row",
            "title": title,
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
            "panels": [],
        }
    )


RED = [{"color": "green", "value": None}, {"color": "orange", "value": 0.05}, {"color": "red", "value": 0.15}]
REQ = "clamp_min(sum(rate(assistant_requests_total[$__rate_interval])), 1e-9)"

stat("Turns / min", "sum(rate(assistant_requests_total[5m])) * 60", 0, decimals=1)
stat(
    "Error rate",
    "sum(rate(assistant_errors_total[15m])) / clamp_min(sum(rate(assistant_requests_total[15m])), 1e-9)",
    4,
    "percentunit",
    RED,
)
stat(
    "p95 latency",
    "histogram_quantile(0.95, sum by (le) (rate(assistant_turn_latency_seconds_bucket[15m])))",
    8,
    "s",
    [{"color": "green", "value": None}, {"color": "orange", "value": 10}, {"color": "red", "value": 20}],
)
stat(
    "Handoff rate",
    "sum(rate(assistant_handoff_total[1h])) / clamp_min(sum(rate(assistant_requests_total[1h])), 1e-9)",
    12,
    "percentunit",
)
stat(
    "Groundedness (sampled, 6h)",
    'sum(rate(assistant_online_score_sum{metric="groundedness"}[6h])) / '
    'clamp_min(sum(rate(assistant_online_score_count{metric="groundedness"}[6h])), 1e-9)',
    16,
    "percentunit",
    [{"color": "red", "value": None}, {"color": "orange", "value": 0.7}, {"color": "green", "value": 0.85}],
)
stat("LLM spend (24h)", "sum(increase(llm_cost_usd_total[24h]))", 20, "currencyUSD", decimals=3)

row("Agent behaviour", 4)
series(
    "Turns by outcome",
    [("sum by (outcome) (rate(assistant_requests_total[$__rate_interval])) * 60", "{{outcome}}")],
    0,
    5,
    unit="short",
)
series(
    "Turns by claim type",
    [("sum by (claim_type) (rate(assistant_requests_total[$__rate_interval])) * 60", "{{claim_type}}")],
    12,
    5,
    unit="short",
)
series(
    "Self-healing retries by cause / turn",
    [(f"sum by (cause) (rate(assistant_retries_total[$__rate_interval])) / {REQ}", "{{cause}}")],
    0,
    13,
    unit="percentunit",
)
series(
    "Handoffs and abstentions / turn",
    [
        (f"sum by (reason) (rate(assistant_handoff_total[$__rate_interval])) / {REQ}", "handoff: {{reason}}"),
        (f"sum by (reason) (rate(assistant_abstain_total[$__rate_interval])) / {REQ}", "abstain: {{reason}}"),
    ],
    12,
    13,
    unit="percentunit",
)

row("Quality (online evaluation)", 21)
series(
    "Online scores (rolling mean)",
    [
        (
            "sum by (metric) (rate(assistant_online_score_sum[1h])) / clamp_min(sum by (metric) "
            "(rate(assistant_online_score_count[1h])), 1e-9)",
            "{{metric}}",
        ),
    ],
    0,
    22,
    unit="percentunit",
)
series(
    "Guardrail events",
    [("sum by (kind) (increase(assistant_guardrail_events_total[$__rate_interval]))", "{{kind}}")],
    12,
    22,
    unit="short",
)
series(
    "User feedback",
    [("sum by (rating) (increase(assistant_feedback_total[$__rate_interval]))", "{{rating}}")],
    0,
    30,
    unit="short",
)
series("Judge errors", [("sum(increase(judge_errors_total[$__rate_interval]))", "judge errors")], 12, 30, unit="short")

row("Latency and cost", 38)
series(
    "Turn latency",
    [
        ("histogram_quantile(0.5, sum by (le) (rate(assistant_turn_latency_seconds_bucket[$__rate_interval])))", "p50"),
        (
            "histogram_quantile(0.95, sum by (le) (rate(assistant_turn_latency_seconds_bucket[$__rate_interval])))",
            "p95",
        ),
    ],
    0,
    39,
    unit="s",
)
series(
    "p95 latency by agent node",
    [
        (
            "histogram_quantile(0.95, sum by (le, node) "
            "(rate(assistant_node_latency_seconds_bucket[$__rate_interval])))",
            "{{node}}",
        ),
    ],
    12,
    39,
    unit="s",
)
series(
    "LLM tokens / min",
    [("sum by (tier, direction) (rate(llm_tokens_total[$__rate_interval])) * 60", "{{tier}} {{direction}}")],
    0,
    47,
    unit="short",
)
series("LLM spend (cumulative)", [("sum by (tier) (llm_cost_usd_total)", "{{tier}}")], 12, 47, unit="currencyUSD")

row("Host", 55)
series(
    "CPU busy",
    [('1 - avg(rate(node_cpu_seconds_total{mode="idle"}[$__rate_interval]))', "cpu")],
    0,
    56,
    w=8,
    unit="percentunit",
)
series(
    "Memory used",
    [("1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes", "memory")],
    8,
    56,
    w=8,
    unit="percentunit",
)
series(
    "Disk free",
    [('node_filesystem_avail_bytes{mountpoint="/host"} / node_filesystem_size_bytes{mountpoint="/host"}', "disk free")],
    16,
    56,
    w=8,
    unit="percentunit",
)

dashboard = {
    "uid": "dispute-assistant",
    "title": "Dispute Assistant: service, quality, cost",
    "schemaVersion": 39,
    "version": 1,
    "editable": True,
    "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"},
    "tags": ["llm", "agent", "evaluation"],
    "panels": panels,
    "templating": {"list": []},
    "annotations": {"list": []},
}
out = Path(__file__).parent / "dashboards" / "assistant.json"
out.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
print(f"wrote {out} with {len(panels)} panels")

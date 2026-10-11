"""Pull the real complaint sub-issue distribution that the golden set is modelled on.

The CFPB public API (checked 2026-10-09) returns structured fields but not narrative text, so test cases
are written by hand to mirror these real sub-issues rather than copied from complaints.
"""

import json
from datetime import date
from pathlib import Path

import httpx

API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
SINCE = "2025-10-01"
WANTED = {
    "Credit card": [
        "Problem with a purchase shown on your statement",
        "Problem with a company's investigation into an existing problem",
    ],
    "Checking or savings account": [
        "Managing an account",
        "Problem with a lender or other company charging your account",
    ],
    "Money transfer, virtual currency, or money service": [
        "Fraud or scam",
        "Unauthorized transactions or other transaction problem",
    ],
}

out = {"source": API, "date_received_min": SINCE, "pulled_on": date.today().isoformat(), "products": {}}
for product, issues in WANTED.items():
    r = httpx.get(API, params={"size": 0, "product": product, "date_received_min": SINCE}, timeout=60)
    r.raise_for_status()
    buckets = r.json()["aggregations"]["issue"]["issue"]["buckets"]
    out["products"][product] = {
        b["key"]: {
            "count": b["doc_count"],
            "sub_issues": {s["key"]: s["doc_count"] for s in b["sub_issue.raw"]["buckets"]},
        }
        for b in buckets
        if b["key"] in issues
    }

path = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "cfpb_taxonomy.json"
path.write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))

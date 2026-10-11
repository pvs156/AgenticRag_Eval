"""Date mentions in free text (used by the verifier and by eval scorers)."""

from __future__ import annotations

import re
from datetime import date

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})\b"
    r"|\b(" + "|".join(m[:3] for m in MONTHS) + r")[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
    r"|\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
    re.I,
)


def dates_in(text: str) -> set[date]:
    out: set[date] = set()
    for m in _DATE_RE.finditer(text):
        try:
            if m.group(1):
                out.add(date.fromisoformat(m.group(1)))
            elif m.group(2):
                month = [x[:3].lower() for x in MONTHS].index(m.group(2)[:3].lower()) + 1
                out.add(date(int(m.group(4)), month, int(m.group(3))))
            else:
                out.add(date(int(m.group(7)), int(m.group(5)), int(m.group(6))))
        except ValueError:
            continue
    return out

"""PII redaction applied to user input before it is logged, traced, stored or sent to an LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_ACCOUNT = re.compile(r"\b(account|acct|routing)(\s*(number|no\.?|#))?\s*[:#]?\s*(\d[\d -]{5,}\d)", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")


@dataclass
class Redacted:
    text: str
    kinds: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.kinds)


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def redact(text: str) -> Redacted:
    kinds: list[str] = []

    def card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            kinds.append("card_number")
            return f"[CARD ••••{digits[-4:]}]"
        return m.group(0)

    out = _CARD.sub(card, text)
    if _SSN.search(out):
        kinds.append("ssn")
        out = _SSN.sub("[SSN]", out)
    if _ACCOUNT.search(out):
        kinds.append("account_number")
        out = _ACCOUNT.sub(lambda m: f"{m.group(1)} [NUMBER]", out)
    if _EMAIL.search(out):
        kinds.append("email")
        out = _EMAIL.sub("[EMAIL]", out)
    if _PHONE.search(out):
        kinds.append("phone")
        out = _PHONE.sub("[PHONE]", out)
    return Redacted(out, kinds)

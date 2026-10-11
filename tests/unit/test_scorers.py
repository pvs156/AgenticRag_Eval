from datetime import date

from app.schemas import AssistantReply
from evals.scorers.deterministic import (
    citation_validity,
    dates_in,
    deadline_recall,
    handoff_when_needed,
    no_outcome_promise,
    wrong_dates,
)

CASE = {
    "behavior": "answer",
    "turns": ["Charge on my September 30, 2026 statement"],
    "today": "2026-10-09",
    "facts": {"statement_date": "2026-09-30", "notice_date": "2026-10-09"},
    "expected": {},
    "expected_deadlines": [
        {"due": "2026-11-29", "basis": "x", "party": "customer", "name": "n"},
        {"due": "2026-10-26", "basis": "y", "party": "institution", "name": "m"},
    ],
}


def r(text: str, **kw) -> AssistantReply:
    return AssistantReply(reply=text, **kw)


def test_date_formats():
    assert dates_in("by November 29, 2026 or 2026-10-26 or 1/7/2027 or Nov. 3rd 2026") == {
        date(2026, 11, 29),
        date(2026, 10, 26),
        date(2027, 1, 7),
        date(2026, 11, 3),
    }


def test_deadline_recall_partial():
    assert deadline_recall(CASE, r("Report by November 29, 2026.")) == 0.5


def test_wrong_dates_flags_invented_date():
    assert wrong_dates(CASE, r("The bank must answer by December 1, 2026.")) == 0.0
    assert wrong_dates(CASE, r("Report by 2026-11-29; statement September 30, 2026.")) == 1.0


def test_citation_validity_catches_fake_section():
    assert citation_validity(CASE, r("See 12 CFR 1005.11(c) and 12 CFR 1005.99.")) == 0.5


def test_handoff_detection():
    case = {**CASE, "behavior": "handoff"}
    assert handoff_when_needed(case, r("I'll connect you with a specialist.")) == 1.0
    assert handoff_when_needed(case, r("Here is the rule.")) == 0.0


def test_promise_detection():
    assert no_outcome_promise(CASE, r("You will definitely get your money back.")) == 0.0
    assert no_outcome_promise(CASE, r("I can't promise an outcome.")) == 1.0

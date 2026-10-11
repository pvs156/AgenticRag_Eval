"""Deterministic extractor on sentences written for these tests (not taken from the golden or held-out sets)."""

from datetime import date

import pytest

from app.agent.heuristics import extract_heuristics as h

TODAY = date(2026, 10, 9)


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "A $40 coffee shop charge on my debit card wasn't me",
            {"intent": "dispute", "claim_type": "unauthorized", "account_type": "debit", "channel": "pos"},
        ),
        (
            "My Mastercard credit card shows a purchase I don't recognize",
            {"claim_type": "unauthorized", "account_type": "credit"},
        ),
        (
            "The blender I ordered with my credit card never arrived",
            {"claim_type": "merchant", "goods_accepted": False},
        ),
        ("I was double-charged at the bakery on my debit card", {"claim_type": "merchant", "wrong_amount": True}),
        (
            "A guy posing as tech support got me to send $500 by Zelle",
            {"intent": "scam", "account_type": "debit", "channel": "transfer", "customer_initiated": True},
        ),
        (
            "My AI shopping agent bought three toasters on my credit card",
            {"intent": "agent_purchase", "account_type": "credit"},
        ),
        ("Should I buy bitcoin with my refund?", {"intent": "out_of_scope"}),
        ("How do I raise my credit limit?", {"intent": "out_of_scope"}),
        ("I live in Australia, do your rules apply to me?", {"non_us": True}),
        ("Someone used my prepaid card", {"account_type": "prepaid"}),
    ],
)
def test_classification(text, expected):
    got = h(text, TODAY)
    for k, v in expected.items():
        assert got.get(k) == v, (k, got)


def test_dates_are_assigned_by_context():
    got = h("My bill dated Sept 12 showed it; my card was stolen on October 3, and the charge was 10/1.", TODAY)
    assert got["statement_date"] == date(2026, 9, 12)
    assert got["learned_of_loss_date"] == date(2026, 10, 3)
    assert got["transaction_date"] == date(2026, 10, 1)
    assert got["access_device_lost_or_stolen"] is True


def test_month_without_year_in_the_future_means_last_year():
    assert h("statement from December 20", date(2026, 1, 5))["statement_date"] == date(2025, 12, 20)


def test_yesterday_loss():
    got = h("My wallet was stolen yesterday with my debit card in it", TODAY)
    assert got["learned_of_loss_date"] == date(2026, 10, 8)


def test_credentials_given_to_fraudster():
    got = h("I gave the caller the code from my text and then $300 left my checking account", TODAY)
    assert got["credentials_obtained_by_fraud"] is True and got["customer_initiated"] is False


def test_ambiguous_card_left_for_llm():
    got = h("There's a charge on my card I don't recognize", TODAY)
    assert "account_type" not in got  # "card" alone is ambiguous


def test_amount_and_phone_notice():
    got = h("I called the bank about the $1,234.56 charge", TODAY)
    assert got["amount"] == 1234.56 and got["notice_in_writing"] is False


def test_foreign_merchant_is_not_non_us_customer():
    assert "non_us" not in h("A shop in Spain charged my debit card and I wasn't there", TODAY)


def test_notice_date_from_earlier_written_dispute():
    got = h("On August 3 I sent my card issuer a written dispute about a missing order on my July 20 statement.", TODAY)
    assert got["notice_date"] == date(2026, 8, 3) and got["statement_date"] == date(2026, 7, 20)


def test_transfer_out_implies_bank_account():
    assert h("Someone transferred $900 out and I never approved it", TODAY)["account_type"] == "debit"
    assert "account_type" not in h("A transfer showed up on my credit card and also my checking", TODAY)


def test_already_sent_is_customer_initiated():
    assert h("A caller pressured me and I already sent $200", TODAY)["customer_initiated"] is True

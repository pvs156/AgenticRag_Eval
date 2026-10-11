from datetime import date

import pytest

from app.rules.engine import assess
from app.rules.models import AccountType, Channel, ClaimFacts, ClaimType, Regime

NOTICE = date(2026, 10, 9)  # Friday; Monday 10-12 is a Fed holiday
STATEMENT = date(2026, 9, 30)


def due(a, basis_prefix: str, party: str | None = None):
    for d in a.deadlines:
        if d.basis.startswith(basis_prefix) and (party is None or d.party == party):
            return d.due
    raise AssertionError(f"no deadline {basis_prefix}: {[d.basis for d in a.deadlines]}")


def facts(**kw):
    base = dict(notice_date=NOTICE, statement_date=STATEMENT)
    base.update(kw)
    return ClaimFacts(**base)


# ---------------------------------------------------------------- Reg E unauthorized


def test_debit_unauthorized_pos_deadlines():
    a = assess(facts(claim_type=ClaimType.UNAUTHORIZED, account_type=AccountType.DEBIT, channel=Channel.POS))
    assert a.regime == Regime.REG_E and a.covered_as_error is True
    assert due(a, "12 CFR 1005.11(b)(1)") == date(2026, 11, 29)  # statement + 60 days
    assert due(a, "12 CFR 1005.11(c)(1)") == date(2026, 10, 26)  # 10 business days
    assert due(a, "12 CFR 1005.11(c)(2)") == date(2027, 1, 7)  # POS -> 90 calendar days
    assert not a.needs_human


def test_debit_unauthorized_atm_uses_45_days():
    a = assess(facts(claim_type=ClaimType.UNAUTHORIZED, account_type=AccountType.DEBIT, channel=Channel.ATM))
    assert due(a, "12 CFR 1005.11(c)(2)") == date(2026, 11, 23)  # 45 days


def test_foreign_transfer_uses_90_days():
    a = assess(facts(claim_type=ClaimType.UNAUTHORIZED, account_type=AccountType.DEBIT, channel=Channel.FOREIGN))
    assert due(a, "12 CFR 1005.11(c)(2)") == date(2027, 1, 7)


def test_new_account_extends_both_periods():
    a = assess(
        facts(
            claim_type=ClaimType.UNAUTHORIZED,
            account_type=AccountType.DEBIT,
            channel=Channel.TRANSFER,
            first_deposit_date=date(2026, 9, 20),
            transaction_date=date(2026, 10, 1),
        )
    )
    assert due(a, "12 CFR 1005.11(c)(1)") == date(2026, 11, 9)  # 20 business days
    assert due(a, "12 CFR 1005.11(c)(2)") == date(2027, 1, 7)  # 90 days


def test_new_account_needs_transaction_date():
    a = assess(
        facts(
            claim_type=ClaimType.UNAUTHORIZED,
            account_type=AccountType.DEBIT,
            channel=Channel.TRANSFER,
            first_deposit_date=date(2026, 9, 20),
        )
    )
    assert "transaction_date" in a.missing_facts


def test_lost_card_reported_in_time_caps_at_50():
    a = assess(
        facts(
            claim_type=ClaimType.UNAUTHORIZED,
            account_type=AccountType.DEBIT,
            channel=Channel.POS,
            access_device_lost_or_stolen=True,
            learned_of_loss_date=date(2026, 10, 8),
        )
    )
    assert due(a, "12 CFR 1005.6(b)(1)") == date(2026, 10, 13)
    assert any("$50" in n for n in a.liability_notes)


def test_lost_card_reported_late_up_to_500():
    a = assess(
        facts(
            claim_type=ClaimType.UNAUTHORIZED,
            account_type=AccountType.DEBIT,
            channel=Channel.POS,
            access_device_lost_or_stolen=True,
            learned_of_loss_date=date(2026, 9, 1),
        )
    )
    assert any("$500" in n for n in a.liability_notes)


def test_oral_notice_adds_written_confirmation_deadline():
    a = assess(
        facts(
            claim_type=ClaimType.UNAUTHORIZED,
            account_type=AccountType.DEBIT,
            channel=Channel.POS,
            notice_in_writing=False,
        )
    )
    assert due(a, "12 CFR 1005.11(b)(2)") == date(2026, 10, 26)


def test_missing_statement_date_is_reported():
    a = assess(
        ClaimFacts(
            claim_type=ClaimType.UNAUTHORIZED, account_type=AccountType.DEBIT, channel=Channel.POS, notice_date=NOTICE
        )
    )
    assert "statement_date" in a.missing_facts
    assert due(a, "12 CFR 1005.11(b)(1)") is None


# ---------------------------------------------------------------- Reg Z


def test_credit_unauthorized_deadlines_and_liability():
    a = assess(facts(claim_type=ClaimType.UNAUTHORIZED, account_type=AccountType.CREDIT))
    assert a.regime == Regime.REG_Z and a.covered_as_error is True
    assert due(a, "12 CFR 1026.13(b)(1)") == date(2026, 11, 29)
    assert due(a, "12 CFR 1026.13(c)(1)") == date(2026, 11, 8)
    assert due(a, "12 CFR 1026.13(c)(2)") == date(2027, 1, 7)
    assert any("$50" in n for n in a.liability_notes)


def test_credit_merchant_not_delivered_is_billing_error():
    a = assess(facts(claim_type=ClaimType.MERCHANT, account_type=AccountType.CREDIT, goods_accepted=False))
    assert a.covered_as_error is True and not a.needs_human


def test_credit_merchant_quality_dispute_routes_to_claims_and_defenses():
    a = assess(facts(claim_type=ClaimType.MERCHANT, account_type=AccountType.CREDIT, goods_accepted=True))
    assert a.covered_as_error is False and a.needs_human
    assert "12 CFR 1026.12(c)" in a.citations


def test_credit_merchant_unknown_acceptance_asks():
    a = assess(facts(claim_type=ClaimType.MERCHANT, account_type=AccountType.CREDIT))
    assert "goods_accepted" in a.missing_facts and a.covered_as_error is None


def test_debit_merchant_dispute_not_covered_by_reg_e():
    a = assess(facts(claim_type=ClaimType.MERCHANT, account_type=AccountType.DEBIT, channel=Channel.POS))
    assert a.regime == Regime.NOT_COVERED and a.needs_human and a.covered_as_error is False


# ---------------------------------------------------------------- scams


def test_scam_customer_initiated_debit_not_unauthorized():
    a = assess(
        facts(
            claim_type=ClaimType.SCAM, account_type=AccountType.DEBIT, channel=Channel.TRANSFER, customer_initiated=True
        )
    )
    assert a.covered_as_error is None and a.needs_human
    assert any("1005.2(m)" in r for r in a.reasons)


def test_scam_credentials_stolen_is_unauthorized():
    a = assess(
        facts(
            claim_type=ClaimType.SCAM,
            account_type=AccountType.DEBIT,
            channel=Channel.TRANSFER,
            customer_initiated=False,
            credentials_obtained_by_fraud=True,
        )
    )
    assert a.covered_as_error is True
    assert any("2(m)-3" in r for r in a.reasons)


def test_scam_unknown_facts_requests_them():
    a = assess(facts(claim_type=ClaimType.SCAM, account_type=AccountType.DEBIT, channel=Channel.TRANSFER))
    assert {"customer_initiated", "credentials_obtained_by_fraud"} <= set(a.missing_facts)


def test_scam_credit_card():
    a = assess(facts(claim_type=ClaimType.SCAM, account_type=AccountType.CREDIT, customer_initiated=True))
    assert a.regime == Regime.REG_Z and a.needs_human and a.covered_as_error is None


# ---------------------------------------------------------------- agent-initiated (unsettled)


@pytest.mark.parametrize("account", [AccountType.DEBIT, AccountType.CREDIT])
def test_agent_initiated_is_unsettled(account):
    a = assess(facts(claim_type=ClaimType.AGENT_INITIATED, account_type=account, channel=Channel.POS))
    assert a.unsettled and a.needs_human and a.covered_as_error is None
    assert a.deadlines, "customer still gets the notice deadline that preserves their rights"


def test_agent_credit_cites_designee():
    a = assess(facts(claim_type=ClaimType.AGENT_INITIATED, account_type=AccountType.CREDIT))
    assert any("designee" in r for r in a.reasons)


# ---------------------------------------------------------------- routing edge cases


def test_unknown_account_type_asks_first():
    a = assess(facts(claim_type=ClaimType.UNAUTHORIZED))
    assert a.regime == Regime.UNKNOWN and "account_type" in a.missing_facts and not a.deadlines


def test_prepaid_escalates():
    a = assess(facts(claim_type=ClaimType.UNAUTHORIZED, account_type=AccountType.PREPAID))
    assert a.needs_human


def test_unauthorized_but_customer_initiated_conflict_escalates():
    a = assess(
        facts(
            claim_type=ClaimType.UNAUTHORIZED,
            account_type=AccountType.DEBIT,
            channel=Channel.POS,
            customer_initiated=True,
        )
    )
    assert a.needs_human and a.covered_as_error is None


# ---------------------------------------------------------------- added in stage 2


def test_debit_wrong_amount_is_incorrect_transfer():
    a = assess(
        facts(claim_type=ClaimType.MERCHANT, account_type=AccountType.DEBIT, channel=Channel.POS, wrong_amount=True)
    )
    assert a.regime == Regime.REG_E and a.covered_as_error is True and not a.needs_human


def test_credit_wrong_amount_escalates():
    a = assess(facts(claim_type=ClaimType.MERCHANT, account_type=AccountType.CREDIT, wrong_amount=True))
    assert a.needs_human and a.covered_as_error is None


def test_late_customer_notice_is_flagged():
    a = assess(
        facts(claim_type=ClaimType.UNAUTHORIZED, account_type=AccountType.CREDIT, statement_date=date(2026, 6, 30))
    )
    assert a.needs_human and any("appears to have passed" in r for r in a.reasons)


def test_bank_missed_resolution_deadline_is_flagged():
    a = assess(
        facts(
            claim_type=ClaimType.MERCHANT,
            account_type=AccountType.CREDIT,
            goods_accepted=False,
            statement_date=date(2026, 5, 31),
            notice_date=date(2026, 6, 15),
        ),
        today=date(2026, 10, 9),
    )
    assert a.needs_human and any("institution's deadline" in r for r in a.reasons)


def test_scam_stolen_card_details_on_credit_is_unauthorized_use():
    a = assess(facts(claim_type=ClaimType.SCAM, account_type=AccountType.CREDIT, customer_initiated=False))
    assert a.covered_as_error is True and any("$50" in n for n in a.liability_notes)


def test_scam_credit_unknown_initiator_asks():
    a = assess(facts(claim_type=ClaimType.SCAM, account_type=AccountType.CREDIT))
    assert "customer_initiated" in a.missing_facts

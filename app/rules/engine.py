"""Deterministic regime routing, deadlines and liability notes.

Every rule here is traceable to the eCFR text in corpus/ (as of the date in corpus/sources.yaml).
The LLM never computes these values; it only explains them.
"""

from __future__ import annotations

from datetime import date, timedelta

from .calendar import BUSINESS_DAY_ASSUMPTION, add_business_days
from .models import AccountType, Assessment, Channel, ClaimFacts, ClaimType, Deadline, Regime

UNSETTLED_AGENT_NOTE = (
    "The indexed regulations do not address purchases made by AI agents. Whether an agent counts as a person "
    "the customer furnished the card to (Reg E) or one with authority to use the card (Reg Z) is unsettled."
)


# --------------------------------------------------------------------------- Regulation E


def _is_new_account(f: ClaimFacts) -> bool | None:
    """Transfer within 30 days after the first deposit (12 CFR 1005.11(c)(3))."""
    if f.first_deposit_date is None:
        return False
    if f.transaction_date is None:
        return None
    return f.transaction_date <= f.first_deposit_date + timedelta(days=30)


def reg_e_deadlines(f: ClaimFacts, a: Assessment) -> None:
    a.deadlines.append(
        Deadline(
            name="Customer reports the error to the bank",
            due=f.statement_date + timedelta(days=60) if f.statement_date else None,
            party="customer",
            basis="12 CFR 1005.11(b)(1)",
            note="60 days after the bank sent the first statement showing the error. Oral notice counts.",
        )
    )
    if f.statement_date is None:
        a.missing_facts.append("statement_date")
    if f.notice_in_writing is False:
        a.deadlines.append(
            Deadline(
                name="Written confirmation, if the bank requires it",
                due=add_business_days(f.notice_date, 10),
                party="customer",
                basis="12 CFR 1005.11(b)(2)",
                note="10 business days after an oral notice. " + BUSINESS_DAY_ASSUMPTION,
            )
        )

    new_account = _is_new_account(f)
    if new_account is None:
        a.missing_facts.append("transaction_date")
    initial_bd = 20 if new_account else 10
    extended = 90 if (new_account or f.channel in (Channel.POS, Channel.FOREIGN)) else 45
    if f.channel == Channel.UNKNOWN and not new_account:
        a.missing_facts.append("channel")

    a.deadlines.append(
        Deadline(
            name="Bank determines whether an error occurred, or provisionally credits the account",
            due=add_business_days(f.notice_date, initial_bd),
            party="institution",
            basis="12 CFR 1005.11(c)(1)-(2)" + (", (c)(3)(i)" if new_account else ""),
            note=f"{initial_bd} business days after receiving the notice. " + BUSINESS_DAY_ASSUMPTION,
        )
    )
    a.deadlines.append(
        Deadline(
            name="Bank completes the investigation (only if it provisionally credited)",
            due=f.notice_date + timedelta(days=extended),
            party="institution",
            basis="12 CFR 1005.11(c)(2)" + (", (c)(3)(ii)" if extended == 90 else ""),
            note=f"{extended} calendar days after receiving the notice"
            + (
                " (extended period for point-of-sale debit, foreign-initiated, or new-account transfers)."
                if extended == 90
                else "."
            )
            + " Results are reported within 3 business days after the investigation ends.",
        )
    )
    a.citations += ["12 CFR 1005.11(b)", "12 CFR 1005.11(c)"]


def reg_e_liability(f: ClaimFacts, a: Assessment) -> None:
    if f.access_device_lost_or_stolen:
        if f.learned_of_loss_date is None:
            a.missing_facts.append("learned_of_loss_date")
        else:
            cutoff = add_business_days(f.learned_of_loss_date, 2)
            a.deadlines.append(
                Deadline(
                    name="Report the lost or stolen card to keep liability at $50 or less",
                    due=cutoff,
                    party="customer",
                    basis="12 CFR 1005.6(b)(1)",
                    note="2 business days after learning of the loss or theft. " + BUSINESS_DAY_ASSUMPTION,
                    escalate_if_missed=False,
                )
            )
            if f.notice_date <= cutoff:
                a.liability_notes.append(
                    "Reported within 2 business days of learning of the loss: liability is capped at the "
                    "lesser of $50 or the unauthorized transfers before notice (12 CFR 1005.6(b)(1))."
                )
            else:
                a.liability_notes.append(
                    "Reported after 2 business days: liability can be up to $500, under the conditions in "
                    "12 CFR 1005.6(b)(2)."
                )
    a.liability_notes.append(
        "Reporting within 60 days of the statement avoids liability for later unauthorized transfers "
        "(12 CFR 1005.6(b)(3)). Delays caused by extenuating circumstances extend these limits "
        "(12 CFR 1005.6(b)(4))."
    )
    a.citations += ["12 CFR 1005.6(b)"]


# --------------------------------------------------------------------------- Regulation Z


def reg_z_deadlines(f: ClaimFacts, a: Assessment) -> None:
    a.deadlines.append(
        Deadline(
            name="Customer sends a written billing error notice",
            due=f.statement_date + timedelta(days=60) if f.statement_date else None,
            party="customer",
            basis="12 CFR 1026.13(b)(1)",
            note="Must be written and reach the billing-error address on the statement within 60 days after "
            "the first statement showing the error was sent. A phone call alone does not trigger these rights.",
        )
    )
    if f.statement_date is None:
        a.missing_facts.append("statement_date")
    if f.notice_in_writing is False:
        a.reasons.append("Notice so far is not in writing; Reg Z billing-error rights need a written notice.")
    a.deadlines.append(
        Deadline(
            name="Card issuer acknowledges the notice in writing",
            due=f.notice_date + timedelta(days=30),
            party="institution",
            basis="12 CFR 1026.13(c)(1)",
            note="30 days after receiving the notice, unless the dispute is resolved first. "
            "Computed from the date given as the notice date.",
        )
    )
    a.deadlines.append(
        Deadline(
            name="Card issuer resolves the billing error",
            due=f.notice_date + timedelta(days=90),
            party="institution",
            basis="12 CFR 1026.13(c)(2)",
            note="Within 2 complete billing cycles and never later than 90 days; the date shown is the 90-day "
            "outer limit.",
        )
    )
    a.citations += ["12 CFR 1026.13(b)", "12 CFR 1026.13(c)"]


def reg_z_unauthorized_liability(a: Assessment) -> None:
    a.liability_notes.append(
        "Cardholder liability for unauthorized credit card use is at most the lesser of $50 or the amount "
        "charged before the issuer is notified (12 CFR 1026.12(b)(1)(ii)); lower limits set by state law or "
        "the card agreement take priority (12 CFR 1026.12(b)(4))."
    )
    a.citations += ["12 CFR 1026.12(b)"]


# --------------------------------------------------------------------------- routing


def _regime_for(account: AccountType) -> Regime:
    return {AccountType.DEBIT: Regime.REG_E, AccountType.CREDIT: Regime.REG_Z}.get(account, Regime.UNKNOWN)


def assess(f: ClaimFacts, today: date | None = None) -> Assessment:
    """Assess a claim. `today` (defaults to the notice date) is used to flag deadlines already passed."""
    a = _assess(f)
    _flag_passed_deadlines(f, a, today or f.notice_date)
    a.citations = list(dict.fromkeys(a.citations))
    a.missing_facts = list(dict.fromkeys(a.missing_facts))
    return a


def _flag_passed_deadlines(f: ClaimFacts, a: Assessment, today: date) -> None:
    for d in a.deadlines:
        if d.due is None or not d.escalate_if_missed:
            continue
        if d.party == "customer" and d.due < f.notice_date:
            a.needs_human = True
            a.reasons.append(
                f"The customer deadline '{d.name}' ({d.basis}) appears to have passed on {d.due.isoformat()}. "
                "Rights may be reduced; a specialist should review (Reg E allows extensions for extenuating "
                "circumstances, 12 CFR 1005.6(b)(4))."
            )
        elif d.party == "institution" and d.due < today:
            a.needs_human = True
            a.reasons.append(
                f"The institution's deadline '{d.name}' ({d.basis}) appears to have passed on "
                f"{d.due.isoformat()}. Escalate for review."
            )


def _assess(f: ClaimFacts) -> Assessment:
    a = Assessment(regime=_regime_for(f.account_type), covered_as_error=None)

    if f.account_type == AccountType.UNKNOWN:
        a.missing_facts.append("account_type")
        a.reasons.append("Need to know whether this was a debit/bank account or a credit card.")
        return a
    if f.account_type == AccountType.PREPAID:
        a.regime = Regime.REG_E
        a.needs_human = True
        a.reasons.append(
            "Prepaid accounts have their own rules in Regulation E (section 1005.18), which are not in the "
            "indexed sources."
        )
        return a

    handler = {
        ClaimType.UNAUTHORIZED: _unauthorized,
        ClaimType.MERCHANT: _merchant,
        ClaimType.SCAM: _scam,
        ClaimType.AGENT_INITIATED: _agent,
    }[f.claim_type]
    handler(f, a)
    return a


def _unauthorized(f: ClaimFacts, a: Assessment) -> None:
    if f.customer_initiated:
        a.needs_human = True
        a.reasons.append("Customer says they made the payment, which conflicts with an unauthorized claim.")
    if a.regime == Regime.REG_E:
        a.covered_as_error = None if f.customer_initiated else True
        a.citations += ["12 CFR 1005.2(m)", "12 CFR 1005.11(a)"]
        reg_e_deadlines(f, a)
        reg_e_liability(f, a)
    else:
        a.covered_as_error = None if f.customer_initiated else True
        a.citations += ["12 CFR 1026.13(a)"]
        reg_z_deadlines(f, a)
        reg_z_unauthorized_liability(a)


def _merchant(f: ClaimFacts, a: Assessment) -> None:
    if a.regime == Regime.REG_Z:
        a.citations += ["12 CFR 1026.13(a)", "12 CFR 1026.12(c)"]
        if f.wrong_amount:
            a.needs_human = True
            a.reasons.append(
                "Wrong or duplicate credit card amounts are usually handled as billing errors, but the indexed "
                "sources do not state which billing-error category applies; a specialist should confirm."
            )
            reg_z_deadlines(f, a)
            return
        if f.goods_accepted is None:
            a.missing_facts.append("goods_accepted")
        elif f.goods_accepted:
            a.covered_as_error = False
            a.needs_human = True
            a.reasons.append(
                "Quality disputes about goods the customer accepted are not billing errors "
                "(12 CFR Part 1026 Supp. I, comment 13(a)(3)-1.ii). The customer may still assert claims "
                "against the card issuer under 12 CFR 1026.12(c) if they tried to resolve it with the merchant "
                "and the purchase was over $50 and in their state or within 100 miles."
            )
        else:
            a.covered_as_error = True
        reg_z_deadlines(f, a)
    elif f.wrong_amount:
        # Wrong or duplicate amount on a debit payment is an "incorrect electronic fund transfer".
        a.covered_as_error = True
        a.citations += ["12 CFR 1005.11(a)"]
        a.reasons.append("A transfer for the wrong amount is an error under 12 CFR 1005.11(a)(1)(ii).")
        reg_e_deadlines(f, a)
    else:
        a.regime = Regime.NOT_COVERED
        a.covered_as_error = False
        a.needs_human = True
        a.citations += ["12 CFR 1005.11(a)"]
        a.reasons.append(
            "Reg E error resolution covers unauthorized or incorrect transfers, not disputes about goods or "
            "services from a payment the customer made. If the amount charged differs from what was agreed, "
            "that may be an incorrect transfer (12 CFR 1005.11(a)(1)(ii)). Card network chargeback rules and "
            "bank policy may also apply; they are not in the indexed sources."
        )


def _scam(f: ClaimFacts, a: Assessment) -> None:
    a.needs_human = True
    if a.regime == Regime.REG_E:
        a.citations += ["12 CFR 1005.2(m)"]
        if f.credentials_obtained_by_fraud and not f.customer_initiated:
            a.covered_as_error = True
            a.reasons.append(
                "A transfer made by someone who obtained the card or credentials from the customer through "
                "fraud is an unauthorized transfer (12 CFR Part 1005 Supp. I, comment 2(m)-3)."
            )
            reg_e_deadlines(f, a)
            reg_e_liability(f, a)
        elif f.customer_initiated:
            a.covered_as_error = None
            a.reasons.append(
                "A transfer the customer made personally is generally not an 'unauthorized electronic fund "
                "transfer' (12 CFR 1005.2(m)). Whether any other protection or bank policy applies needs a "
                "specialist."
            )
            reg_e_deadlines(f, a)
        else:
            a.missing_facts += ["customer_initiated", "credentials_obtained_by_fraud"]
    elif f.customer_initiated is False:
        # Fraudster used stolen card details: unauthorized use, no authority (12 CFR 1026.12(b)(1)(i)).
        a.covered_as_error = True
        a.citations += ["12 CFR 1026.12(b)", "12 CFR 1026.13(a)"]
        a.reasons.append(
            "Charges made by someone else with stolen card details are unauthorized use (12 CFR 1026.12(b)(1)(i))."
        )
        reg_z_deadlines(f, a)
        reg_z_unauthorized_liability(a)
    elif f.customer_initiated:
        a.covered_as_error = None
        a.citations += ["12 CFR 1026.12(b)", "12 CFR 1026.13(a)"]
        a.reasons.append(
            "A credit card purchase the customer made is not 'unauthorized use' (12 CFR 1026.12(b)(1)(i)), but if "
            "the goods or services were not delivered as agreed it may be a billing error (12 CFR 1026.13(a)(3))."
        )
        reg_z_deadlines(f, a)
    else:
        a.missing_facts.append("customer_initiated")


def _agent(f: ClaimFacts, a: Assessment) -> None:
    a.unsettled = True
    a.needs_human = True
    a.covered_as_error = None
    a.reasons.append(UNSETTLED_AGENT_NOTE)
    if a.regime == Regime.REG_E:
        a.citations += ["12 CFR 1005.2(m)"]
        a.reasons.append(
            "Under Reg E, transfers by a person the customer furnished the access device to are not "
            "unauthorized unless the customer told the bank that person is no longer authorized "
            "(12 CFR 1005.2(m)(1)). Revoking the agent's access with the bank is a sensible first step."
        )
        reg_e_deadlines(f, a)
    else:
        a.citations += ["12 CFR 1026.12(b)", "12 CFR 1026.13(a)"]
        a.reasons.append(
            "Under Reg Z, unauthorized use excludes people with actual, implied or apparent authority "
            "(12 CFR 1026.12(b)(1)(i)), and billing errors include goods not accepted by, or not delivered as "
            "agreed to, the consumer's designee (12 CFR 1026.13(a)(3))."
        )
        reg_z_deadlines(f, a)

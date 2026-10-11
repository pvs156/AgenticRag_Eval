"""Deterministic first-pass extraction.

Unambiguous signals (card type, explicit dates and what they refer to, "AI agent", "scam", "never arrived",
"charged twice", out-of-scope topics) are read with patterns. They take precedence over the LLM, which fills only
what these patterns leave open. Small models misclassify these often; patterns don't, and they are testable.
Returns only the fields it detected.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

I = re.I  # noqa: E741

ADVICE_RE = re.compile(r"\b(invest|index funds?|stocks?|crypto|bitcoin|sue|suing|lawsuit|lawyer|attorney)\b", I)
OTHER_TOPIC_RE = re.compile(
    r"\b(mortgage|refinanc\w*|credit limit|interest rate|personal loan|car loan|credit score|account balance"
    r"|current balance|my balance|open an account|close my account)\b",
    I,
)
NON_US_RE = re.compile(
    r"\b(i'?m|i am|i live|i bank|we bank|living|based)\s+in\s+(the\s+)?(uk|u\.k\.|united kingdom|britain|england|"
    r"canada|australia|europe|eu|india|mexico|ireland)\b|\b(uk|u\.k\.|canada|canadian|australian|european|eu)('s)?\s+"
    r"(app\s+)?(scam\s+)?(reimbursement\s+)?(scheme|rules|law|regulations?)\b",
    I,
)
AGENT_RE = re.compile(
    r"\b(ai|a\.i\.)\s+(shopping\s+|budgeting\s+|personal\s+)?(agent|assistant|concierge|bot)\b"
    r"|\b(shopping|budgeting|purchasing)\s+(agent|assistant|bot)\b|\bmy\s+agent\b|\bai\s+bot\b",
    I,
)
SCAM_RE = re.compile(
    r"\b(scam\w*|tricked|conned|fraudster|pretend\w*|posing|impersonat\w*|fake|phishing|clicked (a|the) link"
    r"|dating app|romance|convinced me|claiming to be|told me to (send|move|transfer)|safe account|avoid arrest"
    r"|got me to)\b",
    I,
)
MERCHANT_RE = re.compile(
    r"(never (arrived|came|showed up|delivered)|not delivered|didn'?t (arrive|receive|get)|wasn'?t delivered"
    r"|refused (the )?delivery|returned (it|them|the)|cancel+ed|no refund|never refunded|won'?t refund"
    r"|refuses? (a |to )?refund|not what (they|was) promised|wasn'?t what they promised|damaged|defective|torn"
    r"|poor quality|runs badly|works (badly|poorly)|charged (me )?twice|two times|twice for|double[- ]?charged"
    r"|duplicate|wrong amount|instead of|overcharg\w*|tip from)",
    I,
)
UNAUTH_RE = re.compile(
    r"(didn'?t make|did not make|never made|never authori[sz]ed|not authori[sz]ed|unauthori[sz]ed|wasn'?t me"
    r"|not me\b|isn'?t mine|aren'?t mine|not mine|don'?t recogni[sz]e|do not recogni[sz]e|never (bought|used|been)"
    r"|someone (else )?(used|took|got|charged|withdrew|stole|ran up|sent)|stolen|got into my|hacked|mystery charge"
    r"|without (my )?permission|no idea who|didn'?t send it)",
    I,
)

CREDIT_RE = re.compile(
    r"\bcredit card\b|\b(visa|mastercard|discover)\s+credit\b|\bamex\b|\bamerican express\b|\bcard (bill|issuer)\b",
    I,
)
DEBIT_RE = re.compile(
    r"\b(debit|checking|savings|atm|bank account|banking app|bank'?s app|online banking|zelle|venmo|cash app"
    r"|payment app|person-to-person|bank transfer)\b",
    I,
)
# Money moved *out of* an account by transfer or withdrawal implies a deposit account, not a credit card.
DEBIT_IMPLIED_RE = re.compile(r"\b(transfer\w*|withdr[ae]w\w*|wired?)\b", I)
PREPAID_RE = re.compile(r"\bprepaid card\b", I)

ATM_RE = re.compile(r"\batm\b", I)
TRANSFER_RE = re.compile(
    r"\b(transfer\w*|zelle|venmo|cash app|payment app|person-to-person|p2p|sent \$|send \$|wire|ach)\b", I
)
POS_RE = re.compile(
    r"\b(store|shop|purchase|merchant|online|restaurant|gas station|pharmacy|grocery|hotel|bought|order\w*|bill)\b",
    I,
)

LOST_RE = re.compile(
    r"((lost|left) my (debit |credit )?(card|wallet)|(card|wallet|phone) (was|got|is) (lost|stolen|missing)"
    r"|stole my (card|wallet)|(card|wallet) stolen|wallet was stolen|card (was|went) missing|missing (card|wallet)"
    r"|my (debit |credit )?card was missing)",
    I,
)
SELF_INITIATED_STRONG_RE = re.compile(
    r"\b(myself|himself|herself|ourselves)\b|\bdid make the payment\b|\bi did it\b", I
)
SELF_INITIATED_RE = re.compile(
    r"\b(i|he|she|we) (already |just |then |also )?(sent|paid|transferred|moved|wired|did the transfer)\b"
    r"|convinced me to send|got me to send"
    r"|told me to (send|move|transfer) .{0,40}\bi did\b",
    I,
)
NOT_SELF_RE = re.compile(
    r"((didn'?t|did not|never) (make|send|authori[sz]e|approve)|without me doing|wasn'?t me|not me\b"
    r"|someone (else )?(used|took|sent|logged|charged|withdrew|ran up)|hacked|got into my|charges i didn'?t make"
    r"|they logged)",
    I,
)
CREDENTIALS_RE = re.compile(
    r"((read out|gave|shared|entered|typed|told them|provided).{0,50}(code|password|pin\b|login|card (number|details))"
    r"|(code|password|card number|card details).{0,40}(into|on) (a |the )?fake|clicked (a|the) link)",
    I,
)
NOT_ACCEPTED_RE = re.compile(
    r"(never (arrived|came|showed up|delivered)|not delivered|didn'?t (arrive|receive|get)|wasn'?t delivered"
    r"|refused (the )?delivery|returned (it|them|the)|cancel+ed|never refunded|nothing was (ever )?delivered"
    r"|no tickets)",
    I,
)
ACCEPTED_RE = re.compile(
    r"(\bkept it\b|\bi kept\b|i'?m using it|still using|arrived and i|runs badly|works (badly|poorly))", I
)
WRONG_AMOUNT_RE = re.compile(
    r"(charged (me )?twice|two times|twice for|double[- ]?charged|duplicate|wrong amount|instead of (the )?\$"
    r"|overcharg\w*|tip from)",
    I,
)
PHONE_NOTICE_RE = re.compile(r"\b(phoned|called|by phone|over the phone)\b", I)
AMOUNT_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?")

MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
_MONTH_ALT = "|".join(m[:3] + r"[a-z]*\.?" for m in MONTHS)
DATE_RE = re.compile(
    rf"\b(?P<mon>{_MONTH_ALT})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?\b"
    r"|\b(?P<iso>\d{4}-\d{2}-\d{2})\b|\b(?P<m>\d{1,2})/(?P<d>\d{1,2})(?:/(?P<y>\d{4}))?\b"
    r"|\b(?P<rel>yesterday|today)\b",
    I,
)


def _to_date(m: re.Match, today: date) -> date | None:
    try:
        if m.group("rel"):
            return today - timedelta(days=1) if m.group("rel").lower() == "yesterday" else today
        if m.group("iso"):
            return date.fromisoformat(m.group("iso"))
        if m.group("mon"):
            month = [x[:3] for x in MONTHS].index(m.group("mon")[:3].lower()) + 1
            day, year = int(m.group("day")), int(m.group("year") or today.year)
        else:
            month, day, year = int(m.group("m")), int(m.group("d")), int(m.group("y") or today.year)
        d = date(year, month, day)
        if not (m.group("year") or m.group("y") or m.group("iso")) and d > today:
            d = date(year - 1, month, day)  # "September 30" said in January means last year
        return d
    except ValueError:
        return None


DATE_CONTEXT = [
    ("statement_date", r"statement|\bbill\b|billing"),
    # the date the customer already told the bank, e.g. "On June 15 I sent them a written dispute"
    ("notice_date", r"sent (my|the|a|them|it)\b|disputed|reported|notified|wrote to|filed|told (the|my) (bank|issuer)"),
    ("first_deposit_date", r"first deposit|opened|deposit"),
    ("learned_of_loss_date", r"\blost\b|stolen|left my|missing|noticed|wallet"),
    ("transaction_date", r"charge[ds]?\b|purchase|transaction|paid|sent|transfer"),
]


def _dates(text: str, today: date) -> dict:
    """Assign each date to the closest context keyword (a date belongs to the nearest thing it describes)."""
    out: dict = {}
    for m in DATE_RE.finditer(text):
        d = _to_date(m, today)
        if d is None:
            continue
        before = text[max(0, m.start() - 70) : m.start()].lower()
        after = text[m.end() : m.end() + 40].lower()
        best, best_dist = None, 10**9
        for field, pattern in DATE_CONTEXT:
            for k in re.finditer(pattern, before):
                if (dist := len(before) - k.end()) < best_dist:
                    best, best_dist = field, dist
            if field != "first_deposit_date" and (k := re.search(pattern, after)) and k.start() < best_dist:
                best, best_dist = field, k.start()
        if best is None and m.group("rel") and m.group("rel").lower() == "today":
            continue
        out.setdefault(best or "transaction_date", d)
    return out


def extract_heuristics(text: str, today: date) -> dict:
    """Return the facts and intent these patterns can establish with confidence."""
    t = text
    f: dict = {}

    disputeish = bool(MERCHANT_RE.search(t) or UNAUTH_RE.search(t) or SCAM_RE.search(t) or AGENT_RE.search(t))
    if ADVICE_RE.search(t) or (OTHER_TOPIC_RE.search(t) and not disputeish):
        f["intent"] = "out_of_scope"
        return f
    if NON_US_RE.search(t):
        f["non_us"] = True
        f["intent"] = "general_question"
        return f

    if AGENT_RE.search(t):
        f["intent"] = "agent_purchase"
    elif SCAM_RE.search(t):
        f["intent"] = "scam"
    elif MERCHANT_RE.search(t):
        f["intent"], f["claim_type"] = "dispute", "merchant"
    elif UNAUTH_RE.search(t):
        f["intent"], f["claim_type"] = "dispute", "unauthorized"

    if PREPAID_RE.search(t):
        f["account_type"] = "prepaid"
    else:
        credit, debit = bool(CREDIT_RE.search(t)), bool(DEBIT_RE.search(t))
        debit = debit or (not credit and bool(DEBIT_IMPLIED_RE.search(t)))
        if credit != debit:
            f["account_type"] = "credit" if credit else "debit"

    if ATM_RE.search(t):
        f["channel"] = "atm"
    elif TRANSFER_RE.search(t) and f.get("account_type") != "credit":
        f["channel"] = "transfer"
    elif POS_RE.search(t) or re.search(r"\bcard\b", t, I):
        f["channel"] = "pos"

    f.update(_dates(t, today))
    if LOST_RE.search(t):
        f["access_device_lost_or_stolen"] = True
        if "learned_of_loss_date" not in f and re.search(r"\byesterday\b", t, I):
            f["learned_of_loss_date"] = today - timedelta(days=1)

    if SELF_INITIATED_STRONG_RE.search(t) or (SELF_INITIATED_RE.search(t) and not NOT_SELF_RE.search(t)):
        f["customer_initiated"] = True
    elif NOT_SELF_RE.search(t) or CREDENTIALS_RE.search(t):
        f["customer_initiated"] = False
    if CREDENTIALS_RE.search(t):
        f["credentials_obtained_by_fraud"] = True

    if NOT_ACCEPTED_RE.search(t):
        f["goods_accepted"] = False
    elif ACCEPTED_RE.search(t):
        f["goods_accepted"] = True
    if WRONG_AMOUNT_RE.search(t):
        f["wrong_amount"] = True
    if PHONE_NOTICE_RE.search(t):
        f["notice_in_writing"] = False
    if m := AMOUNT_RE.search(t):
        f["amount"] = float(m.group(1).replace(",", "") + "." + (m.group(2) or "0"))
    return f

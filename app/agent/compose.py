"""Reply composition. Exact content (dates, liability, questions, refusals) is templated; the LLM writes only
the plain-language explanation, which the verifier then checks."""

from __future__ import annotations

from datetime import date

from app.llm.client import LLM
from app.rag.retriever import Hit
from app.rules.calendar import BUSINESS_DAY_ASSUMPTION
from app.rules.models import Assessment

DISCLAIMER = "_This is general information from federal regulations, not legal or financial advice._"

ASK = {
    "account_type": "Was this on a debit card or bank account, or on a credit card?",
    "customer_initiated": (
        "Did you make or approve the payment yourself (for example, you were persuaded to send it), or did someone "
        "else make it using your card details, login or a code you shared?"
    ),
    "goods_accepted": ("Did you receive and keep what you paid for, or was it not delivered, refused or returned?"),
    "claim_type": "Did you make this purchase yourself, or is it a charge you don't recognize at all?",
}
ASK_ORDER = ["account_type", "claim_type", "customer_initiated", "goods_accepted"]

OUT_OF_SCOPE = (
    "I can only help with card and bank account disputes, unauthorized charges and scam reports here, so I can't "
    "advise on that. If it's about your account, I can connect you with a person at the bank."
)
INJECTION = (
    "I can't change how I work or confirm rules that aren't in my sources. I'm happy to help with a specific "
    "charge or dispute: tell me what happened and whether it was a debit or credit card."
)
HANDOFF = (
    "Of course. I'll connect you with a specialist. They'll see a summary of what you've told me so far, so you "
    "won't need to repeat it."
)
NON_US = (
    "My sources only cover US federal rules (Regulations E and Z), so I can't tell you how another country's rules "
    "or schemes apply. I'll connect you with a specialist who can help."
)
URGENT = (
    "**Please stop and do not send any more money.** Hang up on the caller; real banks and police never ask you to "
    "move money to stay safe. Then contact your bank's fraud line using the number on the back of your card."
)

EXPLAIN = """You explain US dispute rules to a bank customer in plain, calm language.
Write 80-150 words. Use ONLY the facts and regulation excerpts below.
Rules:
- Cite provisions in square brackets exactly as given, e.g. [12 CFR 1005.11(c)]. Cite nothing else.
- Do NOT write any dates, day counts or time limits (no "10 business days", no "60 days"). The exact key dates are
  listed separately after your text.
- Say each point once. Do not repeat yourself.
- Never promise or guarantee a refund or outcome. Do not give personal financial or legal advice.
- {unsettled_rule}
- {handoff_rule}

Customer said: "{question}"
Situation: claim type = {claim_type}; rules = {regime}; covered as an error = {covered}.
Findings from the rules engine:
{reasons}
Regulation excerpts:
{sources}"""


def fmt_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def deadline_block(a: Assessment) -> str:
    if not a.deadlines:
        return ""
    lines = ["**Key dates** (computed from the regulation; assumes today's report is your notice to the bank):"]
    uses_bd = False
    for d in a.deadlines:
        who = "You" if d.party == "customer" else "Bank"
        when = fmt_date(d.due) if d.due else "60 days after the statement date (tell me the date and I'll work it out)"
        lines.append(f"- {who}: {d.name}: **{when}** ({d.basis})")
        uses_bd = uses_bd or "business day" in d.note
    if uses_bd:
        lines.append(f"\n_{BUSINESS_DAY_ASSUMPTION}_")
    return "\n".join(lines)


def liability_block(a: Assessment) -> str:
    return "\n".join(["**What you could owe**"] + [f"- {n}" for n in a.liability_notes]) if a.liability_notes else ""


def explain(llm: LLM, *, question: str, a: Assessment, claim_type: str, hits: list[Hit], feedback: list[str]) -> str:
    sources = "\n\n".join(f"[{h.citation}] {h.chunk['text'][:1200]}" for h in hits) or "(none)"
    reasons = "\n".join(f"- {r}" for r in a.reasons + a.liability_notes) or "- (none)"
    prompt = EXPLAIN.format(
        question=question,
        claim_type=claim_type,
        regime={"reg_e": "Regulation E (debit/electronic transfers)", "reg_z": "Regulation Z (credit cards)"}.get(
            a.regime.value, a.regime.value
        ),
        covered={True: "yes", False: "no", None: "cannot be determined yet"}[a.covered_as_error],
        reasons=reasons,
        sources=sources,
        unsettled_rule=(
            "Say plainly that the rules for this situation are unsettled and not addressed by the regulations."
            if a.unsettled
            else "If the excerpts don't cover something, say so."
        ),
        handoff_rule=(
            "Say that a specialist should review this case." if a.needs_human else "Do not invent next steps."
        ),
    )
    msgs = [{"role": "user", "content": prompt}]
    if feedback:
        msgs.append(
            {"role": "user", "content": "Your previous draft had problems. Fix them:\n- " + "\n- ".join(feedback)}
        )
    return llm.chat(msgs, name="agent.explain", max_tokens=400).strip()


# Reviewed, templated summaries used when the LLM's explanation fails verification. Each statement is taken
# from the cited provision (see README "Verified rules").
SUMMARIES: dict[tuple[str, str, bool | None], str] = {
    ("unauthorized", "reg_e", True): (
        "A debit card payment or electronic transfer you didn't make is an unauthorized electronic fund transfer. "
        "The bank must treat it as an error and investigate once you report it [12 CFR 1005.11(a)]."
    ),
    ("unauthorized", "reg_z", True): (
        "A credit card charge you didn't make is a billing error you can dispute in writing with the card issuer "
        "[12 CFR 1026.13(a)], and your liability for unauthorized use is limited [12 CFR 1026.12(b)]."
    ),
    ("merchant", "reg_z", True): (
        "A credit card charge for goods or services that weren't delivered or accepted as agreed is a billing error "
        "you can dispute in writing with the card issuer [12 CFR 1026.13(a)]."
    ),
    ("merchant", "reg_e", True): (
        "A debit payment for the wrong amount, including being charged twice, is an error the bank must investigate "
        "once you report it [12 CFR 1005.11(a)]."
    ),
    ("scam", "reg_e", True): (
        "If someone else made the transfer using details or codes they obtained from you by fraud, it counts as an "
        "unauthorized transfer that the bank must investigate [12 CFR 1005.11(a)]."
    ),
    ("scam", "reg_z", True): (
        "Charges someone else made with your card details are unauthorized use, which you can dispute with the card "
        "issuer [12 CFR 1026.12(b)]."
    ),
}


def safe_fallback(a: Assessment, claim_type: str | None = None) -> str:
    """Used when the LLM explanation fails verification: only reviewed, templated content."""
    parts = []
    if summary := SUMMARIES.get((claim_type or "", a.regime.value, a.covered_as_error)):
        parts.append(summary)
    parts += [f"- {r}" for r in a.reasons]
    if not parts:
        parts.append("Here are the key dates and rules that apply to your situation.")
    return "\n".join(parts)

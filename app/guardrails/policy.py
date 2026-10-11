"""Input and output policy checks. Deterministic on purpose: fast, testable, and not fooled by prompt tricks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

INJECTION_RE = re.compile(
    r"(ignore (all |any )?(your |the )?(previous |prior |above )?(instructions|rules|prompt)"
    r"|disregard (your|the|all) (instructions|rules)|you are now|new instructions:|system prompt"
    r"|pretend (to be|you are)|act as (if|an?) |developer mode|jailbreak)",
    re.I,
)
HUMAN_REQUEST_RE = re.compile(
    r"((talk|speak|chat) (to|with) (a |an )?(human|person|agent|representative|someone real)"
    r"|(get|give|connect|transfer) me (to )?(a |an )?(human|person|representative|real person)"
    r"|human,? please|real person|not (want|like) (to talk to )?a bot|don'?t want (to talk to )?a bot)",
    re.I,
)
URGENT_RE = re.compile(
    r"(on the (other )?(line|phone) (right )?now|still on the phone|right now telling me|avoid arrest"
    r"|threaten(ing|ed) (me|to)|send more (money)? now)",
    re.I,
)
# Affirmative promises only. "cannot be guaranteed" and Reg Z's "check guarantee card" are not promises.
PROMISE_RE = re.compile(
    r"(you will (definitely |certainly |surely )?(get|receive) (your money|a refund|the money|reimbursed)"
    r"|\b(i|we) guarantee\b|you('| a)re guaranteed|\bguaranteed? (a |your )?(refund|outcome)"
    r"|will (definitely|certainly) be refunded|you will be refunded)",
    re.I,
)
_NEGATION_BEFORE = re.compile(r"(\bnot\b|n't\b|\bcannot\b|\bno\b|\bnever\b|\bwithout\b)[^.]{0,30}$", re.I)
UNSETTLED_RE = re.compile(
    r"(unsettled|not (yet )?(settled|clear)|evolving|unclear|no (clear|specific|explicit) (rule|guidance|answer)"
    r"|(do|does|did)(n't| not) (specifically |explicitly |directly |clearly )?(address|cover|say|state)"
    r"|not (specifically |explicitly |directly |clearly )?(addressed|covered))",
    re.I,
)


def affirmative_promise(text: str) -> bool:
    for m in PROMISE_RE.finditer(text):
        if not _NEGATION_BEFORE.search(text[max(0, m.start() - 40) : m.start()]):
            return True
    return False


DAYCOUNT_RE = re.compile(
    r"\b(\d+|one|two|three|five|ten|twenty|thirty|forty[- ]five|sixty|ninety)[\s-]+(business\s+|calendar\s+)?days?\b"
    r"|\b(two|2) (complete )?billing cycles\b",
    re.I,
)
MAX_EXPLANATION_WORDS = 220
CITATION_RE = re.compile(r"(?:12\s*CFR\s*|§\s*)(10(?:05|26)\.\d+(?:\([a-z0-9]+\))*)", re.I)


@dataclass
class InputSignals:
    injection: bool = False
    human_request: bool = False
    urgent: bool = False


def scan_input(text: str) -> InputSignals:
    return InputSignals(
        injection=bool(INJECTION_RE.search(text)),
        human_request=bool(HUMAN_REQUEST_RE.search(text)),
        urgent=bool(URGENT_RE.search(text)),
    )


@dataclass
class OutputCheck:
    problems: list[str] = field(default_factory=list)
    cause: str | None = None  # GENERATION | CITATION | None

    @property
    def ok(self) -> bool:
        return not self.problems


def check_output(
    text: str, *, allowed_dates: set[date], allowed_citations: set[str], must_mention_unsettled: bool, dates_in
) -> OutputCheck:
    """Deterministic verifier for LLM-written text (the deterministic deadline block is not checked here)."""
    chk = OutputCheck()
    if len(text.strip()) < 20:
        chk.problems.append("The explanation is empty or too short.")
        chk.cause = "GENERATION"
    stray = sorted(dates_in(text) - allowed_dates)
    if stray:
        chk.problems.append(
            "It states dates that are not in the computed deadlines: "
            + ", ".join(d.isoformat() for d in stray)
            + ". Do not write any dates; the key dates are listed separately."
        )
        chk.cause = chk.cause or "GENERATION"
    cited = {f"12 CFR {m.group(1)}" for m in CITATION_RE.finditer(text)}
    bad = sorted(c for c in cited if not any(a.startswith(c) or c.startswith(a) for a in allowed_citations))
    if bad:
        chk.problems.append(f"It cites provisions not in the provided sources: {', '.join(bad)}.")
        chk.cause = chk.cause or "CITATION"
    if affirmative_promise(text):
        chk.problems.append("It promises or guarantees an outcome; the assistant must never do that.")
        chk.cause = chk.cause or "GENERATION"
    if must_mention_unsettled and not UNSETTLED_RE.search(text):
        chk.problems.append("It must say plainly that the rules for this situation are unsettled.")
        chk.cause = chk.cause or "GENERATION"
    # Time limits live only in the computed key-dates block; prose that restates them can contradict it
    # (measured: "10 business days" written for a new account where the rule is 20).
    if DAYCOUNT_RE.search(text):
        chk.problems.append(
            "It states day counts or time limits. Remove them; the computed key dates are listed separately."
        )
        chk.cause = chk.cause or "GENERATION"
    sentences = [re.sub(r"\W+", " ", s).strip().lower() for s in re.split(r"(?<=[.!?])\s+", text)]
    sentences = [s for s in sentences if len(s) > 30]
    if len(sentences) != len(set(sentences)):
        chk.problems.append("It repeats the same sentence. Say each point once.")
        chk.cause = chk.cause or "GENERATION"
    if len(text.split()) > MAX_EXPLANATION_WORDS:
        chk.problems.append(f"It is too long. Keep it under {MAX_EXPLANATION_WORDS - 50} words.")
        chk.cause = chk.cause or "GENERATION"
    return chk

"""The agent: a LangGraph state machine.

guard_in -> understand -> route --(refuse | handoff)--------------------------------------> finalize
                                 \\-> rules --(ask)----------------------------------------> finalize
                                          \\-> retrieve -> explain -> verify --(ok)--------> finalize
                                                              ^           |
                                                              +- repair <-+ (max_retries, then safe fallback)
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agent import compose
from app.agent.extract import Extraction, extract
from app.agent.heuristics import extract_heuristics
from app.config import get_settings
from app.guardrails.dates import dates_in
from app.guardrails.pii import redact
from app.guardrails.policy import check_output, scan_input
from app.llm.client import LLM, LLMError, make_generator
from app.obs import metrics
from app.obs.tracing import get_tracer
from app.rag.retriever import Hit, Retriever, get_retriever
from app.rules.engine import assess
from app.rules.models import AccountType, Assessment, ClaimFacts, ClaimType
from app.schemas import AssistantReply, SourceRef

CLAIM_FROM_INTENT = {"scam": "scam", "agent_purchase": "agent_initiated"}
FACT_KEYS = set(ClaimFacts.model_fields) - {"notice_date", "claim_type"}
UNGROUNDED_LLM_FIELDS = (
    "account_type",
    "statement_date",
    "transaction_date",
    "first_deposit_date",
    "learned_of_loss_date",
    "notice_in_writing",
    "non_us",  # a foreign *merchant* is not a foreign *customer* (measured: gpt-oss-120b confused them)
)


class State(TypedDict, total=False):
    text: str  # redacted user message
    today: date
    known: dict  # facts accumulated across turns
    ask_rounds: int
    unresolved_turns: int
    signals: dict
    extraction: dict
    route: str  # refuse_scope | refuse_injection | handoff_human | handoff_non_us | ask | answer
    claim_type: str | None
    assessment: Assessment
    ask_for: list[str]
    hits: list[Hit]
    draft: str
    feedback: list[str]
    retries: int
    verified: bool
    reply: AssistantReply
    steps: list[dict]


class Agent:
    def __init__(self, llm: LLM | None = None, retriever: Retriever | None = None):
        self.s = get_settings()
        self.llm = llm or make_generator()
        self.retriever = retriever or get_retriever()
        self.graph = self._build()

    # ------------------------------------------------------------------ helpers

    def _step(self, state: State, node: str, **info: Any) -> None:
        state.setdefault("steps", []).append({"node": node, **info})

    def _timed(self, name: str, fn):
        def wrapper(state: State) -> State:
            start = time.perf_counter()
            with get_tracer().span(f"agent.{name}", as_type="span") as span:
                out = fn(state)
                span.update(output={k: v for k, v in (out or {}).items() if k in ("route", "claim_type", "retries")})
            metrics.NODE_LATENCY.labels(name).observe(time.perf_counter() - start)
            return out

        return wrapper

    # ------------------------------------------------------------------ nodes

    def guard_in(self, state: State) -> State:
        red = redact(state["text"])
        for kind in red.kinds:
            metrics.GUARDRAIL.labels(f"pii_{kind}").inc()
        sig = scan_input(red.text)
        if sig.injection:
            metrics.GUARDRAIL.labels("injection").inc()
        self._step(state, "guard_in", pii=red.kinds, **vars(sig))
        return {"text": red.text, "signals": vars(sig), "steps": state["steps"]}

    def understand(self, state: State) -> State:
        sig = state["signals"]
        if sig["human_request"] and not sig["urgent"]:
            self._step(state, "understand", skipped="human_request")
            return {"extraction": Extraction(intent="human_request").model_dump(mode="json"), "steps": state["steps"]}
        h = extract_heuristics(state["text"], state["today"])
        llm_error = None
        if h.get("intent") in ("out_of_scope",) or h.get("non_us"):
            merged = Extraction(**h).model_dump(mode="json")  # decided deterministically; no LLM call needed
        else:
            try:
                ex = extract(self.llm, state["text"], state["today"], state.get("known", {}))
                merged = ex.model_dump(mode="json")
                # Grounding rule: dates and card type must come from the customer's own words, which the
                # deterministic parser reads. Measured failure: the small model invented "today" as the statement
                # date and guessed card types, producing confident wrong deadlines.
                for k in UNGROUNDED_LLM_FIELDS:
                    merged[k] = Extraction.model_fields[k].default
            except LLMError as err:
                llm_error = str(err)[:200]
                merged = Extraction(intent=h.get("intent", "human_request")).model_dump(mode="json")
            # Deterministic findings win; the LLM fills only what the patterns left open.
            merged.update({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in h.items()})
        self._step(
            state,
            "understand",
            intent=merged["intent"],
            claim_type=merged.get("claim_type"),
            account=merged.get("account_type"),
            deterministic=sorted(h),
            llm_error=llm_error,
        )
        return {"extraction": merged, "steps": state["steps"]}

    def route(self, state: State) -> State:
        ex, sig = state["extraction"], state["signals"]
        if sig["injection"]:
            r = "refuse_injection"
        elif ex["intent"] == "human_request" or sig["human_request"]:
            r = "handoff_human"
        elif ex.get("non_us"):
            r = "handoff_non_us"
        elif ex["intent"] == "out_of_scope":
            r = "refuse_scope"
        else:
            r = "rules"
        self._step(state, "route", route=r)
        return {"route": r, "steps": state["steps"]}

    def rules(self, state: State) -> State:
        ex = state["extraction"]
        known = dict(state.get("known") or {})
        for k in FACT_KEYS:
            v = ex.get(k)
            if v is None or v == "unknown" or (k == "access_device_lost_or_stolen" and v is False):
                continue  # no information: keep what earlier turns established
            known[k] = v
        if ex.get("notice_date"):
            known["notice_date"] = ex["notice_date"]
        if ex["intent"] in CLAIM_FROM_INTENT:
            known["claim_type"] = CLAIM_FROM_INTENT[ex["intent"]]
        elif ex.get("claim_type"):
            known["claim_type"] = ex["claim_type"]
        claim = known.get("claim_type")

        ask_for: list[str] = []
        if known.get("account_type", "unknown") == "unknown":
            ask_for.append("account_type")
        if claim is None and ex["intent"] != "general_question":
            ask_for.append("claim_type")
        # The customer may have notified the bank earlier ("On June 15 I sent a written dispute"); otherwise this
        # conversation is treated as the notice. A future date is never accepted as a notice date.
        notice = date.fromisoformat(known["notice_date"]) if known.get("notice_date") else state["today"]
        facts = ClaimFacts(
            claim_type=ClaimType(claim or "unauthorized"),
            notice_date=min(notice, state["today"]),
            **{k: v for k, v in known.items() if k in FACT_KEYS},
        )
        a = assess(facts, today=state["today"])
        if claim == "scam" and known.get("customer_initiated") is None:
            ask_for.append("customer_initiated")
        if claim == "merchant" and facts.account_type == AccountType.CREDIT and "goods_accepted" in a.missing_facts:
            ask_for.append("goods_accepted")

        rounds = state.get("ask_rounds", 0)
        route = "ask" if ask_for and rounds < 2 and not state["signals"]["urgent"] else "answer"
        if ask_for and route == "answer":
            a.needs_human = True
            a.reasons.append("Some key facts are still missing, so a specialist should review this case.")
        self._step(
            state,
            "rules",
            regime=a.regime.value,
            covered=a.covered_as_error,
            needs_human=a.needs_human,
            unsettled=a.unsettled,
            ask_for=ask_for,
            citations=a.citations,
        )
        return {
            "known": known,
            "claim_type": claim,
            "assessment": a,
            "ask_for": ask_for,
            "route": route,
            "ask_rounds": rounds + (route == "ask"),
            "steps": state["steps"],
        }

    def retrieve(self, state: State) -> State:
        a = state["assessment"]
        anchored = self.retriever.by_citation(a.citations)
        regime = {"reg_e": "E", "reg_z": "Z"}.get(a.regime.value)
        query = f"{state['text']} {' '.join(a.citations)}"
        searched = self.retriever.search(query, regime=regime, k=4)
        seen, hits = set(), []
        for h in anchored + searched:
            if h.chunk["chunk_id"] not in seen:
                seen.add(h.chunk["chunk_id"])
                hits.append(h)
        hits = hits[:6]
        self._step(state, "retrieve", anchored=len(anchored), citations=[h.citation for h in hits])
        return {"hits": hits, "retries": 0, "feedback": [], "steps": state["steps"]}

    def explain(self, state: State) -> State:
        try:
            draft = compose.explain(
                self.llm,
                question=state["text"],
                a=state["assessment"],
                claim_type=state.get("claim_type") or "unknown",
                hits=state["hits"],
                feedback=state.get("feedback", []),
            )
        except LLMError as err:
            draft = ""
            self._step(state, "explain", error=str(err)[:200])
        return {"draft": draft, "steps": state["steps"]}

    def verify(self, state: State) -> State:
        a = state["assessment"]
        allowed_dates = {d.due for d in a.deadlines if d.due} | dates_in(state["text"]) | {state["today"]}
        allowed_cites = set(a.citations) | {h.citation for h in state["hits"]}
        chk = check_output(
            state["draft"],
            allowed_dates=allowed_dates,
            allowed_citations=allowed_cites,
            must_mention_unsettled=a.unsettled,
            dates_in=dates_in,
        )
        self._step(state, "verify", ok=chk.ok, problems=chk.problems, retry=state.get("retries", 0))
        if not chk.ok:
            metrics.RETRIES.labels(chk.cause or "GENERATION").inc()
        return {"verified": chk.ok, "feedback": chk.problems, "steps": state["steps"]}

    def repair(self, state: State) -> State:
        return {"retries": state.get("retries", 0) + 1}

    def finalize(self, state: State) -> State:
        route = state["route"]
        a: Assessment | None = state.get("assessment")
        sig = state["signals"]
        parts: list[str] = []
        handoff, reason, abstained, asked = False, None, False, []
        actions: list[str] = []
        if sig.get("urgent"):
            parts.append(compose.URGENT)
        if route == "refuse_injection":
            parts.append(compose.INJECTION)
            abstained = True
        elif route == "refuse_scope":
            parts.append(compose.OUT_OF_SCOPE)
            abstained = True
        elif route == "handoff_human":
            parts.append(compose.HANDOFF)
            handoff, reason = True, "customer_request"
        elif route == "handoff_non_us":
            parts.append(compose.NON_US)
            handoff, reason, abstained = True, "not_in_sources", True
        elif route == "ask":
            asked = sorted(state["ask_for"], key=compose.ASK_ORDER.index)[:2]
            parts.append("I can help with that. To give you the right rules and dates, I need a bit more detail:")
            parts += [f"- {compose.ASK[f]}" for f in asked]
            if state.get("claim_type") == "scam":  # design spec: scam reports always get a route to a person
                handoff, reason = True, "scam"
                parts.append(
                    "If you'd rather talk this through with a person, I can connect you with a specialist now."
                )
        else:  # answer
            text = state.get("draft", "")
            if not state.get("verified"):
                text = compose.safe_fallback(a, state.get("claim_type"))
                abstained = True
                metrics.ABSTAINS.labels("verification_failed").inc()
            parts.append(text)
            if blk := compose.deadline_block(a):
                parts.append(blk)
            if blk := compose.liability_block(a):
                parts.append(blk)
            if a.needs_human or abstained:
                handoff = True
                reason = "unsettled" if a.unsettled else "needs_review" if a.needs_human else "verification_failed"
                parts.append("I'd like a specialist to review this with you. Would you like me to connect you?")
            if a.covered_as_error:
                actions.append("open_dispute_case")
            if state.get("known", {}).get("access_device_lost_or_stolen") or state.get("claim_type") in (
                "unauthorized",
                "scam",
            ):
                actions.append("block_card")
        unresolved = state.get("unresolved_turns", 0) + (route in ("ask",) or abstained)
        if unresolved >= self.s.max_unresolved_turns and not handoff:
            handoff, reason = True, "unresolved_turns"
            parts.append("We've gone back and forth a few times. Would you like me to connect you with a person?")
        parts.append(compose.DISCLAIMER)
        if handoff:
            metrics.HANDOFFS.labels(reason or "other").inc()

        hits: list[Hit] = state.get("hits", [])
        reply = AssistantReply(
            reply="\n\n".join(p for p in parts if p),
            sources=[
                SourceRef(
                    citation=h.citation,
                    heading=h.chunk["heading"],
                    quote=h.chunk["text"],
                    url=h.chunk["url"],
                    as_of=h.chunk["as_of"],
                )
                for h in hits
            ],
            claim_type=state.get("claim_type"),
            regime=a.regime.value if a else None,
            deadlines=a.deadlines if a and route == "answer" else [],
            handoff_offered=handoff,
            handoff_reason=reason,
            unsettled=bool(a and a.unsettled),
            asked_for=asked,
            abstained=abstained,
            suggested_actions=actions,
            system="agent",
            steps=state.get("steps", []),
            corpus_version=self.retriever.version,
        )
        return {"reply": reply, "unresolved_turns": unresolved}

    # ------------------------------------------------------------------ graph

    def _build(self):
        g = StateGraph(State)
        for name in ("guard_in", "understand", "route", "rules", "retrieve", "explain", "verify", "repair", "finalize"):
            g.add_node(name, self._timed(name, getattr(self, name)))
        g.set_entry_point("guard_in")
        g.add_edge("guard_in", "understand")
        g.add_edge("understand", "route")
        g.add_conditional_edges("route", lambda s: "rules" if s["route"] == "rules" else "finalize")
        g.add_conditional_edges("rules", lambda s: "retrieve" if s["route"] == "answer" else "finalize")
        g.add_edge("retrieve", "explain")
        g.add_edge("explain", "verify")
        g.add_conditional_edges(
            "verify",
            lambda s: (
                "finalize"
                if s["verified"] or not self.s.enable_healing or s.get("retries", 0) >= self.s.max_retries
                else "repair"
            ),
        )
        g.add_edge("repair", "explain")
        g.add_edge("finalize", END)
        return g.compile()

    # ------------------------------------------------------------------ public

    def turn(self, text: str, today: date, session: dict | None = None) -> tuple[AssistantReply, dict]:
        """Run one chat turn. `session` carries known facts and counters between turns."""
        session = session or {}
        start = time.perf_counter()
        tracer = get_tracer()
        with tracer.span("chat.turn", as_type="agent", input=redact(text).text) as span:
            out = self.graph.invoke(
                {
                    "text": text,
                    "today": today,
                    "known": session.get("known", {}),
                    "ask_rounds": session.get("ask_rounds", 0),
                    "unresolved_turns": session.get("unresolved_turns", 0),
                    "steps": [],
                }
            )
            reply: AssistantReply = out["reply"]
            span.update(
                output=reply.reply,
                metadata={
                    "claim_type": reply.claim_type,
                    "regime": reply.regime,
                    "handoff": reply.handoff_offered,
                    "abstained": reply.abstained,
                },
            )
            trace_id = tracer.current_trace_id()
        metrics.LATENCY.observe(time.perf_counter() - start)
        outcome = (
            "abstain"
            if reply.abstained
            else "handoff"
            if reply.handoff_offered
            else ("ask" if reply.asked_for else "answer")
        )
        metrics.REQUESTS.labels(reply.claim_type or "none", outcome).inc()
        new_session = {
            "known": out.get("known", session.get("known", {})),
            "ask_rounds": out.get("ask_rounds", 0),
            "unresolved_turns": out.get("unresolved_turns", 0),
            "trace_id": trace_id,
        }
        return reply, new_session


_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


def run_turns(turns: list[str], today: date) -> AssistantReply:
    """Evaluate a scripted conversation; returns the reply to the last turn."""
    session: dict = {}
    reply = None
    for t in turns:
        reply, session = get_agent().turn(t, today, session)
    return reply

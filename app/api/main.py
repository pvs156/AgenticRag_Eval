"""HTTP API (FastAPI). The Next.js front end calls these through its server-side BFF routes."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from app.agent.graph import get_agent
from app.config import get_settings
from app.guardrails.pii import redact
from app.obs import metrics
from app.obs.online_eval import evaluate_turn
from app.obs.tracing import get_tracer
from app.schemas import AssistantReply
from app.store import Store

log = logging.getLogger("api")


# ------------------------------------------------------------------ dependencies


def check_token(x_demo_token: str | None = Header(default=None)) -> None:
    token = get_settings().demo_token
    if token and x_demo_token != token:
        raise HTTPException(status_code=401, detail="invalid demo token")


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    now, window = time.time(), _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= get_settings().rate_limit_per_min:
        raise HTTPException(status_code=429, detail="too many requests, please wait a minute")
    window.append(now)


guarded = [Depends(check_token), Depends(rate_limit)]


# ------------------------------------------------------------------ models


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatOut(BaseModel):
    session_id: str
    trace_id: str | None
    trace_url: str | None = None
    online_scores: dict[str, float] = {}
    result: AssistantReply


class FeedbackIn(BaseModel):
    session_id: str | None = None
    trace_id: str | None = None
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=1000)


class ActionIn(BaseModel):
    session_id: str
    action: str
    confirm: bool


# ------------------------------------------------------------------ lifecycle


_ready = threading.Event()


@asynccontextmanager
async def lifespan(_: FastAPI):
    def load() -> None:
        try:
            agent = get_agent()
            agent.retriever.search("warm up")  # loads embedding + rerank models and the vector index
            _ready.set()
            log.info("agent ready")
        except Exception:
            log.exception("warm-up failed")

    threading.Thread(target=load, daemon=True).start()
    yield
    get_tracer().flush()


app = FastAPI(title="Dispute & Scam Resolution Assistant", version="0.1.0", lifespan=lifespan)
store = Store()


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict:
    if not _ready.is_set():
        raise HTTPException(status_code=503, detail="warming up")
    return {"status": "ready", "corpus_version": get_agent().retriever.version}


@app.get("/metrics")
def prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ------------------------------------------------------------------ chat


@app.post("/v1/chat", response_model=ChatOut, dependencies=guarded)
def chat(body: ChatIn) -> ChatOut:
    if not _ready.is_set():
        raise HTTPException(status_code=503, detail="assistant is starting, try again shortly")
    sid = body.session_id or uuid.uuid4().hex
    session = store.get_session(sid) or {}
    try:
        reply, session = get_agent().turn(body.message, date.today(), session)
    except Exception as err:
        metrics.ERRORS.labels("chat").inc()
        log.exception("chat failed")
        raise HTTPException(status_code=500, detail="something went wrong; please try again") from err
    trace_id = session.get("trace_id")
    store.save_session(sid, session)
    store.audit(
        "turn",
        {
            "message": redact(body.message).text,
            "claim_type": reply.claim_type,
            "regime": reply.regime,
            "handoff": reply.handoff_offered,
            "handoff_reason": reply.handoff_reason,
            "abstained": reply.abstained,
            "asked_for": reply.asked_for,
            "deadlines": [d.model_dump(mode="json") for d in reply.deadlines],
            "steps": reply.steps,
        },
        session_id=sid,
        trace_id=trace_id,
    )
    scores = evaluate_turn(reply, trace_id)
    get_tracer().flush()
    return ChatOut(
        session_id=sid,
        trace_id=trace_id,
        trace_url=get_tracer().trace_url(trace_id),
        online_scores=scores,
        result=reply,
    )


@app.post("/v1/feedback", dependencies=guarded)
def feedback(body: FeedbackIn) -> dict:
    store.feedback(body.session_id, body.trace_id, body.rating, body.comment)
    metrics.FEEDBACK.labels({1: "up", -1: "down", 0: "neutral"}[body.rating]).inc()
    get_tracer().score(trace_id=body.trace_id, name="user_feedback", value=body.rating, comment=body.comment)
    return {"ok": True}


MOCK_ACTIONS = {"open_dispute_case", "block_card", "handoff"}


@app.post("/v1/actions", dependencies=guarded)
def actions(body: ActionIn) -> dict:
    """Mock write actions. Nothing real happens; the point is the confirm-before-act pattern and the audit."""
    if body.action not in MOCK_ACTIONS:
        raise HTTPException(status_code=400, detail="unknown action")
    session = store.get_session(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not body.confirm:
        store.audit("action_declined", {"action": body.action}, session_id=body.session_id)
        return {"ok": True, "status": "declined"}
    case_id = store.create_case(body.session_id, body.action, {"facts": session.get("known", {})})
    store.audit("action_confirmed", {"action": body.action, "case_id": case_id}, session_id=body.session_id)
    if body.action == "handoff":
        metrics.HANDOFFS.labels("confirmed").inc()
    messages = {
        "open_dispute_case": (
            f"Demo dispute case {case_id} created; a real bank would now start the investigation clock."
        ),
        "block_card": f"Demo card block {case_id} recorded. In a real bank your card would now be frozen.",
        "handoff": f"Demo handoff {case_id} created. A specialist would receive your conversation summary.",
    }
    return {"ok": True, "status": "done", "reference": case_id, "message": messages[body.action]}


@app.get("/v1/sessions/{sid}/audit", dependencies=guarded)
def audit_trail(sid: str) -> list[dict]:
    """Replayable audit trail for one conversation (the interviewer view uses this)."""
    return store.audit_trail(sid)

"""Online evaluation of live traffic.

Every turn gets cheap deterministic scores (verification passed, citation validity, abstained). A sampled
share also gets an LLM-judge groundedness score. All scores go to Langfuse (attached to the trace) and to
Prometheus (for Grafana alerts). Failures here never affect the user's reply.
"""

from __future__ import annotations

import json
import logging
import random
import re

from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.client import LLMError, make_judge
from app.obs import metrics
from app.obs.tracing import get_tracer
from app.schemas import AssistantReply

log = logging.getLogger(__name__)
_CITE = re.compile(r"\[(12 CFR [^\]]+)\]")


class Groundedness(BaseModel):
    score: float = Field(ge=0, le=1, description="1 = every claim supported by the sources, 0 = unsupported")
    reason: str = ""


JUDGE_PROMPT = """You check whether an assistant's explanation is supported by regulation excerpts.
Ignore the 'Key dates' and 'What you could owe' sections (they are computed separately).
Score 1.0 if every factual claim in the explanation is supported by the excerpts, 0.0 if the main claims are
unsupported, in between otherwise.

Excerpts:
{sources}

Assistant explanation:
{reply}"""


def deterministic_scores(reply: AssistantReply) -> dict[str, float]:
    verify_steps = [s for s in reply.steps if s.get("node") == "verify"]
    cited = set(_CITE.findall(reply.reply))
    source_cites = {s.citation for s in reply.sources}
    valid = [c for c in cited if any(s.startswith(c) or c.startswith(s) for s in source_cites)]
    out = {"abstained": float(reply.abstained), "handoff_offered": float(reply.handoff_offered)}
    if verify_steps:
        out["first_draft_passed"] = float(verify_steps[0].get("ok", False))
        out["retries"] = float(len(verify_steps) - 1)
    if cited:
        out["citation_validity"] = len(valid) / len(cited)
    return out


def judge_groundedness(reply: AssistantReply) -> Groundedness | None:
    explanation = reply.reply.split("**Key dates**")[0]
    sources = "\n\n".join(f"[{s.citation}] {s.quote[:1000]}" for s in reply.sources[:6])
    if not sources:
        return None
    judge = make_judge()
    msgs = [{"role": "user", "content": JUDGE_PROMPT.format(sources=sources, reply=explanation)}]
    return judge.structured(msgs, Groundedness, name="online_judge", max_tokens=300)


def evaluate_turn(reply: AssistantReply, trace_id: str | None) -> dict:
    tracer = get_tracer()
    scores = deterministic_scores(reply)
    if reply.sources and not reply.abstained and random.random() < get_settings().online_eval_sample_rate:
        try:
            g = judge_groundedness(reply)
            if g:
                scores["groundedness"] = g.score
                tracer.score(trace_id=trace_id, name="groundedness", value=g.score, comment=g.reason[:500])
        except (LLMError, Exception) as err:  # noqa: BLE001 - online scoring is best effort
            metrics.JUDGE_ERRORS.inc()
            log.warning("online judge failed: %s", err)
    for name, value in scores.items():
        if name in ("citation_validity", "groundedness", "first_draft_passed"):
            metrics.ONLINE_SCORE.labels(name).observe(value)
        if name != "groundedness":
            tracer.score(trace_id=trace_id, name=name, value=value)
    log.debug("online scores %s", json.dumps(scores))
    return scores

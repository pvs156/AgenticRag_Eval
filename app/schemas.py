"""Response contract shared by the baseline RAG and the agent, so the same scorers grade both."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.rules.models import Deadline


class SourceRef(BaseModel):
    citation: str
    heading: str = ""
    quote: str = ""
    url: str = ""
    as_of: str = ""


class AssistantReply(BaseModel):
    reply: str
    sources: list[SourceRef] = []
    claim_type: str | None = None
    regime: str | None = None
    deadlines: list[Deadline] = []
    handoff_offered: bool = False
    handoff_reason: str | None = None
    unsettled: bool = False
    asked_for: list[str] = []
    abstained: bool = False
    suggested_actions: list[str] = []  # mock write actions; each needs explicit user confirmation
    system: str = "agent"  # "baseline" | "agent"
    steps: list[dict] = Field(default_factory=list, description="Ordered node log for audit and debugging")
    corpus_version: str = ""

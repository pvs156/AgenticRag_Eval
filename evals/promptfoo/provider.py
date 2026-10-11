"""Promptfoo Python provider: sends each red-team prompt through the real agent graph."""

from datetime import date

from app.agent.graph import get_agent


def call_api(prompt, options, context):
    reply, _ = get_agent().turn(prompt, date.today(), {})
    return {
        "output": reply.reply,
        "metadata": {"abstained": reply.abstained, "handoff": reply.handoff_offered, "regime": reply.regime},
    }

"""LLM step 1: understand the customer's message and extract structured facts.

The model only classifies and extracts. Rules, deadlines and routing are deterministic downstream."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.llm.client import LLM

Intent = Literal["dispute", "scam", "agent_purchase", "general_question", "out_of_scope", "human_request"]


class Extraction(BaseModel):
    intent: Intent = Field(
        description="dispute = unauthorized/wrong/merchant charge; scam = tricked or defrauded; agent_purchase = an "
        "AI agent/assistant made the purchase; general_question = about dispute rules without a specific charge; "
        "out_of_scope = anything else (investing, loans, mortgages, balances, legal action); human_request = wants "
        "a person"
    )
    claim_type: Literal["unauthorized", "merchant", "scam", "agent_initiated"] | None = Field(
        default=None,
        description="unauthorized = customer did not make the charge; merchant = customer made the purchase but "
        "goods/services were not delivered as agreed, or wrong/duplicate amount; scam = customer was tricked; "
        "agent_initiated = AI agent made it",
    )
    account_type: Literal["debit", "credit", "prepaid", "unknown"] = Field(
        default="unknown",
        description="debit = debit card, checking/savings, bank transfer, payment app from bank account; credit = "
        "credit card; prepaid = prepaid card; unknown if not stated (a bare 'card' is unknown)",
    )
    channel: Literal["pos", "atm", "transfer", "foreign", "unknown"] = Field(
        default="unknown",
        description="pos = card purchase at a merchant incl. online; atm; transfer = online/app/P2P/ACH; foreign = "
        "initiated outside the US",
    )
    statement_date: date | None = Field(default=None, description="date of the statement showing the item")
    transaction_date: date | None = None
    first_deposit_date: date | None = Field(default=None, description="only if the account was just opened")
    learned_of_loss_date: date | None = Field(default=None, description="when they noticed the card lost/stolen")
    access_device_lost_or_stolen: bool = Field(default=False, description="card/wallet/phone lost or stolen")
    customer_initiated: bool | None = Field(
        default=None, description="true if the customer personally made/approved the payment (even if tricked)"
    )
    credentials_obtained_by_fraud: bool | None = Field(
        default=None, description="true if a fraudster got the card details/login/code and made the payment"
    )
    goods_accepted: bool | None = Field(
        default=None,
        description="merchant disputes: true if they received and kept the goods; false if not "
        "delivered, refused or returned",
    )
    wrong_amount: bool | None = Field(default=None, description="charged the wrong amount or charged twice")
    notice_in_writing: bool | None = Field(default=None, description="false if they reported by phone only")
    amount: float | None = None
    non_us: bool = Field(default=False, description="customer is outside the US or asks about non-US rules")


PROMPT = """You extract facts from a bank customer's message about a card or account problem.
Today is {today}. Resolve relative dates ("yesterday", "last Friday") to calendar dates. Use null for unknown
facts; never guess. Previously known facts from this conversation: {known}

Customer message:
\"\"\"{text}\"\"\""""


def extract(llm: LLM, text: str, today: date, known: dict) -> Extraction:
    msgs = [{"role": "user", "content": PROMPT.format(today=today.isoformat(), known=known or "none", text=text)}]
    return llm.structured(msgs, Extraction, name="agent.extract", max_tokens=600)

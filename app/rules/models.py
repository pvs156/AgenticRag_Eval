from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class ClaimType(StrEnum):
    UNAUTHORIZED = "unauthorized"  # "I didn't make this charge"
    MERCHANT = "merchant"  # "I paid but goods/services weren't delivered as agreed"
    SCAM = "scam"  # "I was tricked into paying / sending money"
    AGENT_INITIATED = "agent_initiated"  # "My AI shopping agent bought the wrong thing"


class AccountType(StrEnum):
    DEBIT = "debit"  # consumer deposit account accessed by debit card or electronic transfer (Reg E)
    CREDIT = "credit"  # credit card / open-end credit (Reg Z)
    PREPAID = "prepaid"
    UNKNOWN = "unknown"


class Channel(StrEnum):
    POS = "pos"  # debit card at a merchant, incl. online, mail and phone orders (Supp. I 11(c)(3)-1)
    ATM = "atm"
    TRANSFER = "transfer"  # online/app/P2P/ACH transfer
    FOREIGN = "foreign"  # transfer not initiated within a US state
    UNKNOWN = "unknown"


class Regime(StrEnum):
    REG_E = "reg_e"
    REG_Z = "reg_z"
    NOT_COVERED = "not_covered"  # outside the indexed federal error-resolution rules
    UNKNOWN = "unknown"


class ClaimFacts(BaseModel):
    claim_type: ClaimType
    account_type: AccountType = AccountType.UNKNOWN
    channel: Channel = Channel.UNKNOWN
    notice_date: date = Field(description="Date the customer notifies the institution (usually today)")
    statement_date: date | None = Field(
        default=None, description="Date the periodic statement first showing the item was sent"
    )
    first_deposit_date: date | None = Field(default=None, description="For new-account extensions")
    transaction_date: date | None = None
    access_device_lost_or_stolen: bool = False
    learned_of_loss_date: date | None = None
    customer_initiated: bool | None = Field(
        default=None, description="Did the customer personally make or approve the payment?"
    )
    credentials_obtained_by_fraud: bool | None = Field(
        default=None,
        description="Did a fraudster obtain the card/login from the customer and make the transfer themselves?",
    )
    goods_accepted: bool | None = Field(
        default=None, description="Merchant disputes: did the customer accept the goods?"
    )
    wrong_amount: bool | None = Field(
        default=None, description="Charged the wrong amount or charged twice for a purchase the customer made"
    )
    notice_in_writing: bool | None = None
    amount: float | None = None


class Deadline(BaseModel):
    name: str
    due: date | None
    party: str  # "customer" | "institution"
    basis: str  # citation
    note: str = ""
    # False for windows that only change a liability tier (missing them is explained, not escalated).
    escalate_if_missed: bool = True


class Assessment(BaseModel):
    regime: Regime
    covered_as_error: bool | None  # None = cannot be determined from facts/rules
    deadlines: list[Deadline] = []
    liability_notes: list[str] = []
    citations: list[str] = []
    missing_facts: list[str] = []
    needs_human: bool = False
    unsettled: bool = False
    reasons: list[str] = []

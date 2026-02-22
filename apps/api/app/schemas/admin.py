from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminPricingRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_alias: str
    multiplier: str
    pricing_version: str


class AdminPricingListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pricing_version: str
    items: list[AdminPricingRead]


class AdminPricingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    multiplier: float = Field(gt=0.0, le=100.0)
    pricing_version: str


class AdminUsageBreakdownItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_alias: str
    call_count: int
    credits_burned: str


class AdminUsageSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_credits_burned: str
    total_llm_calls: int
    total_output_tokens: int
    from_date: date | None = None
    to_date: date | None = None
    breakdown: list[AdminUsageBreakdownItem]


class AdminTransactionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    amount: str
    note: str | None
    created_at: datetime


class AdminWalletRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    balance: str
    recent_transactions: list[AdminTransactionRead]


class AdminGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float = Field(le=10_000.0)
    note: str | None = None


class AdminGrantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    new_balance: str
    transaction_id: str

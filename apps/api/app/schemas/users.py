from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WalletRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    balance: str


class UsageEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    model_alias: str
    credits_burned: str
    created_at: datetime


class UsageListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[UsageEventRead]
    total: int


class TransactionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    amount: str
    initiated_by: str | None
    note: str | None
    reference_id: str | None
    created_at: datetime


class TransactionListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transactions: list[TransactionRead]
    total: int

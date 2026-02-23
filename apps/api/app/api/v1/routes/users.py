from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import CreditTransaction, LlmCallEvent
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.schemas.users import (
    TransactionListRead,
    TransactionRead,
    UsageEventRead,
    UsageListRead,
    WalletRead,
)
from apps.api.app.services.billing.wallet import WalletService, get_wallet_service
from apps.api.app.utils.decimal_format import format_decimal

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/wallet", response_model=WalletRead)
async def get_my_wallet(
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
) -> WalletRead:
    user_id = current_user["user_id"]
    wallet = await wallet_service.get_or_create_wallet(db, user_id=user_id)
    await db.commit()
    balance = wallet.balance if wallet.balance is not None else Decimal("0")
    return WalletRead(user_id=user_id, balance=format_decimal(balance))


@router.get("/me/usage", response_model=UsageListRead)
async def get_my_usage(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageListRead:
    user_id = current_user["user_id"]
    total = int(await db.scalar(select(func.count(LlmCallEvent.id)).where(LlmCallEvent.user_id == user_id)) or 0)
    rows = await db.scalars(
        select(LlmCallEvent)
        .where(LlmCallEvent.user_id == user_id)
        .order_by(LlmCallEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = [
        UsageEventRead(
            id=row.id,
            model_alias=row.model_alias,
            credits_burned=format_decimal(Decimal(str(row.credits_burned))),
            created_at=row.created_at,
        )
        for row in rows.all()
    ]
    return UsageListRead(events=events, total=total)


@router.get("/me/transactions", response_model=TransactionListRead)
async def get_my_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionListRead:
    user_id = current_user["user_id"]
    total = int(
        await db.scalar(select(func.count(CreditTransaction.id)).where(CreditTransaction.user_id == user_id)) or 0
    )
    rows = await db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    transactions = [
        TransactionRead(
            id=row.id,
            kind=row.kind,
            amount=format_decimal(Decimal(str(row.amount))),
            initiated_by=row.initiated_by,
            note=row.note,
            reference_id=row.reference_id,
            created_at=row.created_at,
        )
        for row in rows.all()
    ]
    return TransactionListRead(transactions=transactions, total=total)

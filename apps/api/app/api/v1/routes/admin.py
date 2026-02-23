from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import Settings, get_settings
from apps.api.app.db.models import CreditTransaction, CreditWallet, LlmCallEvent
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.schemas.admin import (
    AdminGrantRequest,
    AdminGrantResponse,
    AdminPricingListRead,
    AdminPricingRead,
    AdminPricingUpdate,
    AdminTransactionRead,
    AdminUsageBreakdownItem,
    AdminUsageDailyBucket,
    AdminUsageSummaryRead,
    AdminWalletRead,
)
from apps.api.app.services.billing.wallet import WalletService, get_wallet_service
from apps.api.app.services.billing.pricing_admin import (
    get_active_pricing_version,
    list_model_pricing,
    update_model_multiplier,
)
from apps.api.app.utils.decimal_format import format_decimal

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(
    current_user: dict[str, str] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if current_user["user_id"] not in settings.admin_user_ids:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


@router.get("/pricing", response_model=AdminPricingListRead)
async def get_pricing(
    _: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminPricingListRead:
    active_version = await get_active_pricing_version(db)
    rows = await list_model_pricing(db, pricing_version=active_version)
    return AdminPricingListRead(
        pricing_version=active_version,
        items=[
            AdminPricingRead(
                model_alias=row.model_alias,
                multiplier=format_decimal(Decimal(str(row.multiplier))),
                pricing_version=row.pricing_version,
            )
            for row in rows
        ],
    )


@router.patch("/pricing/{model_alias}", response_model=AdminPricingRead)
async def patch_pricing_multiplier(
    model_alias: str,
    payload: AdminPricingUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminPricingRead:
    try:
        updated = await update_model_multiplier(
            db=db,
            model_alias=model_alias,
            new_multiplier=payload.multiplier,
            pricing_version=payload.pricing_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AdminPricingRead(
        model_alias=updated.model_alias,
        multiplier=format_decimal(Decimal(str(updated.multiplier))),
        pricing_version=updated.pricing_version,
    )


@router.get("/usage/summary", response_model=AdminUsageSummaryRead)
async def get_usage_summary(
    user_id: str | None = Query(default=None),
    model_alias: str | None = Query(default=None),
    bucket: str | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    _: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUsageSummaryRead:
    conditions = []
    if user_id:
        conditions.append(LlmCallEvent.user_id == user_id)
    if model_alias:
        conditions.append(LlmCallEvent.model_alias == model_alias)
    if from_date is not None:
        conditions.append(func.date(LlmCallEvent.created_at) >= from_date)
    if to_date is not None:
        conditions.append(func.date(LlmCallEvent.created_at) <= to_date)

    totals_query = select(
        func.coalesce(func.sum(LlmCallEvent.credits_burned), 0),
        func.count(LlmCallEvent.id),
        func.coalesce(func.sum(LlmCallEvent.output_tokens), 0),
    )
    if conditions:
        totals_query = totals_query.where(*conditions)
    totals_row = (await db.execute(totals_query)).one()
    total_credits = Decimal(str(totals_row[0]))
    total_calls = int(totals_row[1] or 0)
    total_output_tokens = int(totals_row[2] or 0)

    breakdown_query = select(
        LlmCallEvent.model_alias,
        func.count(LlmCallEvent.id),
        func.coalesce(func.sum(LlmCallEvent.credits_burned), 0),
    )
    if conditions:
        breakdown_query = breakdown_query.where(*conditions)
    breakdown_query = breakdown_query.group_by(LlmCallEvent.model_alias).order_by(LlmCallEvent.model_alias.asc())
    breakdown_rows = (await db.execute(breakdown_query)).all()

    daily_rows: list[tuple[date, int, Decimal]] = []
    if bucket == "day":
        daily_query = select(
            func.date(LlmCallEvent.created_at),
            func.count(LlmCallEvent.id),
            func.coalesce(func.sum(LlmCallEvent.credits_burned), 0),
        )
        if conditions:
            daily_query = daily_query.where(*conditions)
        daily_query = daily_query.group_by(func.date(LlmCallEvent.created_at)).order_by(
            func.date(LlmCallEvent.created_at).asc()
        )
        daily_rows = (await db.execute(daily_query)).all()

    return AdminUsageSummaryRead(
        total_credits_burned=format_decimal(total_credits),
        total_llm_calls=total_calls,
        total_output_tokens=total_output_tokens,
        from_date=from_date,
        to_date=to_date,
        breakdown=[
            AdminUsageBreakdownItem(
                model_alias=row[0],
                call_count=int(row[1]),
                credits_burned=format_decimal(Decimal(str(row[2]))),
            )
            for row in breakdown_rows
        ],
        daily=[
            AdminUsageDailyBucket(
                date=row[0],
                call_count=int(row[1]),
                credits_burned=format_decimal(Decimal(str(row[2]))),
            )
            for row in daily_rows
        ],
    )


@router.get("/wallets/{user_id}", response_model=AdminWalletRead)
async def get_wallet_for_user(
    user_id: str,
    _: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminWalletRead:
    wallet = await db.scalar(select(CreditWallet).where(CreditWallet.user_id == user_id))
    if wallet is None:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    tx_rows = await db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(10)
    )
    transactions = [
        AdminTransactionRead(
            id=row.id,
            kind=row.kind,
            amount=format_decimal(Decimal(str(row.amount))),
            initiated_by=row.initiated_by,
            note=row.note,
            created_at=row.created_at,
        )
        for row in tx_rows.all()
    ]
    return AdminWalletRead(
        user_id=user_id,
        balance=format_decimal(Decimal(str(wallet.balance))),
        recent_transactions=transactions,
    )


@router.post("/wallets/{user_id}/grant", response_model=AdminGrantResponse)
async def grant_wallet_credits(
    user_id: str,
    payload: AdminGrantRequest,
    admin_user: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
) -> AdminGrantResponse:
    result = await wallet_service.stage_grant(
        db=db,
        user_id=user_id,
        amount=payload.amount,
        note=payload.note,
        initiated_by=admin_user["user_id"],
    )
    await db.commit()
    return AdminGrantResponse(
        user_id=user_id,
        new_balance=format_decimal(result.new_balance),
        transaction_id=result.transaction_id or "",
    )

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import Settings, get_settings
from apps.api.app.db.models import CreditTransaction, CreditWallet, LlmCallEvent, Session
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.schemas.admin import (
    AdminEnforcementRead,
    AdminEnforcementUpdate,
    AdminGrantRequest,
    AdminGrantResponse,
    AdminActiveUsersRead,
    AdminUserGrantResponse,
    AdminPricingListRead,
    AdminPricingRead,
    AdminSettingsRead,
    AdminPricingUpdate,
    AdminTransactionRead,
    AdminUsageBucket,
    AdminUsageBreakdownItem,
    AdminUsageAnalyticsRead,
    AdminUsageAnalyticsRowRead,
    AdminUsageSummaryRead,
    AdminWalletRead,
)
from apps.api.app.services.billing.enforcement import (
    get_enforcement_enabled,
    get_enforcement_source,
    set_enforcement_override,
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

    daily_rows: list[tuple[object, int, Decimal]] = []
    if bucket in {"day", "week", "month"}:
        dialect = db.bind.dialect.name if db.bind is not None else ""
        if bucket == "day":
            bucket_expr = func.date(LlmCallEvent.created_at)
        elif bucket == "week":
            if dialect == "sqlite":
                # Monday start-of-week date for SQLite test dialect.
                bucket_expr = func.date(
                    LlmCallEvent.created_at,
                    func.printf("-%d days", (func.strftime("%w", LlmCallEvent.created_at) + 6) % 7),
                )
            else:
                bucket_expr = func.date(func.date_trunc("week", LlmCallEvent.created_at))
        else:
            if dialect == "sqlite":
                bucket_expr = func.date(LlmCallEvent.created_at, "start of month")
            else:
                bucket_expr = func.date(func.date_trunc("month", LlmCallEvent.created_at))

        daily_query = select(
            bucket_expr,
            func.count(LlmCallEvent.id),
            func.coalesce(func.sum(LlmCallEvent.credits_burned), 0),
        )
        if conditions:
            daily_query = daily_query.where(*conditions)
        daily_query = daily_query.group_by(bucket_expr).order_by(bucket_expr.asc())
        daily_rows = (await db.execute(daily_query)).all()

    def _bucket_to_date(value: object) -> date:
        if isinstance(value, date):
            return value
        parsed = str(value)[:10]
        return date.fromisoformat(parsed)

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
            AdminUsageBucket(
                date=_bucket_to_date(row[0]),
                call_count=int(row[1]),
                credits_burned=format_decimal(Decimal(str(row[2]))),
            )
            for row in daily_rows
        ],
    )


@router.get("/analytics/usage", response_model=AdminUsageAnalyticsRead)
async def get_admin_usage_analytics(
    start_date: date = Query(...),
    end_date: date = Query(...),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUsageAnalyticsRead:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")

    window_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    window_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

    grouped = (
        select(
            LlmCallEvent.user_id.label("user_id"),
            LlmCallEvent.model_alias.label("model_alias"),
            func.coalesce(
                func.sum(LlmCallEvent.input_tokens_fresh + LlmCallEvent.input_tokens_cached),
                0,
            ).label("total_input_tokens"),
            func.coalesce(func.sum(LlmCallEvent.output_tokens), 0).label("total_output_tokens"),
            func.coalesce(func.sum(LlmCallEvent.credits_burned), 0).label("total_credits_burned"),
            func.count(LlmCallEvent.id).label("event_count"),
        )
        .where(
            LlmCallEvent.created_at >= window_start,
            LlmCallEvent.created_at < window_end,
        )
        .group_by(LlmCallEvent.user_id, LlmCallEvent.model_alias)
        .subquery()
    )

    total = int(await db.scalar(select(func.count()).select_from(grouped)) or 0)
    rows = (
        await db.execute(
            select(grouped)
            .order_by(grouped.c.total_credits_burned.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return AdminUsageAnalyticsRead(
        rows=[
            AdminUsageAnalyticsRowRead(
                user_id=str(row.user_id),
                model_alias=str(row.model_alias),
                total_input_tokens=int(row.total_input_tokens),
                total_output_tokens=int(row.total_output_tokens),
                total_credits_burned=format_decimal(Decimal(str(row.total_credits_burned))),
                event_count=int(row.event_count),
            )
            for row in rows
        ],
        total=total,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/analytics/active-users", response_model=AdminActiveUsersRead)
async def get_admin_active_users(
    window: Literal["day", "week", "month"] = Query(default="day"),
    as_of: date | None = Query(default=None),
    _: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminActiveUsersRead:
    as_of_date = as_of or datetime.now(timezone.utc).date()
    days_back = {"day": 0, "week": 6, "month": 29}[window]
    window_start_date = as_of_date - timedelta(days=days_back)
    window_start = datetime.combine(window_start_date, time.min, tzinfo=timezone.utc)
    window_end = datetime.combine(as_of_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

    active_users = int(
        await db.scalar(
            select(func.count(func.distinct(Session.started_by_user_id))).where(
                Session.deleted_at.is_(None),
                Session.created_at >= window_start,
                Session.created_at < window_end,
            )
        )
        or 0
    )

    first_seen_subquery = (
        select(
            Session.started_by_user_id.label("user_id"),
            func.min(Session.created_at).label("first_seen"),
        )
        .where(Session.deleted_at.is_(None))
        .group_by(Session.started_by_user_id)
        .subquery()
    )
    new_users = int(
        await db.scalar(
            select(func.count()).select_from(first_seen_subquery).where(
                first_seen_subquery.c.first_seen >= window_start,
                first_seen_subquery.c.first_seen < window_end,
            )
        )
        or 0
    )

    return AdminActiveUsersRead(
        window=window,
        as_of=as_of_date,
        active_users=active_users,
        new_users=new_users,
    )


@router.get("/settings", response_model=AdminSettingsRead)
async def get_admin_settings(
    _: dict[str, str] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> AdminSettingsRead:
    return AdminSettingsRead(
        enforcement_enabled=get_enforcement_enabled(settings.credit_enforcement_enabled),
        enforcement_source=get_enforcement_source(),
        low_balance_threshold=settings.low_balance_threshold,
        pricing_version=settings.pricing_version,
    )


@router.patch("/settings/enforcement", response_model=AdminEnforcementRead)
async def patch_enforcement_setting(
    payload: AdminEnforcementUpdate,
    _: dict[str, str] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> AdminEnforcementRead:
    set_enforcement_override(payload.enabled)
    return AdminEnforcementRead(
        enforcement_enabled=get_enforcement_enabled(settings.credit_enforcement_enabled),
        source=get_enforcement_source(),
    )


@router.delete("/settings/enforcement", response_model=AdminEnforcementRead)
async def clear_enforcement_setting(
    _: dict[str, str] = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> AdminEnforcementRead:
    set_enforcement_override(None)
    return AdminEnforcementRead(
        enforcement_enabled=get_enforcement_enabled(settings.credit_enforcement_enabled),
        source=get_enforcement_source(),
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


@router.post("/users/{user_id}/wallet/grant", response_model=AdminUserGrantResponse)
async def admin_grant_user_wallet_credits(
    user_id: str,
    payload: AdminGrantRequest,
    admin_user: dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
) -> AdminUserGrantResponse:
    result = await wallet_service.stage_grant(
        db=db,
        user_id=user_id,
        amount=payload.amount,
        note=payload.note,
        initiated_by=admin_user["user_id"],
    )
    await db.commit()
    return AdminUserGrantResponse(
        user_id=user_id,
        credits_granted=payload.amount,
        new_balance=format_decimal(result.new_balance),
    )

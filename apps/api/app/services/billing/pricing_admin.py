from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import ModelPricing, PricingVersion
from apps.api.app.services.usage.meter import reload_pricing_cache


async def get_active_pricing_version(db: AsyncSession) -> str:
    active_version = await db.scalar(
        select(PricingVersion.version)
        .where(PricingVersion.is_active.is_(True))
        .order_by(PricingVersion.effective_date.desc())
        .limit(1)
    )
    if active_version is None:
        raise ValueError("No active pricing version configured.")
    return active_version


async def list_model_pricing(db: AsyncSession, pricing_version: str) -> list[ModelPricing]:
    rows = await db.scalars(
        select(ModelPricing)
        .where(ModelPricing.pricing_version == pricing_version)
        .order_by(ModelPricing.model_alias.asc())
    )
    return rows.all()


async def update_model_multiplier(
    db: AsyncSession,
    model_alias: str,
    new_multiplier: float,
    pricing_version: str,
) -> ModelPricing:
    row = await db.scalar(
        select(ModelPricing).where(
            ModelPricing.pricing_version == pricing_version,
            ModelPricing.model_alias == model_alias,
        )
    )
    if row is None:
        raise ValueError("Model alias not found for pricing version.")

    row.multiplier = Decimal(str(new_multiplier))
    await db.commit()
    await db.refresh(row)

    active_rows = await list_model_pricing(db, pricing_version=pricing_version)
    reload_pricing_cache(
        {
            pricing.model_alias: float(pricing.multiplier)
            for pricing in active_rows
        }
    )
    return row

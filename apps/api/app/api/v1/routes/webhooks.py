from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import Settings, get_settings
from apps.api.app.db.models import CreditTransaction
from apps.api.app.db.session import get_db
from apps.api.app.services.billing.stripe_client import construct_webhook_event
from apps.api.app.services.billing.wallet import WalletService, get_wallet_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_LOGGER = logging.getLogger(__name__)


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    wallet_service: WalletService = Depends(get_wallet_service),
) -> dict[str, str]:
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    if settings.stripe_webhook_secret:
        try:
            event = construct_webhook_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.stripe_webhook_secret,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid stripe signature") from exc
    else:
        _LOGGER.warning("stripe webhook secret is not configured; signature verification skipped.")
        try:
            import json

            event = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=422, detail="malformed webhook payload") from exc

    event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    if event_type != "payment_intent.succeeded":
        return {"status": "ignored"}

    if isinstance(event, dict):
        obj = ((event.get("data") or {}).get("object") or {})
    else:
        obj = getattr(getattr(event, "data", None), "object", None) or {}
    payment_intent_id = obj.get("id")
    metadata = obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    credits_raw = metadata.get("credits")

    if not payment_intent_id or not user_id or credits_raw is None:
        raise HTTPException(status_code=422, detail="malformed webhook metadata")
    try:
        credits = float(credits_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="malformed webhook metadata") from exc

    existing = await db.scalar(
        select(CreditTransaction).where(CreditTransaction.reference_id == str(payment_intent_id))
    )
    if existing is not None:
        return {"status": "already_processed"}

    await wallet_service.stage_grant(
        db=db,
        user_id=str(user_id),
        amount=credits,
        note="stripe_topup",
        reference_id=str(payment_intent_id),
        initiated_by=None,
    )
    await db.commit()
    return {"status": "ok"}


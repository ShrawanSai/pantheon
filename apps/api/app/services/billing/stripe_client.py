from __future__ import annotations

import asyncio
import importlib
from typing import Any


def _import_stripe() -> Any:
    try:
        return importlib.import_module("stripe")
    except ModuleNotFoundError as exc:
        raise RuntimeError("stripe SDK is not installed.") from exc


async def create_payment_intent(
    *,
    api_key: str,
    amount_cents: int,
    currency: str,
    metadata: dict[str, str],
) -> Any:
    stripe = _import_stripe()
    stripe.api_key = api_key

    create_async = getattr(stripe.PaymentIntent, "create_async", None)
    if callable(create_async):
        return await create_async(
            amount=amount_cents,
            currency=currency,
            metadata=metadata,
        )

    return await asyncio.to_thread(
        stripe.PaymentIntent.create,
        amount=amount_cents,
        currency=currency,
        metadata=metadata,
    )


def construct_webhook_event(*, payload: bytes, sig_header: str, secret: str) -> Any:
    stripe = _import_stripe()
    return stripe.Webhook.construct_event(payload, sig_header, secret)


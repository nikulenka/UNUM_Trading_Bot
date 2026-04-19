from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from json import JSONDecodeError
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.core.config import Settings, get_settings

router = APIRouter(prefix="/alerts")
logger = logging.getLogger(__name__)


class TradingViewWebhookPayload(BaseModel):
    secret: str
    symbol: str
    action: str
    price: Decimal | None = None
    timeframe: str | None = None
    message: str | None = None
    timestamp: str | int | float | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("secret", "symbol")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("action")
    @classmethod
    def _validate_action(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("timeframe", "message")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("timestamp", mode="before")
    @classmethod
    def _normalize_timestamp(cls, value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None

        return str(value)


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _resolve_instrument_id(
    symbol: str,
    settings: Settings,
) -> str | None:
    normalized_symbol = _normalize_symbol(symbol)
    allowed_symbols = {
        _normalize_symbol(settings.primary_instrument_id),
        _normalize_symbol(settings.primary_gateio_symbol),
    }
    allowed_symbols.update(
        _normalize_symbol(alias) for alias in settings.primary_tradingview_aliases
    )

    if normalized_symbol in allowed_symbols:
        return settings.primary_instrument_id

    return None


def _build_payload_hash(payload: TradingViewWebhookPayload) -> str:
    sanitized_payload = payload.model_dump(
        exclude={"secret"},
        exclude_none=True,
    )
    canonical_payload = json.dumps(
        sanitized_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _build_signal_event(
    payload: TradingViewWebhookPayload,
    *,
    instrument_id: str,
) -> dict[str, str]:
    signal_event = {
        "event_type": "tradingview_signal",
        "instrument_id": instrument_id,
        "source_symbol": payload.symbol,
        "action": payload.action,
        "received_at_utc": datetime.now(UTC).isoformat(),
        "payload_hash": _build_payload_hash(payload),
    }

    if payload.price is not None:
        signal_event["price"] = str(payload.price)

    if payload.timeframe is not None:
        signal_event["timeframe"] = payload.timeframe

    if payload.message is not None:
        signal_event["message"] = payload.message

    if payload.timestamp is not None:
        signal_event["timestamp"] = payload.timestamp

    return signal_event


@router.post(
    "/tradingview",
    status_code=status.HTTP_202_ACCEPTED,
)
async def tradingview_webhook(request: Request) -> dict[str, str]:
    try:
        raw_payload = await request.json()
    except JSONDecodeError as exc:
        logger.warning(
            "TradingView webhook rejected due to invalid JSON",
            extra={"path": str(request.url.path)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid JSON payload",
        ) from exc

    try:
        payload = TradingViewWebhookPayload.model_validate(raw_payload)
    except ValidationError as exc:
        logger.warning(
            "TradingView webhook rejected due to invalid payload",
            extra={
                "path": str(request.url.path),
                "error_count": exc.error_count(),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    settings = get_settings()
    configured_secret = settings.tradingview_webhook_secret.strip()

    if not configured_secret:
        logger.error(
            "TradingView webhook rejected because secret is not configured",
            extra={
                "path": str(request.url.path),
                "source_symbol": payload.symbol,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trading webhook is not configured",
        )

    if payload.secret != configured_secret:
        logger.warning(
            "TradingView webhook rejected due to invalid secret",
            extra={
                "path": str(request.url.path),
                "source_symbol": payload.symbol,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid secret",
        )

    instrument_id = _resolve_instrument_id(payload.symbol, settings)
    if instrument_id is None:
        logger.warning(
            "TradingView webhook rejected due to unmapped symbol",
            extra={
                "path": str(request.url.path),
                "source_symbol": payload.symbol,
                "action": payload.action,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unmapped symbol: {payload.symbol}",
        )

    signal_event = _build_signal_event(
        payload,
        instrument_id=instrument_id,
    )
    redis_client = redis.from_url(
        settings.redis_dsn,
        decode_responses=True,
    )

    try:
        event_id = await redis_client.xadd(
            settings.signal_events_stream,
            signal_event,
            maxlen=10000,
        )
    except redis.RedisError as exc:
        logger.exception(
            "TradingView webhook publish failed",
            extra={
                "instrument_id": instrument_id,
                "source_symbol": payload.symbol,
                "action": payload.action,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="signal publication unavailable",
        ) from exc
    finally:
        await redis_client.aclose()

    logger.info(
        "TradingView webhook accepted",
        extra={
            "instrument_id": instrument_id,
            "source_symbol": payload.symbol,
            "action": payload.action,
            "event_id": event_id,
            "signal_stream": settings.signal_events_stream,
        },
    )
    return {
        "status": "accepted",
        "event_id": event_id,
    }

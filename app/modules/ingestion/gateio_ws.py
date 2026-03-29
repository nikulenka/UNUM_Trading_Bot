from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import UTC, datetime
from typing import Any, AsyncGenerator, Final

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from app.modules.ingestion.gateio_rest import GateIOClientError

logger = logging.getLogger(__name__)

DEFAULT_GATEIO_WS_URL: Final[str] = "wss://api.gateio.ws/ws/v4/"
DEFAULT_WS_RECONNECT_DELAY: Final[float] = 5.0
DEFAULT_WS_MAX_RECONNECT_DELAY: Final[float] = 60.0


class GateIOWebSocketError(GateIOClientError):
    """Raised when WebSocket connection or message handling fails."""


class GateIOWebSocketClient:
    """Async WebSocket client for Gate.io spot ticker and trade data."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_GATEIO_WS_URL,
        reconnect_delay: float = DEFAULT_WS_RECONNECT_DELAY,
        max_reconnect_delay: float = DEFAULT_WS_MAX_RECONNECT_DELAY,
        user_agent: str = "ai-bot/1.0",
    ) -> None:
        self._base_url = base_url if base_url.endswith("/") else base_url + "/"
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._current_reconnect_delay = reconnect_delay
        self._headers = {"User-Agent": user_agent}

    async def subscribe_market_data(
        self,
        currency_pair: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Connect to WS and yield ticker/trade events for the given pair."""

        if not currency_pair:
            raise ValueError("currency_pair must not be empty")

        while True:
            try:
                connect_kwargs: dict[str, Any] = {}
                if "additional_headers" in inspect.signature(websockets.connect).parameters:
                    connect_kwargs["additional_headers"] = self._headers
                else:
                    connect_kwargs["extra_headers"] = self._headers

                async with websockets.connect(
                    self._base_url,
                    **connect_kwargs,
                ) as ws:
                    # Subscribe to ticker
                    ticker_msg = {
                        "time": int(datetime.now().timestamp()),
                        "channel": "spot.tickers",
                        "event": "subscribe",
                        "payload": [currency_pair],
                    }
                    await ws.send(json.dumps(ticker_msg))

                    # Subscribe to trades
                    trade_msg = {
                        "time": int(datetime.now().timestamp()),
                        "channel": "spot.trades",
                        "event": "subscribe",
                        "payload": [currency_pair],
                    }
                    await ws.send(json.dumps(trade_msg))

                    logger.info(f"Subscribed to ticker and trades for {currency_pair}")

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            event = self._parse_ws_message(data, currency_pair)
                            if event:
                                # Reset reconnect delay on successful message
                                self._current_reconnect_delay = self._reconnect_delay
                                yield event
                        except json.JSONDecodeError as exc:
                            logger.warning(f"Invalid JSON in WS message: {exc}")
                        except Exception as exc:
                            logger.error(f"Error parsing WS message: {exc}")

            except ConnectionClosed as exc:
                logger.warning(f"WebSocket closed: {exc}. Reconnecting...")
            except InvalidStatus as exc:
                logger.error(f"WebSocket invalid status: {exc}. Reconnecting...")
            except Exception as exc:
                logger.error(f"Unexpected WS error: {exc}. Reconnecting...")

            # Exponential backoff with max cap
            await asyncio.sleep(self._current_reconnect_delay)
            self._current_reconnect_delay = min(
                self._current_reconnect_delay * 2,
                self._max_reconnect_delay,
            )

    def _parse_ws_message(
        self, data: dict[str, Any], currency_pair: str
    ) -> dict[str, Any] | None:
        """Parse WebSocket message into normalized event."""
        if not isinstance(data, dict):
            return None

        event_type = data.get("event")
        if event_type != "update":
            return None

        channel = data.get("channel", "")
        payload = data.get("result", {})

        if not isinstance(payload, dict):
            return None

        ingested_at_utc = datetime.now(UTC)

        if channel == "spot.tickers":
            return self._normalize_ticker(payload, currency_pair, ingested_at_utc)
        elif channel == "spot.trades":
            return self._normalize_trade(payload, currency_pair, ingested_at_utc)

        return None

    def _normalize_ticker(
        self, payload: dict[str, Any], currency_pair: str, ingested_at_utc: datetime
    ) -> dict[str, Any] | None:
        """Normalize ticker event."""
        try:
            return {
                "event_type": "ticker",
                "instrument_id": currency_pair,
                "source_symbol": payload.get("currency_pair", currency_pair),
                "source_time_utc": self._parse_timestamp(payload.get("t")),
                "ingested_at_utc": ingested_at_utc.isoformat(),
                "payload": json.dumps(payload),
            }
        except Exception as exc:
            logger.warning(f"Failed to parse ticker: {exc}")
            return None

    def _normalize_trade(
        self, payload: dict[str, Any], currency_pair: str, ingested_at_utc: datetime
    ) -> dict[str, Any] | None:
        """Normalize trade event."""
        try:
            return {
                "event_type": "trade",
                "instrument_id": currency_pair,
                "source_symbol": payload.get("currency_pair", currency_pair),
                "source_time_utc": self._parse_timestamp(payload.get("t")),
                "ingested_at_utc": ingested_at_utc.isoformat(),
                "payload": json.dumps(payload),
            }
        except Exception as exc:
            logger.warning(f"Failed to parse trade: {exc}")
            return None

    def _parse_timestamp(self, raw_value: Any) -> str:
        """Parse timestamp to ISO format UTC string."""
        try:
            dt = datetime.fromtimestamp(int(str(raw_value)), tz=UTC)
            return dt.isoformat()
        except (TypeError, ValueError):
            return datetime.now(UTC).isoformat()


__all__ = [
    "GateIOWebSocketClient",
    "GateIOWebSocketError",
    "DEFAULT_GATEIO_WS_URL",
]

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_GATEIO_API_BASE_URL: Final[str] = "https://api.gateio.ws/api/v4"
DEFAULT_GATEIO_TIMEOUT_SECONDS: Final[float] = 10.0


class GateIOClientError(RuntimeError):
    """Base exception for Gate.io client failures."""


class GateIORequestError(GateIOClientError):
    """Raised when the Gate.io API request fails."""


class GateIOResponseError(GateIOClientError):
    """Raised when the Gate.io API response cannot be parsed."""


@dataclass(frozen=True, slots=True)
class HistoricalCandle:
    open_time_utc: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    base_volume: Decimal
    quote_volume: Decimal | None = None
    is_closed: bool | None = None


class GateIOHistoricalCandlesClient:
    """Minimal REST client for Gate.io spot historical candlesticks."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_GATEIO_API_BASE_URL,
        timeout_seconds: float = DEFAULT_GATEIO_TIMEOUT_SECONDS,
        user_agent: str = "ai-bot/1.0",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._headers = {
            "Accept": "application/json",
            "User-Agent": user_agent,
        }

    def get_candles(
        self,
        currency_pair: str,
        interval: str = "15m",
        *,
        limit: int | None = None,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
    ) -> list[HistoricalCandle]:
        if not currency_pair:
            raise ValueError("currency_pair must not be empty")

        if not interval:
            raise ValueError("interval must not be empty")

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than zero")

        if (
            from_timestamp is not None
            and to_timestamp is not None
            and from_timestamp > to_timestamp
        ):
            raise ValueError(
                "from_timestamp must be less than or equal to to_timestamp"
            )

        params: dict[str, str] = {
            "currency_pair": currency_pair,
            "interval": interval,
        }
        if limit is not None:
            params["limit"] = str(limit)
        if from_timestamp is not None:
            params["from"] = str(from_timestamp)
        if to_timestamp is not None:
            params["to"] = str(to_timestamp)

        payload = self._get_json("/spot/candlesticks", params)
        if not isinstance(payload, list):
            raise GateIOResponseError(
                "Gate.io historical candles response must be a JSON array"
            )

        candles = [self._parse_candle(raw_candle) for raw_candle in payload]
        candles = [candle for candle in candles if candle.is_closed is not False]
        return sorted(candles, key=lambda candle: candle.open_time_utc)

    def _get_json(self, path: str, params: dict[str, str]) -> Any:
        url = f"{self._base_url}{path}?{urlencode(params)}"
        request = Request(url=url, headers=self._headers, method="GET")

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise GateIORequestError(
                f"Gate.io request failed with status {exc.code}: {message}"
            ) from exc
        except URLError as exc:
            raise GateIORequestError(
                f"Gate.io request failed: {exc.reason}"
            ) from exc

        if status != 200:
            raise GateIORequestError(
                f"Gate.io request returned unexpected status {status}: {body}"
            )

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise GateIOResponseError(
                "Gate.io response body is not valid JSON"
            ) from exc

    def _parse_candle(self, raw_candle: Any) -> HistoricalCandle:
        if isinstance(raw_candle, dict):
            return self._parse_mapping_candle(raw_candle)

        if isinstance(raw_candle, (list, tuple)):
            return self._parse_sequence_candle(raw_candle)

        raise GateIOResponseError(
            f"Unsupported Gate.io candle payload type: {type(raw_candle).__name__}"
        )

    def _parse_mapping_candle(
        self, raw_candle: dict[str, Any]
    ) -> HistoricalCandle:
        try:
            timestamp = raw_candle["t"]
            base_volume = raw_candle["v"]
            close_price = raw_candle["c"]
            high_price = raw_candle["h"]
            low_price = raw_candle["l"]
            open_price = raw_candle["o"]
        except KeyError as exc:
            missing_field = exc.args[0]
            raise GateIOResponseError(
                f"Missing Gate.io candle field: {missing_field}"
            ) from exc

        return HistoricalCandle(
            open_time_utc=self._parse_timestamp(timestamp),
            open_price=self._parse_decimal(open_price, field_name="o"),
            high_price=self._parse_decimal(high_price, field_name="h"),
            low_price=self._parse_decimal(low_price, field_name="l"),
            close_price=self._parse_decimal(close_price, field_name="c"),
            base_volume=self._parse_decimal(base_volume, field_name="v"),
            quote_volume=self._parse_optional_decimal(
                raw_candle.get("sum"),
                field_name="sum",
            ),
            is_closed=self._parse_optional_bool(
                raw_candle.get("is_closed", raw_candle.get("closed"))
            ),
        )

    def _parse_sequence_candle(
        self, raw_candle: list[Any] | tuple[Any, ...]
    ) -> HistoricalCandle:
        if len(raw_candle) < 6:
            raise GateIOResponseError(
                "Gate.io candle array must contain at least 6 values"
            )

        timestamp, base_volume, close_price, high_price, low_price, open_price, *rest = (
            raw_candle
        )

        quote_volume: Decimal | None = None
        is_closed: bool | None = None

        if rest:
            first_extra = rest[0]
            if len(rest) == 1 and self._looks_like_bool(first_extra):
                is_closed = self._parse_optional_bool(first_extra)
            else:
                quote_volume = self._parse_optional_decimal(
                    first_extra,
                    field_name="quote_volume",
                )
                if len(rest) > 1:
                    is_closed = self._parse_optional_bool(rest[1])

        return HistoricalCandle(
            open_time_utc=self._parse_timestamp(timestamp),
            open_price=self._parse_decimal(open_price, field_name="open_price"),
            high_price=self._parse_decimal(high_price, field_name="high_price"),
            low_price=self._parse_decimal(low_price, field_name="low_price"),
            close_price=self._parse_decimal(close_price, field_name="close_price"),
            base_volume=self._parse_decimal(
                base_volume,
                field_name="base_volume",
            ),
            quote_volume=quote_volume,
            is_closed=is_closed,
        )

    def _parse_timestamp(self, raw_value: Any) -> datetime:
        try:
            return datetime.fromtimestamp(int(str(raw_value)), tz=UTC)
        except (TypeError, ValueError) as exc:
            raise GateIOResponseError(
                f"Invalid Gate.io candle timestamp: {raw_value!r}"
            ) from exc

    def _parse_decimal(self, raw_value: Any, *, field_name: str) -> Decimal:
        try:
            return Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise GateIOResponseError(
                f"Invalid decimal value for {field_name}: {raw_value!r}"
            ) from exc

    def _parse_optional_decimal(
        self, raw_value: Any, *, field_name: str
    ) -> Decimal | None:
        if raw_value in (None, ""):
            return None

        return self._parse_decimal(raw_value, field_name=field_name)

    def _parse_optional_bool(self, raw_value: Any) -> bool | None:
        if raw_value in (None, ""):
            return None

        if isinstance(raw_value, bool):
            return raw_value

        normalized = str(raw_value).strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False

        raise GateIOResponseError(
            f"Invalid boolean value in Gate.io candle payload: {raw_value!r}"
        )

    def _looks_like_bool(self, raw_value: Any) -> bool:
        if isinstance(raw_value, bool):
            return True

        return str(raw_value).strip().lower() in {"true", "false"}


__all__ = [
    "GateIOClientError",
    "GateIOHistoricalCandlesClient",
    "GateIORequestError",
    "GateIOResponseError",
    "HistoricalCandle",
]

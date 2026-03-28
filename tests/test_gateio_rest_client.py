import json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest

from app.modules.ingestion.gateio_rest import (
    GateIOHistoricalCandlesClient,
    GateIOResponseError,
)


class FakeHTTPResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_get_candles_builds_request_and_returns_sorted_candles() -> None:
    client = GateIOHistoricalCandlesClient()
    response = FakeHTTPResponse(
        [
            ["1700000900", "5.5", "102.0", "103.0", "101.0", "100.0"],
            ["1700000000", "7.5", "100.0", "101.0", "99.0", "98.0"],
        ]
    )

    with patch(
        "app.modules.ingestion.gateio_rest.urlopen",
        return_value=response,
    ) as mocked_urlopen:
        candles = client.get_candles(
            "BTC_USDT",
            interval="15m",
            limit=2,
            from_timestamp=1700000000,
            to_timestamp=1700001800,
        )

    request = mocked_urlopen.call_args.args[0]
    query = parse_qs(urlparse(request.full_url).query)

    assert query == {
        "currency_pair": ["BTC_USDT"],
        "interval": ["15m"],
        "limit": ["2"],
        "from": ["1700000000"],
        "to": ["1700001800"],
    }
    assert [candle.open_price for candle in candles] == [
        Decimal("98.0"),
        Decimal("100.0"),
    ]
    assert candles[0].base_volume == Decimal("7.5")
    assert candles[1].close_price == Decimal("102.0")


def test_get_candles_parses_mapping_payload() -> None:
    client = GateIOHistoricalCandlesClient()
    response = FakeHTTPResponse(
        [
            {
                "t": "1700000000",
                "v": "12.5",
                "c": "101.0",
                "h": "102.0",
                "l": "99.5",
                "o": "100.0",
                "sum": "1262.5",
                "is_closed": "true",
            }
        ]
    )

    with patch("app.modules.ingestion.gateio_rest.urlopen", return_value=response):
        candles = client.get_candles("BTC_USDT")

    candle = candles[0]

    assert candle.quote_volume == Decimal("1262.5")
    assert candle.is_closed is True
    assert candle.high_price == Decimal("102.0")


def test_get_candles_skips_open_candles() -> None:
    client = GateIOHistoricalCandlesClient()
    response = FakeHTTPResponse(
        [
            ["1700000000", "7.5", "100.0", "101.0", "99.0", "98.0", True],
            ["1700000600", "8.5", "101.0", "102.0", "100.0", "99.0", False],
        ]
    )

    with patch("app.modules.ingestion.gateio_rest.urlopen", return_value=response):
        candles = client.get_candles("BTC_USDT")

    assert len(candles) == 1
    assert candles[0].open_price == Decimal("98.0")
    assert candles[0].is_closed is True


def test_get_candles_rejects_non_array_payload() -> None:
    client = GateIOHistoricalCandlesClient()
    response = FakeHTTPResponse({"unexpected": "object"})

    with patch("app.modules.ingestion.gateio_rest.urlopen", return_value=response):
        with pytest.raises(
            GateIOResponseError,
            match="response must be a JSON array",
        ):
            client.get_candles("BTC_USDT")

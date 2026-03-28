
from app.modules.ingestion.gateio_ws import GateIOWebSocketClient


def test_parse_ws_message_returns_ticker_event() -> None:
    client = GateIOWebSocketClient()
    data = {
        "event": "update",
        "channel": "spot.tickers",
        "result": {
            "currency_pair": "BTC_USDT",
            "t": 1700000000,
            "last": "50000.00",
        },
    }
    event = client._parse_ws_message(data, "BTC_USDT")
    assert event is not None
    assert event["event_type"] == "ticker"
    assert event["instrument_id"] == "BTC_USDT"


def test_parse_ws_message_returns_trade_event() -> None:
    client = GateIOWebSocketClient()
    data = {
        "event": "update",
        "channel": "spot.trades",
        "result": {
            "currency_pair": "BTC_USDT",
            "t": 1700000000,
            "id": 12345,
            "price": "50000.00",
        },
    }
    event = client._parse_ws_message(data, "BTC_USDT")
    assert event is not None
    assert event["event_type"] == "trade"
    assert event["instrument_id"] == "BTC_USDT"


def test_parse_ws_message_skips_non_update_events() -> None:
    client = GateIOWebSocketClient()
    data = {"event": "subscribe", "channel": "spot.tickers"}
    event = client._parse_ws_message(data, "BTC_USDT")
    assert event is None


def test_parse_ws_message_skips_unknown_channel() -> None:
    client = GateIOWebSocketClient()
    data = {
        "event": "update",
        "channel": "spot.unknown",
        "result": {},
    }
    event = client._parse_ws_message(data, "BTC_USDT")
    assert event is None

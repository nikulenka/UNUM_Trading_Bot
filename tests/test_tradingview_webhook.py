from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.tradingview as tradingview_module
from app.api.tradingview import router


class FakeRedisClient:
    def __init__(self) -> None:
        self.xadd_calls: list[tuple[str, dict[str, str], int | None]] = []
        self.closed = False

    async def xadd(
        self,
        stream_name: str,
        mapping: dict[str, str],
        maxlen: int | None = None,
    ) -> str:
        self.xadd_calls.append((stream_name, mapping, maxlen))
        return "1743336000-0"

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        yield client


@pytest.fixture
def fake_settings(monkeypatch):
    settings = SimpleNamespace(
        tradingview_webhook_secret="top-secret",
        primary_instrument_id="BTC_USDT",
        primary_gateio_symbol="BTC_USDT",
        primary_tradingview_aliases=("BTCUSDT", "BTC/USDT", "BTC_USDT"),
        signal_events_stream="signal.events",
        redis_dsn="redis://127.0.0.1:6379/0",
    )
    monkeypatch.setattr(tradingview_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def fake_redis_client(monkeypatch):
    client = FakeRedisClient()
    monkeypatch.setattr(
        tradingview_module.redis,
        "from_url",
        lambda *args, **kwargs: client,
    )
    return client


@pytest.mark.integration
def test_tradingview_webhook_publishes_signal_event(
    api_client,
    fake_settings,
    fake_redis_client,
) -> None:
    response = api_client.post(
        "/alerts/tradingview",
        json={
            "secret": "top-secret",
            "symbol": "BTCUSDT",
            "action": "BUY",
            "price": "50000.50",
            "timeframe": "15m",
            "message": "enter long",
            "timestamp": "2026-03-29T12:00:00Z",
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "event_id": "1743336000-0",
    }

    assert fake_redis_client.closed is True
    assert len(fake_redis_client.xadd_calls) == 1

    stream_name, event, maxlen = fake_redis_client.xadd_calls[0]
    assert stream_name == fake_settings.signal_events_stream
    assert maxlen == 10000
    assert event["event_type"] == "tradingview_signal"
    assert event["instrument_id"] == "BTC_USDT"
    assert event["source_symbol"] == "BTCUSDT"
    assert event["action"] == "buy"
    assert event["price"] == "50000.50"
    assert event["timeframe"] == "15m"
    assert event["message"] == "enter long"
    assert event["timestamp"] == "2026-03-29T12:00:00Z"
    assert "received_at_utc" in event
    assert "payload_hash" in event
    assert "secret" not in event


@pytest.mark.unit
def test_tradingview_webhook_rejects_invalid_secret(
    api_client,
    fake_redis_client,
    fake_settings,
) -> None:
    response = api_client.post(
        "/alerts/tradingview",
        json={
            "secret": "wrong-secret",
            "symbol": "BTCUSDT",
            "action": "buy",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "invalid secret"}
    assert fake_redis_client.xadd_calls == []


@pytest.mark.unit
def test_tradingview_webhook_rejects_unmapped_symbol(
    api_client,
    fake_redis_client,
    fake_settings,
) -> None:
    response = api_client.post(
        "/alerts/tradingview",
        json={
            "secret": "top-secret",
            "symbol": "ETHUSDT",
            "action": "sell",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "unmapped symbol: ETHUSDT"}
    assert fake_redis_client.xadd_calls == []


@pytest.mark.unit
def test_tradingview_webhook_rejects_invalid_json(api_client) -> None:
    response = api_client.post(
        "/alerts/tradingview",
        content="{",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid JSON payload"}


@pytest.mark.unit
def test_tradingview_webhook_rejects_unexpected_fields(
    api_client,
    fake_redis_client,
    fake_settings,
) -> None:
    response = api_client.post(
        "/alerts/tradingview",
        json={
            "secret": "top-secret",
            "symbol": "BTCUSDT",
            "action": "buy",
            "unexpected": "value",
        },
    )

    assert response.status_code == 422
    assert fake_redis_client.xadd_calls == []
    assert response.json()["detail"][0]["type"] == "extra_forbidden"

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.ingestion.backfill import persist_successful_backfill_batch
from app.modules.ingestion.gateio_rest import HistoricalCandle
from app.modules.persistence.models import BackfillState, BackfillStatus


class FakeBackfillSession:
    def __init__(self) -> None:
        self.executed_statements: list[object] = []
        self.added_instances: list[object] = []
        self.committed = False

    def add(self, instance: object) -> None:
        self.added_instances.append(instance)

    async def execute(self, statement: object) -> None:
        self.executed_statements.append(statement)

    async def commit(self) -> None:
        self.committed = True


def _build_state() -> BackfillState:
    return BackfillState(
        instrument_id="BTC_USDT",
        timeframe="15m",
        requested_start_utc=datetime(2026, 3, 25, 0, 0, tzinfo=UTC),
        requested_end_utc=datetime(2026, 3, 25, 0, 30, tzinfo=UTC),
        status=BackfillStatus.PENDING,
    )


def _build_candle(open_time: datetime, open_price: str) -> HistoricalCandle:
    price = Decimal(open_price)
    return HistoricalCandle(
        open_time_utc=open_time,
        open_price=price,
        high_price=price + Decimal("1"),
        low_price=price - Decimal("1"),
        close_price=price + Decimal("0.5"),
        base_volume=Decimal("10"),
        quote_volume=Decimal("100"),
        is_closed=True,
    )


def test_backfill_batch_updates_state_after_commit() -> None:
    state = _build_state()
    session = FakeBackfillSession()
    candles = [
        _build_candle(datetime(2026, 3, 25, 0, 0, tzinfo=UTC), "100"),
        _build_candle(datetime(2026, 3, 25, 0, 15, tzinfo=UTC), "101"),
    ]

    result = asyncio.run(
        persist_successful_backfill_batch(
            session,
            state,
            candles,
        )
    )

    assert session.committed is True
    assert len(session.executed_statements) == 1
    assert session.added_instances == [state]
    assert state.last_completed_candle_open_time_utc == candles[-1].open_time_utc
    assert state.status == BackfillStatus.RUNNING
    assert state.last_error is None
    assert result.candles_processed == 2
    assert result.last_completed_candle_open_time_utc == candles[-1].open_time_utc


def test_backfill_batch_rejects_open_candles() -> None:
    state = _build_state()
    session = FakeBackfillSession()
    open_candle = HistoricalCandle(
        open_time_utc=datetime(2026, 3, 25, 0, 0, tzinfo=UTC),
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100.5"),
        base_volume=Decimal("10"),
        quote_volume=Decimal("100"),
        is_closed=False,
    )

    with pytest.raises(ValueError, match="closed candles only"):
        asyncio.run(
            persist_successful_backfill_batch(
                session,
                state,
                [open_candle],
            )
        )

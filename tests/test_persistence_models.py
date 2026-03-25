from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint

from app.modules.persistence.base import Base
from app.modules.persistence.models import BackfillState, BackfillStatus, OHLCVCandle


def test_persistence_tables_are_registered_in_metadata() -> None:
    assert "ohlcv_candles" in Base.metadata.tables
    assert "backfill_state" in Base.metadata.tables


def test_ohlcv_candles_has_expected_unique_constraint() -> None:
    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in OHLCVCandle.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert (
        "instrument_id",
        "timeframe",
        "open_time_utc",
    ) in unique_constraints


def test_backfill_state_has_expected_shape() -> None:
    table = BackfillState.__table__

    assert table.c.requested_start_utc.nullable is False
    assert table.c.last_completed_candle_open_time_utc.nullable is True
    assert table.c.last_error.nullable is True
    assert table.c.status.default.arg == BackfillStatus.PENDING


def test_backfill_state_marks_successful_batch() -> None:
    state = BackfillState(
        instrument_id="BTC_USDT",
        timeframe="15m",
        requested_start_utc=datetime(2026, 3, 25, 0, 0, tzinfo=UTC),
        requested_end_utc=datetime(2026, 3, 25, 1, 0, tzinfo=UTC),
        status=BackfillStatus.PENDING,
    )
    completed_at = datetime(2026, 3, 25, 0, 15, tzinfo=UTC)

    state.mark_successful_batch(completed_at)

    assert state.last_completed_candle_open_time_utc == completed_at
    assert state.status == BackfillStatus.RUNNING
    assert state.last_error is None

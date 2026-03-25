from __future__ import annotations

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

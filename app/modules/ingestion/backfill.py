"""Utilities for persisting historical Gate.io backfill batches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, Sequence

from sqlalchemy.dialects.postgresql import insert

from app.modules.ingestion.gateio_rest import HistoricalCandle
from app.modules.persistence.models import BackfillState, OHLCVCandle

BACKFILL_CANDLE_INDEX_COLUMNS: Final[tuple[str, str, str]] = (
    "instrument_id",
    "timeframe",
    "open_time_utc",
)


class BackfillSession(Protocol):
    """Minimal session protocol used by the backfill batch writer."""

    def add(self, instance: object) -> None:
        ...

    async def execute(self, statement: Any) -> Any:
        ...

    async def commit(self) -> None:
        ...


@dataclass(frozen=True, slots=True)
class BackfillBatchResult:
    """Summary for a successfully processed historical candle batch."""

    candles_processed: int
    last_completed_candle_open_time_utc: datetime


class BackfillBatchWriter:
    """Persist a batch of closed candles and advance backfill progress."""

    async def write_successful_batch(
        self,
        session: BackfillSession,
        state: BackfillState,
        candles: Sequence[HistoricalCandle],
    ) -> BackfillBatchResult:
        ordered_candles = sorted(candles, key=lambda candle: candle.open_time_utc)

        if not ordered_candles:
            raise ValueError("candles must not be empty")

        if any(candle.is_closed is False for candle in ordered_candles):
            raise ValueError("backfill batches must contain closed candles only")

        rows = [self._to_row(state, candle) for candle in ordered_candles]
        statement = (
            insert(OHLCVCandle)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=list(BACKFILL_CANDLE_INDEX_COLUMNS)
            )
        )
        await session.execute(statement)

        last_completed_candle_open_time_utc = ordered_candles[-1].open_time_utc
        state.mark_successful_batch(last_completed_candle_open_time_utc)
        session.add(state)
        await session.commit()

        return BackfillBatchResult(
            candles_processed=len(ordered_candles),
            last_completed_candle_open_time_utc=last_completed_candle_open_time_utc,
        )

    def _to_row(
        self,
        state: BackfillState,
        candle: HistoricalCandle,
    ) -> dict[str, Any]:
        return {
            "instrument_id": state.instrument_id,
            "timeframe": state.timeframe,
            "open_time_utc": candle.open_time_utc,
            "open_price": candle.open_price,
            "high_price": candle.high_price,
            "low_price": candle.low_price,
            "close_price": candle.close_price,
            "base_volume": candle.base_volume,
            "quote_volume": candle.quote_volume,
        }


async def persist_successful_backfill_batch(
    session: BackfillSession,
    state: BackfillState,
    candles: Sequence[HistoricalCandle],
) -> BackfillBatchResult:
    """Convenience wrapper for persisting one successful batch."""

    return await BackfillBatchWriter().write_successful_batch(session, state, candles)


__all__ = [
    "BackfillBatchResult",
    "BackfillBatchWriter",
    "BackfillSession",
    "persist_successful_backfill_batch",
]

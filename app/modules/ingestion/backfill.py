"""Utilities for persisting and running a manual Gate.io backfill."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import validate_settings
from app.modules.ingestion.gateio_rest import (
    GateIOHistoricalCandlesClient,
    HistoricalCandle,
)
from app.modules.persistence.models import BackfillState, BackfillStatus, OHLCVCandle

DEFAULT_BACKFILL_BATCH_LIMIT: Final[int] = 100
DEFAULT_BACKFILL_INSTRUMENT_ID: Final[str] = "BTC_USDT"
# Keep the manual runner conservative so it stays well below API limits.
DEFAULT_BACKFILL_REQUEST_DELAY_SECONDS: Final[float] = 3.0
DEFAULT_BACKFILL_TIMEFRAME: Final[str] = "15m"
BACKFILL_TIMEFRAME_SECONDS: Final[dict[str, int]] = {
    "15m": 15 * 60,
}

logger = logging.getLogger(__name__)

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


def _resolve_logging_level(log_level: str | None) -> int:
    if log_level is None:
        return logging.INFO

    normalized_log_level = str(log_level).strip()
    if not normalized_log_level:
        return logging.INFO

    if normalized_log_level.isdigit():
        return int(normalized_log_level)

    return getattr(logging, normalized_log_level.upper(), logging.INFO)


def _configure_logging(log_level: str | None) -> None:
    logging.basicConfig(
        level=_resolve_logging_level(log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )


def _parse_non_empty_string(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise argparse.ArgumentTypeError("Value must not be empty")

    return value


def _parse_utc_datetime(raw_value: str) -> datetime:
    normalized_value = raw_value.strip()
    if not normalized_value:
        raise ValueError("datetime value must not be empty")

    if normalized_value.endswith("Z"):
        normalized_value = normalized_value[:-1] + "+00:00"

    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        parsed_value = parsed_value.replace(tzinfo=UTC)

    return parsed_value.astimezone(UTC)


def _parse_utc_datetime_arg(raw_value: str) -> datetime:
    try:
        return _parse_utc_datetime(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_positive_int(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid integer value: {raw_value!r}"
        ) from exc

    if value <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero")

    return value


def _parse_non_negative_float(raw_value: str) -> float:
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid number value: {raw_value!r}"
        ) from exc

    if value < 0:
        raise argparse.ArgumentTypeError("Value must be zero or greater")

    return value


def _get_interval_seconds(timeframe: str) -> int:
    try:
        return BACKFILL_TIMEFRAME_SECONDS[timeframe]
    except KeyError as exc:
        supported_timeframes = ", ".join(sorted(BACKFILL_TIMEFRAME_SECONDS))
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}; supported timeframes: "
            f"{supported_timeframes}"
        ) from exc


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the manual backfill command."""

    parser = argparse.ArgumentParser(
        prog="backfill",
        description=(
            "Backfill closed Gate.io candles into Postgres with a deliberate "
            "delay between requests to stay gentle on the API."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--instrument-id",
        type=_parse_non_empty_string,
        default=DEFAULT_BACKFILL_INSTRUMENT_ID,
        help="Internal instrument identifier / Gate.io currency pair to backfill.",
    )
    parser.add_argument(
        "--timeframe",
        default=DEFAULT_BACKFILL_TIMEFRAME,
        choices=sorted(BACKFILL_TIMEFRAME_SECONDS),
        help="Candle timeframe to backfill.",
    )
    parser.add_argument(
        "--start-utc",
        type=_parse_utc_datetime_arg,
        default=None,
        help=(
            "Start timestamp in UTC ISO-8601 format. Required on first run "
            "when no backfill state exists yet."
        ),
    )
    parser.add_argument(
        "--end-utc",
        type=_parse_utc_datetime_arg,
        default=None,
        help=(
            "End timestamp in UTC ISO-8601 format. Defaults to the latest "
            "closed candle boundary when omitted."
        ),
    )
    parser.add_argument(
        "--batch-limit",
        type=_parse_positive_int,
        default=DEFAULT_BACKFILL_BATCH_LIMIT,
        help="Maximum number of candles to request per API call.",
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=_parse_non_negative_float,
        default=DEFAULT_BACKFILL_REQUEST_DELAY_SECONDS,
        help=(
            "Seconds to sleep between API requests so the manual runner stays "
            "slow and conservative."
        ),
    )
    return parser


def _default_requested_end_utc(interval_seconds: int) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=interval_seconds)


async def _load_or_create_backfill_state(
    session: AsyncSession,
    *,
    instrument_id: str,
    timeframe: str,
    start_utc: datetime | None,
    end_utc: datetime | None,
    default_end_utc: datetime,
) -> BackfillState:
    state = await session.scalar(
        select(BackfillState).where(
            BackfillState.instrument_id == instrument_id,
            BackfillState.timeframe == timeframe,
        )
    )

    if state is None:
        if start_utc is None:
            raise ValueError(
                "--start-utc is required when no backfill state exists yet"
            )

        resolved_end_utc = end_utc or default_end_utc
        if resolved_end_utc <= start_utc:
            raise ValueError("--end-utc must be later than --start-utc")

        state = BackfillState(
            instrument_id=instrument_id,
            timeframe=timeframe,
            requested_start_utc=start_utc,
            requested_end_utc=resolved_end_utc,
            status=BackfillStatus.PENDING,
        )
        session.add(state)
        await session.commit()
        return state

    if start_utc is not None and state.requested_start_utc != start_utc:
        raise ValueError(
            f"Existing backfill state for {instrument_id} {timeframe} uses "
            f"start {state.requested_start_utc.isoformat()}, not "
            f"{start_utc.isoformat()}"
        )

    if end_utc is not None and state.requested_end_utc is not None:
        if state.requested_end_utc != end_utc:
            raise ValueError(
                f"Existing backfill state for {instrument_id} {timeframe} uses "
                f"end {state.requested_end_utc.isoformat()}, not "
                f"{end_utc.isoformat()}"
            )

    if state.requested_end_utc is None:
        resolved_end_utc = end_utc or default_end_utc
        if resolved_end_utc <= state.requested_start_utc:
            raise ValueError("--end-utc must be later than --start-utc")

        state.requested_end_utc = resolved_end_utc
        session.add(state)
        await session.commit()

    return state


async def _set_backfill_status(
    session: AsyncSession,
    state: BackfillState,
    status: BackfillStatus,
    *,
    last_error: str | None = None,
) -> None:
    state.status = status
    state.last_error = last_error
    session.add(state)
    await session.commit()


def _next_backfill_cursor(
    state: BackfillState,
    interval_seconds: int,
) -> datetime:
    if state.last_completed_candle_open_time_utc is None:
        return state.requested_start_utc

    return state.last_completed_candle_open_time_utc + timedelta(
        seconds=interval_seconds
    )


async def _run_manual_backfill(args: argparse.Namespace) -> None:
    """Run the manual backfill loop with throttled Gate.io requests."""

    settings = validate_settings()
    _configure_logging(getattr(settings, "log_level", "INFO"))

    database_url = getattr(settings, "postgres_dsn", None)
    if not database_url:
        raise ValueError("POSTGRES_DSN is required to run the manual backfill")

    interval_seconds = _get_interval_seconds(args.timeframe)
    default_end_utc = _default_requested_end_utc(interval_seconds)

    engine = create_async_engine(str(database_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    client = GateIOHistoricalCandlesClient(user_agent="trade-bot-backfill/1.0")

    try:
        async with session_factory() as session:
            state: BackfillState | None = None
            try:
                state = await _load_or_create_backfill_state(
                    session,
                    instrument_id=args.instrument_id,
                    timeframe=args.timeframe,
                    start_utc=args.start_utc,
                    end_utc=args.end_utc,
                    default_end_utc=default_end_utc,
                )
                await _set_backfill_status(session, state, BackfillStatus.RUNNING)

                requested_end_utc = state.requested_end_utc
                assert requested_end_utc is not None

                resume_suffix = ""
                if state.last_completed_candle_open_time_utc is not None:
                    resume_suffix = (
                        f" (resuming from "
                        f"{state.last_completed_candle_open_time_utc.isoformat()})"
                    )

                logger.info(
                    "Starting backfill for %s %s from %s to %s "
                    "(limit=%s, delay=%.1fs)%s",
                    state.instrument_id,
                    state.timeframe,
                    state.requested_start_utc.isoformat(),
                    requested_end_utc.isoformat(),
                    args.batch_limit,
                    args.request_delay_seconds,
                    resume_suffix,
                )

                processed_batches = 0
                processed_candles = 0

                while True:
                    next_cursor_utc = _next_backfill_cursor(state, interval_seconds)
                    if next_cursor_utc > requested_end_utc:
                        break

                    logger.info(
                        "Fetching %s %s candles from %s to %s (limit=%s)",
                        state.instrument_id,
                        state.timeframe,
                        next_cursor_utc.isoformat(),
                        requested_end_utc.isoformat(),
                        args.batch_limit,
                    )
                    candles = await asyncio.to_thread(
                        client.get_candles,
                        state.instrument_id,
                        state.timeframe,
                        limit=args.batch_limit,
                        from_timestamp=int(next_cursor_utc.timestamp()),
                        to_timestamp=int(requested_end_utc.timestamp()),
                    )

                    if not candles:
                        logger.info(
                            "Gate.io returned no more candles for %s %s between "
                            "%s and %s; stopping backfill",
                            state.instrument_id,
                            state.timeframe,
                            next_cursor_utc.isoformat(),
                            requested_end_utc.isoformat(),
                        )
                        break

                    batch_result = await persist_successful_backfill_batch(
                        session,
                        state,
                        candles,
                    )
                    processed_batches += 1
                    processed_candles += batch_result.candles_processed

                    logger.info(
                        "Processed %s closed candles ending at %s",
                        batch_result.candles_processed,
                        batch_result.last_completed_candle_open_time_utc.isoformat(),
                    )

                    next_cursor_utc = _next_backfill_cursor(state, interval_seconds)
                    if next_cursor_utc > requested_end_utc:
                        break

                    logger.info(
                        "Sleeping %.1f seconds before the next Gate.io request",
                        args.request_delay_seconds,
                    )
                    await asyncio.sleep(args.request_delay_seconds)

                await _set_backfill_status(session, state, BackfillStatus.COMPLETED)
                logger.info(
                    "Backfill completed for %s %s; batches=%s candles=%s through %s",
                    state.instrument_id,
                    state.timeframe,
                    processed_batches,
                    processed_candles,
                    requested_end_utc.isoformat(),
                )
            except Exception as exc:
                try:
                    await session.rollback()
                except Exception:
                    logger.exception("Failed to roll back the backfill session")

                if state is not None:
                    try:
                        await _set_backfill_status(
                            session,
                            state,
                            BackfillStatus.FAILED,
                            last_error=str(exc),
                        )
                    except Exception:
                        logger.exception("Failed to mark backfill state as failed")
                raise
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the manual backfill command."""

    args = _build_parser().parse_args(argv)
    _configure_logging("INFO")

    try:
        asyncio.run(_run_manual_backfill(args))
    except KeyboardInterrupt:
        logger.warning("Manual backfill interrupted")
        return 130
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    except Exception:
        logger.exception("Manual backfill failed")
        return 1

    return 0


__all__ = [
    "BackfillBatchResult",
    "BackfillBatchWriter",
    "BackfillSession",
    "main",
    "persist_successful_backfill_batch",
]


if __name__ == "__main__":
    raise SystemExit(main())

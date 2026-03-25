from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SQLEnum
from sqlalchemy import Identity, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.persistence.base import Base

NUMERIC_PRECISION = 38
NUMERIC_SCALE = 18


class BackfillStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OHLCVCandle(Base):
    """Persisted OHLCV candle for a single instrument and timeframe."""

    __tablename__ = "ohlcv_candles"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "open_time_utc",
            name="uq_ohlcv_candles_instrument_id_timeframe_open_time_utc",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    open_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    open_price: Mapped[Decimal] = mapped_column(
        Numeric(NUMERIC_PRECISION, NUMERIC_SCALE),
        nullable=False,
    )
    high_price: Mapped[Decimal] = mapped_column(
        Numeric(NUMERIC_PRECISION, NUMERIC_SCALE),
        nullable=False,
    )
    low_price: Mapped[Decimal] = mapped_column(
        Numeric(NUMERIC_PRECISION, NUMERIC_SCALE),
        nullable=False,
    )
    close_price: Mapped[Decimal] = mapped_column(
        Numeric(NUMERIC_PRECISION, NUMERIC_SCALE),
        nullable=False,
    )
    base_volume: Mapped[Decimal] = mapped_column(
        Numeric(NUMERIC_PRECISION, NUMERIC_SCALE),
        nullable=False,
    )
    quote_volume: Mapped[Decimal | None] = mapped_column(
        Numeric(NUMERIC_PRECISION, NUMERIC_SCALE),
        nullable=True,
    )


class BackfillState(Base):
    """Tracks resumable historical backfill progress per instrument/timeframe."""

    __tablename__ = "backfill_state"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            name="uq_backfill_state_instrument_id_timeframe",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_start_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    requested_end_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_completed_candle_open_time_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[BackfillStatus] = mapped_column(
        SQLEnum(
            BackfillStatus,
            name="backfill_status",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=BackfillStatus.PENDING,
        server_default=text("'pending'"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def mark_successful_batch(
        self, last_completed_candle_open_time_utc: datetime
    ) -> None:
        """Advance the backfill watermark after a batch persists successfully."""

        self.last_completed_candle_open_time_utc = last_completed_candle_open_time_utc
        self.status = BackfillStatus.RUNNING
        self.last_error = None


__all__ = [
    "BackfillState",
    "BackfillStatus",
    "OHLCVCandle",
]

"""create ingestion tables

Revision ID: 202603250001
Revises:
Create Date: 2026-03-25 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202603250001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ohlcv_candles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("open_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open_price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("high_price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("low_price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("close_price", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("base_volume", sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column("quote_volume", sa.Numeric(precision=38, scale=18), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ohlcv_candles"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            "open_time_utc",
            name="uq_ohlcv_candles_instrument_id_timeframe_open_time_utc",
        ),
    )
    op.create_table(
        "backfill_state",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("requested_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_completed_candle_open_time_utc",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                name="backfill_status",
                native_enum=False,
            ),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_backfill_state"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            name="uq_backfill_state_instrument_id_timeframe",
        ),
    )


def downgrade() -> None:
    op.drop_table("backfill_state")
    op.drop_table("ohlcv_candles")

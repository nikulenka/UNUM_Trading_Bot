from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


SUPPORTED_ML_TIMEFRAMES: Final[dict[str, int]] = {
    "15m": 15 * 60,
}

_STANDARD_LOG_LEVELS: Final[set[str]] = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}

_UNIX_EPOCH: Final[datetime] = datetime(1970, 1, 1, tzinfo=UTC)


def get_timeframe_seconds(timeframe: str) -> int:
    """
    Return the candle interval length in seconds for a supported timeframe.

    This is intentionally narrow for the first ML data-prep implementation.
    If the operational backfill and ML prep later share timeframe logic, this
    helper can be moved to a shared module such as:

        app/modules/ingestion/timeframes.py
    """
    try:
        return SUPPORTED_ML_TIMEFRAMES[timeframe]
    except KeyError:
        supported = ", ".join(sorted(SUPPORTED_ML_TIMEFRAMES))
        raise ValueError(
            f"unsupported ML_PREP_TIMEFRAME={timeframe!r}; "
            f"supported values: {supported}"
        ) from None


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _normalize_utc_datetime(value: datetime, *, field_name: str) -> datetime:
    """
    Normalize an aware datetime to UTC.

    Naive datetimes are rejected instead of interpreted as local time. This is
    safer for historical market data because local-time interpretation can
    silently shift the requested range.
    """
    if not _is_timezone_aware(value):
        raise ValueError(f"{field_name} must include timezone information")

    return value.astimezone(UTC)


def _epoch_seconds(value: datetime) -> int:
    """
    Return whole epoch seconds for a UTC datetime.

    The settings validator rejects microsecond precision for start/end
    boundaries, so integer seconds are safe here.
    """
    delta = value - _UNIX_EPOCH
    return delta.days * 86_400 + delta.seconds


def _validate_boundary_alignment(
    *,
    value: datetime,
    field_name: str,
    timeframe: str,
    interval_seconds: int,
) -> None:
    """
    Validate that a datetime aligns to the configured candle boundary.

    Example for 15m:
    - valid:   2024-01-01T00:00:00Z
    - valid:   2024-01-01T00:15:00Z
    - invalid: 2024-01-01T00:05:00Z
    - invalid: 2024-01-01T00:00:00.123Z
    """
    if value.microsecond != 0:
        raise ValueError(
            f"{field_name} must not contain fractional seconds; "
            f"got {value.isoformat()}"
        )

    seconds = _epoch_seconds(value)

    if seconds % interval_seconds != 0:
        raise ValueError(
            f"{field_name} must align to the {timeframe} candle boundary "
            f"({interval_seconds} seconds); got {value.isoformat()}"
        )


def _clean_required_string(value: str, *, field_name: str) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(f"{field_name} must be non-empty")

    return cleaned


def _validate_ml_postgres_dsn(value: str) -> str:
    """
    Validate the ML PostgreSQL DSN.

    The ML data-prep job uses SQLAlchemy async engine creation, so the expected
    DSN is the asyncpg dialect form:

        postgresql+asyncpg://user:password@host:5432/database

    This validation intentionally prevents accidental use of Redis, SQLite,
    or the operational POSTGRES_DSN variable.
    """
    cleaned = _clean_required_string(value, field_name="ML_POSTGRES_DSN")
    parsed = urlsplit(cleaned)

    if parsed.scheme != "postgresql+asyncpg":
        raise ValueError(
            "ML_POSTGRES_DSN must use the postgresql+asyncpg SQLAlchemy dialect, "
            "for example: postgresql+asyncpg://postgres:postgres@ml-postgres:5432/ml"
        )

    if not parsed.hostname:
        raise ValueError("ML_POSTGRES_DSN must include a database host")

    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise ValueError("ML_POSTGRES_DSN must include a database name")

    return cleaned


class MLDataPrepSettings(BaseSettings):
    """
    Environment-backed configuration for the standalone ML historical
    data-preparation job.

    This settings model intentionally uses ML-specific environment variables
    so the job does not accidentally write to the operational application
    database configured by POSTGRES_DSN.

    Required environment variables:
    - ML_POSTGRES_DSN
    - ML_PREP_START_UTC
    - ML_PREP_END_UTC

    Example:

        ML_POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@ml-postgres:5432/ml
        ML_PREP_START_UTC=2024-01-01T00:00:00Z
        ML_PREP_END_UTC=2024-06-01T00:00:00Z
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    ml_postgres_dsn: str = Field(validation_alias="ML_POSTGRES_DSN")

    instrument_id: str = Field(
        default="BTC_USDT",
        validation_alias="ML_PREP_INSTRUMENT_ID",
    )
    gateio_symbol: str = Field(
        default="",
        validation_alias="ML_PREP_GATEIO_SYMBOL",
    )
    timeframe: str = Field(
        default="15m",
        validation_alias="ML_PREP_TIMEFRAME",
    )

    start_utc: datetime = Field(validation_alias="ML_PREP_START_UTC")
    end_utc: datetime = Field(validation_alias="ML_PREP_END_UTC")

    batch_limit: int = Field(
        default=100,
        validation_alias="ML_PREP_BATCH_LIMIT",
    )
    request_delay_seconds: float = Field(
        default=3.0,
        validation_alias="ML_PREP_REQUEST_DELAY_SECONDS",
    )
    max_missing_ratio: float = Field(
        default=0.001,
        validation_alias="ML_PREP_MAX_MISSING_RATIO",
    )

    artifact_dir: Path = Field(
        default=Path("/artifacts/ml-data-prep"),
        validation_alias="ML_PREP_ARTIFACT_DIR",
    )
    create_schema: bool = Field(
        default=True,
        validation_alias="ML_PREP_CREATE_SCHEMA",
    )
    log_level: str = Field(
        default="INFO",
        validation_alias="ML_PREP_LOG_LEVEL",
    )

    @model_validator(mode="after")
    def validate_values(self) -> MLDataPrepSettings:
        self.ml_postgres_dsn = _validate_ml_postgres_dsn(self.ml_postgres_dsn)

        self.instrument_id = _clean_required_string(
            self.instrument_id,
            field_name="ML_PREP_INSTRUMENT_ID",
        )

        self.gateio_symbol = self.gateio_symbol.strip()
        if not self.gateio_symbol:
            self.gateio_symbol = self.instrument_id

        self.timeframe = _clean_required_string(
            self.timeframe,
            field_name="ML_PREP_TIMEFRAME",
        )
        interval_seconds = get_timeframe_seconds(self.timeframe)

        self.start_utc = _normalize_utc_datetime(
            self.start_utc,
            field_name="ML_PREP_START_UTC",
        )
        self.end_utc = _normalize_utc_datetime(
            self.end_utc,
            field_name="ML_PREP_END_UTC",
        )

        if self.end_utc <= self.start_utc:
            raise ValueError(
                "ML_PREP_END_UTC must be greater than ML_PREP_START_UTC"
            )

        _validate_boundary_alignment(
            value=self.start_utc,
            field_name="ML_PREP_START_UTC",
            timeframe=self.timeframe,
            interval_seconds=interval_seconds,
        )
        _validate_boundary_alignment(
            value=self.end_utc,
            field_name="ML_PREP_END_UTC",
            timeframe=self.timeframe,
            interval_seconds=interval_seconds,
        )

        if self.batch_limit <= 0:
            raise ValueError("ML_PREP_BATCH_LIMIT must be greater than zero")

        if self.request_delay_seconds < 0:
            raise ValueError(
                "ML_PREP_REQUEST_DELAY_SECONDS must be non-negative"
            )

        if not 0 <= self.max_missing_ratio <= 1:
            raise ValueError(
                "ML_PREP_MAX_MISSING_RATIO must be between 0 and 1 inclusive"
            )

        self.artifact_dir = self.artifact_dir.expanduser()

        self.log_level = self.log_level.strip().upper()
        if self.log_level not in _STANDARD_LOG_LEVELS:
            supported = ", ".join(sorted(_STANDARD_LOG_LEVELS))
            raise ValueError(
                f"ML_PREP_LOG_LEVEL must be one of: {supported}"
            )

        return self

    @property
    def timeframe_seconds(self) -> int:
        return get_timeframe_seconds(self.timeframe)

    @property
    def expected_candle_count(self) -> int:
        """
        Expected candle count for the configured half-open range:

            [start_utc, end_utc)

        Because start/end boundary alignment is validated, this should always
        be an integer count.
        """
        total_seconds = int((self.end_utc - self.start_utc).total_seconds())
        return total_seconds // self.timeframe_seconds

    @property
    def safe_ml_postgres_target(self) -> str:
        """
        Return a log-safe database target string without credentials.

        Example:

            host ml-postgres:5432 database ml

        This is useful for job startup logs.
        """
        parsed = urlsplit(self.ml_postgres_dsn)

        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port else ""
        database = parsed.path.lstrip("/") or "unknown-database"

        return f"host {host}{port} database {database}"


@lru_cache(maxsize=1)
def get_ml_data_prep_settings() -> MLDataPrepSettings:
    """
    Load and cache ML data-prep settings once per process.

    Tests that modify environment variables should call:

        get_ml_data_prep_settings.cache_clear()
    """
    return MLDataPrepSettings()

# ML Data Preparation Module Technical Design

> This document describes the technical architecture and implementation contract for the standalone ML historical data-preparation module.
>
> The module is an optional, Dockerized job that prepares historical OHLCV candles in a dedicated ML PostgreSQL database and writes a JSON readiness report.

---

## 1. Module Boundary

The ML data-preparation module is a separate offline batch-processing component.

It is not part of:

- FastAPI request handling
- live Gate.io WebSocket ingestion
- Redis stream processing
- TradingView webhook handling
- Streamlit dashboard rendering
- the operational historical backfill state machine

The module may reuse existing low-level ingestion code, especially:

- `GateIOHistoricalCandlesClient`
- `HistoricalCandle`
- `OHLCVCandle`
- SQLAlchemy persistence infrastructure patterns

But it should not depend on the live app runtime or Redis.

---

## 2. Runtime Architecture

The runtime consists of two optional Docker services:

| Service | Type | Lifetime | Responsibility |
|---|---|---|---|
| `ml-postgres` | stateful PostgreSQL service | persistent | Stores prepared ML historical market data |
| `ml-data-prep` | temporary batch job | exits after run | Fetches, loads, validates, and reports on historical data |

The important distinction is:

- `ml-postgres` is persistent storage
- `ml-data-prep` is a temporary worker

```mermaid
flowchart LR
    OP["Manual operator command"] --> JOB["ml-data-prep job"]

    JOB --> CFG["ML data-prep settings"]
    JOB --> GATE["Gate.io historical REST client"]
    GATE --> JOB

    JOB --> LOADER["Candle loader / upsert writer"]
    LOADER --> MLDB[("ML PostgreSQL")]

    JOB --> VALIDATOR["Dataset validator"]
    VALIDATOR --> MLDB

    JOB --> REPORT["Report writer"]
    REPORT --> ARTIFACTS["Mounted artifacts directory"]
```

---

## 3. Package Layout

Create a dedicated package:

```text
app/
  modules/
    ml_data_prep/
      __init__.py
      config.py
      job.py
      loader.py
      validation.py
      report.py
      types.py
```

Optional shared helper:

```text
app/
  modules/
    ingestion/
      timeframes.py
```

### Responsibility Map

| File | Responsibility |
|---|---|
| `config.py` | Environment-backed settings and validation |
| `job.py` | Top-level orchestration and process exit behavior |
| `loader.py` | Historical fetch loop and PostgreSQL upsert logic |
| `validation.py` | Dataset coverage and quality validation |
| `report.py` | JSON readiness report creation and artifact writing |
| `types.py` | Shared dataclasses/enums used across the module |
| `timeframes.py` | Shared timeframe-to-seconds helper, if extracted |

---

## 4. Internal Data Flow

The job should follow a clear pipeline:

```text
settings
  -> database engine
  -> optional schema bootstrap
  -> historical candle fetch
  -> candle upsert
  -> database-backed validation
  -> report generation
  -> process exit
```

The validator should read from the database after loading. It should not trust only the candles returned during the current run.

This matters because the ML database may already contain candles from previous runs.

---

## 5. Configuration Model

ML-specific settings are implemented in:

```text
app/modules/ml_data_prep/config.py
```

Main class:

```python
MLDataPrepSettings
```

Loader:

```python
get_ml_data_prep_settings()
```

Unlike the main application settings, this module should use ML-specific environment variables to avoid accidentally writing to the operational database.

### Required Environment Variables

| Variable | Meaning |
|---|---|
| `ML_POSTGRES_DSN` | Dedicated ML PostgreSQL DSN |
| `ML_PREP_START_UTC` | Requested inclusive start timestamp |
| `ML_PREP_END_UTC` | Requested exclusive end timestamp |

### Optional Environment Variables

| Variable | Default | Meaning |
|---|---|---|
| `ML_PREP_INSTRUMENT_ID` | `BTC_USDT` | Internal instrument ID stored in DB |
| `ML_PREP_GATEIO_SYMBOL` | same as instrument ID | Gate.io source symbol |
| `ML_PREP_TIMEFRAME` | `15m` | Candle timeframe |
| `ML_PREP_BATCH_LIMIT` | `100` | Max candles requested per REST window |
| `ML_PREP_REQUEST_DELAY_SECONDS` | `3.0` | Sleep between fetch windows |
| `ML_PREP_MAX_MISSING_RATIO` | `0.001` | Maximum missing interval ratio before failure |
| `ML_PREP_ARTIFACT_DIR` | `/artifacts/ml-data-prep` | Report output directory |
| `ML_PREP_CREATE_SCHEMA` | `true` | Create ML tables if missing |
| `ML_PREP_LOG_LEVEL` | `INFO` | Job log level |

### Settings Validation Rules

`MLDataPrepSettings` should validate:

- `ML_POSTGRES_DSN` is non-empty
- `start_utc` and `end_utc` are timezone-aware or normalized to UTC
- `end_utc > start_utc`
- `timeframe` is supported
- `batch_limit > 0`
- `request_delay_seconds >= 0`
- `0 <= max_missing_ratio <= 1`
- timestamps align to the timeframe boundary

For this sprint, supported timeframe can remain:

```python
{
    "15m": 900,
}
```

---

## 6. Time Semantics

The module should use a half-open time interval:

```text
[start_utc, end_utc)
```

Meaning:

- `start_utc` is inclusive
- `end_utc` is exclusive
- a candle is included if `open_time_utc >= start_utc` and `open_time_utc < end_utc`

For a timeframe interval of `$interval\_seconds$`, expected candle count is:

$$
expected\_candle\_count = \frac{end\_utc - start\_utc}{interval\_seconds}
$$

For example:

```text
start_utc = 2024-01-01T00:00:00Z
end_utc   = 2024-01-01T01:00:00Z
timeframe = 15m
```

Expected candle opens:

```text
2024-01-01T00:00:00Z
2024-01-01T00:15:00Z
2024-01-01T00:30:00Z
2024-01-01T00:45:00Z
```

The `01:00` candle is not included because `end_utc` is exclusive.

---

## 7. Database Architecture

The ML PostgreSQL database is separate from the main application database.

It uses a dedicated DSN:

```text
ML_POSTGRES_DSN
```

Not:

```text
POSTGRES_DSN
```

### Target Table

The initial ML data-prep table should be compatible with the existing operational candle model:

```text
ohlcv_candles
```

```python
from app.modules.persistence.models import OHLCVCandle
```

The ML database can have the same table name because it is physically separate from the main application database.

### Table Identity

Candle uniqueness is defined by:

```text
instrument_id
timeframe
open_time_utc
```

This key already exist on `OHLCVCandle`.

### Schema Bootstrap

The ML job may create the candle table directly when configured with:

```text
ML_PREP_CREATE_SCHEMA=true
```

Expected behavior:

- create SQLAlchemy async engine from `ML_POSTGRES_DSN`
- run `OHLCVCandle.__table__.create(..., checkfirst=True)` through `run_sync`
- do not create or use `backfill_state`

Future migrations can be added later, but direct bootstrap is acceptable for the first isolated ML table.

---

## 8. Upsert Semantics

The loader must use an upsert, not insert-ignore.

Current operational backfill uses:

```text
ON CONFLICT DO NOTHING
```

The ML loader will use:

```text
ON CONFLICT DO UPDATE
```

Conflict target:

```text
instrument_id, timeframe, open_time_utc
```

Updated fields:

- `open_price`
- `high_price`
- `low_price`
- `close_price`
- `base_volume`
- `quote_volume`

This gives the loader these properties:

- reruns do not create duplicates
- existing rows can be refreshed
- overlapping ranges are safe
- non-overlapping ranges append data
- existing data is not wiped

---

## 9. Core Types

Explicit internal dataclasses are used to keep module boundaries clean.

File:

```text
app/modules/ml_data_prep/types.py
```

### `LoadSummary`

Represents what happened during fetch and load.

```python
@dataclass(frozen=True)
class LoadSummary:
    request_batch_count: int
    loaded_candle_count: int
    empty_batch_count: int
```

Notes:

- `loaded_candle_count` means candles attempted for upsert after filtering to the requested range.
- It does not need to equal newly inserted row count because upserts may update existing rows.

### `ValidationStatus`

```python
class ValidationStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    FAILED = "FAILED"
```

### `ValidationResult`

Represents database-backed validation results.

```python
@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    expected_candle_count: int
    actual_candle_count: int
    missing_interval_count: int
    missing_interval_ratio: float
    missing_intervals_sample: list[str]
    actual_start_utc: datetime | None
    actual_end_utc: datetime | None
    invalid_ohlc_count: int
    invalid_volume_count: int
    notes: list[str]
```

### `DataReadinessReport`

The final serializable report is a plain dictionary.

It should combine:

- settings summary
- `LoadSummary`
- `ValidationResult`
- generated timestamp
- artifact path

---

## 10. Loader Architecture

File:

```text
app/modules/ml_data_prep/loader.py
```

The loader has two responsibilities:

1. fetch historical candles from Gate.io
2. upsert them into ML PostgreSQL

### Public Function

```python
async def load_historical_candles(
    *,
    engine: AsyncEngine,
    settings: MLDataPrepSettings,
) -> LoadSummary:
    ...
```

Internally this can call smaller helpers:

```python
async def create_schema_if_needed(...)
async def upsert_candles(...)
def build_fetch_windows(...)
def candle_to_row(...)
```

### Fetch Window Strategy

For a batch limit `$batch\_limit$` and interval `$interval\_seconds$`:

$$
window\_seconds = batch\_limit \times interval\_seconds
$$

Each request window is:

```text
[window_start, window_end_exclusive)
```

The REST request uses:

```text
from_timestamp = window_start
to_timestamp = window_end_exclusive - interval
```

This keeps the module’s internal half-open range semantics while calling Gate.io with a closed candle boundary.

### Loader Pseudocode

```python
cursor = settings.start_utc

while cursor < settings.end_utc:
    window_end_exclusive = min(
        cursor + timedelta(seconds=settings.batch_limit * interval_seconds),
        settings.end_utc,
    )

    last_expected_open = window_end_exclusive - timedelta(seconds=interval_seconds)

    candles = await asyncio.to_thread(
        client.get_candles,
        currency_pair=settings.gateio_symbol,
        interval=settings.timeframe,
        limit=settings.batch_limit,
        from_timestamp=int(cursor.timestamp()),
        to_timestamp=int(last_expected_open.timestamp()),
    )

    candles = [
        candle
        for candle in candles
        if cursor <= candle.open_time_utc < window_end_exclusive
    ]

    await upsert_candles(
        session=session,
        candles=candles,
        instrument_id=settings.instrument_id,
        timeframe=settings.timeframe,
    )

    cursor = window_end_exclusive

    if cursor < settings.end_utc:
        await asyncio.sleep(settings.request_delay_seconds)
```

### Empty Fetch Windows

If a fetch window returns no candles:

- do not fail immediately
- increment `empty_batch_count`
- advance the cursor
- allow final validation to determine whether the dataset is acceptable

This makes the loader deterministic and keeps the validation layer responsible for data quality decisions.

---

## 11. Upsert Implementation Details

PostgreSQL dialect insert is used:

```python
from sqlalchemy.dialects.postgresql import insert
```

The upsert should target `OHLCVCandle.__table__`.

Conceptual shape:

```python
stmt = insert(OHLCVCandle).values(rows)

stmt = stmt.on_conflict_do_update(
    index_elements=[
        "instrument_id",
        "timeframe",
        "open_time_utc",
    ],
    set_={
        "open_price": stmt.excluded.open_price,
        "high_price": stmt.excluded.high_price,
        "low_price": stmt.excluded.low_price,
        "close_price": stmt.excluded.close_price,
        "base_volume": stmt.excluded.base_volume,
        "quote_volume": stmt.excluded.quote_volume,
    },
)
```

Commit once per fetch window.

Reason:

- keeps transactions bounded
- preserves progress when a later window fails
- supports safe rerun after failure

---

## 12. Validation Architecture

File:

```text
app/modules/ml_data_prep/validation.py
```

The validator reads the ML database after loading.

Public function:

```python
async def validate_dataset(
    *,
    engine: AsyncEngine,
    settings: MLDataPrepSettings,
) -> ValidationResult:
    ...
```

### Validation Query

Fetch rows where:

```sql
instrument_id = :instrument_id
AND timeframe = :timeframe
AND open_time_utc >= :start_utc
AND open_time_utc < :end_utc
```

Order by:

```sql
open_time_utc ASC
```

### Coverage Validation

Generate the expected candle open timestamps from `start_utc` to `end_utc`, stepping by the timeframe interval.

Then compare expected timestamps with stored timestamps.

Compute:

$$
missing\_interval\_ratio = \frac{missing\_interval\_count}{expected\_candle\_count}
$$

If the expected count is zero, treat the configuration as invalid before running the loader.

### OHLC Validation

A row is invalid if any of the following are true:

```text
open_price <= 0
high_price <= 0
low_price <= 0
close_price <= 0
high_price < low_price
high_price < open_price
high_price < close_price
low_price > open_price
low_price > close_price
```

### Volume Validation

A row is invalid if:

```text
base_volume < 0
quote_volume < 0 when quote_volume is not null
```

Null `quote_volume` is allowed.

### Status Decision

The validator should assign one of:

```text
OK
WARNING
FAILED
```

Rules:

| Condition | Status |
|---|---|
| invalid OHLC rows exist | `FAILED` |
| invalid volume rows exist | `FAILED` |
| actual candle count is zero for a non-empty range | `FAILED` |
| missing ratio is greater than configured maximum | `FAILED` |
| missing intervals exist but ratio is within threshold | `WARNING` |
| no missing intervals and no invalid rows | `OK` |

---

## 13. Report Architecture

File:

```text
app/modules/ml_data_prep/report.py
```

The report writer converts settings, load summary, and validation result into a JSON artifact.

Public function:

```python
def write_data_readiness_report(
    *,
    settings: MLDataPrepSettings,
    load_summary: LoadSummary,
    validation_result: ValidationResult,
) -> Path:
    ...
```

### Artifact Paths

Write two files:

```text
report_<instrument>_<timeframe>_<start>_<end>.json
latest.json
```

Example:

```text
artifacts/ml-data-prep/report_BTC_USDT_15m_2024-01-01T000000Z_2024-06-01T000000Z.json
artifacts/ml-data-prep/latest.json
```

### Report Shape

The JSON report should include:

```json
{
  "status": "OK",
  "generated_at_utc": "2026-04-26T12:00:00+00:00",
  "instrument_id": "BTC_USDT",
  "source_symbol": "BTC_USDT",
  "timeframe": "15m",
  "requested_start_utc": "2024-01-01T00:00:00+00:00",
  "requested_end_utc_exclusive": "2024-06-01T00:00:00+00:00",
  "actual_start_utc": "2024-01-01T00:00:00+00:00",
  "actual_end_utc": "2024-05-31T23:45:00+00:00",
  "expected_candle_count": 14592,
  "actual_candle_count": 14592,
  "missing_interval_count": 0,
  "missing_interval_ratio": 0.0,
  "max_allowed_missing_ratio": 0.001,
  "invalid_ohlc_count": 0,
  "invalid_volume_count": 0,
  "loaded_candle_count": 14592,
  "request_batch_count": 146,
  "empty_batch_count": 0,
  "missing_intervals_sample": [],
  "missing_intervals_sample_limit": 100,
  "notes": [
    "Dataset validation passed."
  ]
}
```

### Missing Interval Sampling

Do not include every missing interval if the list is large.

Limit:

```text
100
```

Store:

```json
"missing_intervals_sample": [],
"missing_intervals_sample_limit": 100
```

### Write Safety

A temporary file is used and then renamed.

Behavior:

1. create artifact directory if missing
2. write timestamped report to `*.tmp`
3. rename `*.tmp` to final report path
4. write or overwrite `latest.json` the same way

---

## 14. Job Orchestration

File:

```text
app/modules/ml_data_prep/job.py
```

The job module is the executable entry point.

Run command:

```bash
python -m app.modules.ml_data_prep.job
```

### Flow

```python
async def run() -> ValidationStatus:
    settings = get_ml_data_prep_settings()
    setup_logging(settings.log_level)

    engine = create_async_engine(settings.ml_postgres_dsn)

    try:
        if settings.create_schema:
            await create_schema_if_needed(engine)

        load_summary = await load_historical_candles(
            engine=engine,
            settings=settings,
        )

        validation_result = await validate_dataset(
            engine=engine,
            settings=settings,
        )

        report_path = write_data_readiness_report(
            settings=settings,
            load_summary=load_summary,
            validation_result=validation_result,
        )

        log_summary(validation_result, report_path)

        return validation_result.status

    finally:
        await engine.dispose()
```

### Process Exit Codes

Exit behavior:

| Exit Code | Meaning |
|---:|---|
| `0` | Completed with `OK` or `WARNING` |
| `1` | Unexpected runtime failure |
| `2` | Configuration or input validation failure |
| `3` | Completed but validation status is `FAILED` |

`WARNING` can still return `0` because the run completed successfully and produced an explicit report.

---

## 15. Logging Behavior

The module should log concise operational milestones.

Log events:

- settings summary, excluding secrets
- database engine created
- schema bootstrap started/completed
- each fetch window start/end
- number of candles returned per window
- number of candles upserted per window
- validation summary
- final report path
- final status

Logging of the next things is avoided:

- database passwords
- full DSNs with credentials
- huge missing interval lists

DSN logging style:

```text
ML PostgreSQL DSN configured for host ml-postgres database ml
```

not:

```text
postgresql+asyncpg://postgres:postgres@ml-postgres:5432/ml
```

---

## 16. Docker Compose Architecture

Optional services are added behind the `ml` profile.

This ensures normal application startup is unchanged.

```yaml
services:
  ml-postgres:
    image: postgres:16
    profiles:
      - ml
    environment:
      POSTGRES_DB: ml
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5433:5432"
    volumes:
      - ml_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d ml"]
      interval: 5s
      timeout: 5s
      retries: 10

  ml-data-prep:
    build:
      context: .
    profiles:
      - ml
    depends_on:
      ml-postgres:
        condition: service_healthy
    environment:
      ML_POSTGRES_DSN: postgresql+asyncpg://postgres:postgres@ml-postgres:5432/ml
      ML_PREP_INSTRUMENT_ID: ${ML_PREP_INSTRUMENT_ID:-BTC_USDT}
      ML_PREP_GATEIO_SYMBOL: ${ML_PREP_GATEIO_SYMBOL:-BTC_USDT}
      ML_PREP_TIMEFRAME: ${ML_PREP_TIMEFRAME:-15m}
      ML_PREP_START_UTC: ${ML_PREP_START_UTC}
      ML_PREP_END_UTC: ${ML_PREP_END_UTC}
      ML_PREP_BATCH_LIMIT: ${ML_PREP_BATCH_LIMIT:-100}
      ML_PREP_REQUEST_DELAY_SECONDS: ${ML_PREP_REQUEST_DELAY_SECONDS:-3.0}
      ML_PREP_MAX_MISSING_RATIO: ${ML_PREP_MAX_MISSING_RATIO:-0.001}
      ML_PREP_ARTIFACT_DIR: /artifacts/ml-data-prep
      ML_PREP_CREATE_SCHEMA: ${ML_PREP_CREATE_SCHEMA:-true}
      ML_PREP_LOG_LEVEL: ${ML_PREP_LOG_LEVEL:-INFO}
    volumes:
      - ./artifacts/ml-data-prep:/artifacts/ml-data-prep
    command: ["python", "-m", "app.modules.ml_data_prep.job"]

volumes:
  ml_postgres_data:
```

---

## 17. Operational Commands

Start only the ML database:

```bash
docker compose --profile ml up -d ml-postgres
```

Run the data-prep job:

```bash
ML_PREP_START_UTC=2024-01-01T00:00:00Z \
ML_PREP_END_UTC=2024-06-01T00:00:00Z \
docker compose --profile ml run --rm ml-data-prep
```

Stop the ML database without deleting data:

```bash
docker compose --profile ml stop ml-postgres
```

Delete ML data only when intentionally resetting the volume:

```bash
docker compose --profile ml down -v
```

---

## 18. Error Handling Model

### Configuration Errors

Examples:

- missing `ML_POSTGRES_DSN`
- invalid timestamp
- unsupported timeframe
- non-positive batch limit
- `end_utc <= start_utc`

Behavior:

- log clear error
- do not connect to Gate.io
- do not write report unless settings are sufficiently valid to know artifact path
- exit with code `2`

### Gate.io Request Errors

Examples:

- network failure
- HTTP error
- invalid response

Recommended behavior for first implementation:

- fail the current run
- write failure logs
- exit with code `1`

Do not hide transport failures as validation gaps unless intentionally caught and converted.

### Database Errors

Examples:

- connection failure
- table creation failure
- upsert failure
- validation query failure

Behavior:

- fail the run
- dispose engine
- exit with code `1`

### Validation Failure

Examples:

- missing ratio exceeds threshold
- invalid OHLC rows
- invalid volume rows

Behavior:

- write report with `FAILED`
- exit with code `3`

---

## 19. Integration With Existing Codebase

### Reused Existing Components

| Existing Component | Usage |
|---|---|
| `GateIOHistoricalCandlesClient` | Historical candle fetch |
| `HistoricalCandle` | Normalized candle representation |
| `OHLCVCandle` | SQLAlchemy candle table shape |
| `Base` metadata | Optional table bootstrap |

### Components Not Used

| Component | Reason |
|---|---|
| `BackfillState` | ML job is range-based and idempotent, not state-machine-based |
| `BackfillBatchWriter` | Uses insert-ignore, but ML needs upsert |
| Redis streams | ML data prep is offline and database-backed |
| FastAPI app lifecycle | Job runs as standalone batch process |
| Feed status store | Only applies to live ingestion |

---

## 20. Non-Goals Inside This Module

This module should not contain:

- model training logic
- feature engineering logic
- label generation logic
- backtesting logic
- TradingView signal verification logic
- live ingestion logic
- Redis publication logic
- dashboard UI logic
- scheduled execution logic

Future ML modules can read from the ML PostgreSQL database produced by this module.

---

## 21. Implementation Notes

Minimal settings skeleton

```python
from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MLDataPrepSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    ml_postgres_dsn: str = Field(alias="ML_POSTGRES_DSN")

    instrument_id: str = Field(default="BTC_USDT", alias="ML_PREP_INSTRUMENT_ID")
    gateio_symbol: str | None = Field(default=None, alias="ML_PREP_GATEIO_SYMBOL")
    timeframe: str = Field(default="15m", alias="ML_PREP_TIMEFRAME")

    start_utc: datetime = Field(alias="ML_PREP_START_UTC")
    end_utc: datetime = Field(alias="ML_PREP_END_UTC")

    batch_limit: int = Field(default=100, alias="ML_PREP_BATCH_LIMIT")
    request_delay_seconds: float = Field(default=3.0, alias="ML_PREP_REQUEST_DELAY_SECONDS")
    max_missing_ratio: float = Field(default=0.001, alias="ML_PREP_MAX_MISSING_RATIO")

    artifact_dir: Path = Field(default=Path("/artifacts/ml-data-prep"), alias="ML_PREP_ARTIFACT_DIR")
    create_schema: bool = Field(default=True, alias="ML_PREP_CREATE_SCHEMA")
    log_level: str = Field(default="INFO", alias="ML_PREP_LOG_LEVEL")

    @model_validator(mode="after")
    def validate_values(self) -> "MLDataPrepSettings":
        if not self.gateio_symbol:
            self.gateio_symbol = self.instrument_id

        self.start_utc = self.start_utc.astimezone(UTC)
        self.end_utc = self.end_utc.astimezone(UTC)

        if self.end_utc <= self.start_utc:
            raise ValueError("ML_PREP_END_UTC must be greater than ML_PREP_START_UTC")

        if self.batch_limit <= 0:
            raise ValueError("ML_PREP_BATCH_LIMIT must be greater than zero")

        if self.request_delay_seconds < 0:
            raise ValueError("ML_PREP_REQUEST_DELAY_SECONDS must be non-negative")

        if not 0 <= self.max_missing_ratio <= 1:
            raise ValueError("ML_PREP_MAX_MISSING_RATIO must be between 0 and 1")

        return self


@lru_cache
def get_ml_data_prep_settings() -> MLDataPrepSettings:
    return MLDataPrepSettings()
```

Validation query shape

```python
stmt = (
    select(OHLCVCandle)
    .where(OHLCVCandle.instrument_id == settings.instrument_id)
    .where(OHLCVCandle.timeframe == settings.timeframe)
    .where(OHLCVCandle.open_time_utc >= settings.start_utc)
    .where(OHLCVCandle.open_time_utc < settings.end_utc)
    .order_by(OHLCVCandle.open_time_utc.asc())
)
```

Duplicate check SQL

```sql
SELECT instrument_id, timeframe, open_time_utc, COUNT(*)
FROM ohlcv_candles
GROUP BY instrument_id, timeframe, open_time_utc
HAVING COUNT(*) > 1;
```

Expected result:

```text
0 rows
```

---

## 22. Final Architecture Summary

The ML data-preparation module is an isolated offline batch component.

Its architecture is:

```text
ML settings
  -> Gate.io historical candle fetch
  -> ML PostgreSQL upsert
  -> database-backed validation
  -> JSON readiness report
```

The module writes only to the dedicated ML PostgreSQL database and the mounted artifacts directory.

It does not interact with:

- Redis
- FastAPI
- live WebSocket ingestion
- TradingView webhooks
- dashboard state
- the main application database

This keeps ML data preparation reproducible, rerunnable, and safe to evolve independently from the trading runtime.
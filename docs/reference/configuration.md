# Configuration Reference

> This document describes the current configuration system used by the
> codebase.
>
> Scope:
> - application settings in `app/core/config.py`
> - dashboard settings in `app/dashboard/config.py`
> - environment file resolution
> - settings precedence
> - runtime usage patterns
>
> This is an internal development reference for the current implementation.

---

## 1. Overview

The repository currently has **two separate settings models**:

1. **Application settings**
   - used by the FastAPI app, WebSocket consumer, TradingView webhook,
     backfill CLI, and Alembic env loading
   - defined in:
     - `app/core/config.py`

2. **Dashboard settings**
   - used only by the Streamlit dashboard
   - defined in:
     - `app/dashboard/config.py`

Both settings models use `pydantic-settings`, but they are configured
differently.

---

## 2. Source Files

| Concern | File |
|---|---|
| Main application settings | `app/core/config.py` |
| Dashboard settings | `app/dashboard/config.py` |
| Logging setup using config | `app/core/logging.py` |
| App startup using config | `app/main.py` |
| Alembic env loading using config helper | `alembic/env.py` |
| Config tests | `tests/test_config.py` |

---

## 3. Main Application Settings

### Module
- `app/core/config.py`

### Main type
- `Settings`

### Access pattern
The canonical way to load application settings is:

```python
from app.core.config import get_settings

settings = get_settings()
```

For startup validation, the code uses:

```python
from app.core.config import validate_settings

settings = validate_settings()
```

### Current implementation detail
`validate_settings()` is currently just a thin wrapper around `get_settings()`:

```python
def validate_settings() -> Settings:
    return get_settings()
```

So validation happens through normal Pydantic settings construction.

---

## 4. Application Profiles

The app supports three profiles:

- `dev`
- `test`
- `prod`

These are defined in:

```python
SUPPORTED_PROFILES = ("dev", "test", "prod")
```

### Profile selector
The active profile is chosen by environment variable:

- `APP_ENV`

If `APP_ENV` is not set, the default profile is:

- `dev`

### Profile validation
The helper `_get_env_files()` validates `APP_ENV`.

If the value is not one of the supported profiles, it raises:

- `ValueError`

Example invalid value:
- `APP_ENV=stage`

---

## 5. Environment File Resolution

### App settings env file logic
The application settings do **not** hardcode `env_file` in the Pydantic model.
Instead, env files are selected dynamically through `_get_env_files()`.

Current behavior:

```python
def _get_env_files() -> tuple[str, ...]:
    profile = os.getenv("APP_ENV", "dev")
    return (".env", f".env.{profile}")
```

### Resulting file order

| `APP_ENV` value | Loaded env files |
|---|---|
| `dev` | `.env`, `.env.dev` |
| `test` | `.env`, `.env.test` |
| `prod` | `.env`, `.env.prod` |

### Important detail
The canonical settings loader calls:

```python
Settings(_env_file=_get_env_files())
```

That means:
- `.env` is loaded first
- profile-specific file is loaded second
- profile-specific values override base `.env` values when both define the same key

### Example
If:

`.env`
```env
APP_PORT=7000
LOG_LEVEL=WARNING
```

`.env.test`
```env
APP_PORT=9000
LOG_LEVEL=DEBUG
```

and:

```env
APP_ENV=test
```

then the resulting values are:
- `app_port = 9000`
- `log_level = DEBUG`

---

## 6. Application Settings Precedence

The `Settings` class customizes source ordering using
`settings_customise_sources(...)`.

Current source order is:

1. init arguments
2. environment variables
3. dotenv files
4. file secrets
5. test-profile defaults

In code:

```python
return (
    init_settings,
    env_settings,
    dotenv_settings,
    file_secret_settings,
    TestProfileDefaultsSource(settings_cls),
)
```

### Practical meaning

#### Highest priority
- values passed directly into `Settings(...)`
- environment variables

#### Then
- values from `.env` and `.env.<profile>`

#### Lowest priority
- special fallback defaults used only for `APP_ENV=test`

### What this means in practice
Environment variables override env-file values.

Example:
- `.env.dev` says `APP_PORT=8000`
- environment says `APP_PORT=9999`

Result:
- `app_port = 9999`

This behavior is covered by `tests/test_config.py`.

---

## 7. Test Profile Defaults

### Why this exists
The code provides fallback DSNs for the `test` profile so tests can run in CI
without requiring explicit `.env.test` values.

### Implementation
This is handled by:
- `_get_test_profile_defaults()`
- `TestProfileDefaultsSource`

### Current defaults for `APP_ENV=test`

| Field | Default value |
|---|---|
| `postgres_dsn` | `postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app` |
| `redis_dsn` | `redis://127.0.0.1:6379/0` |

### Important behavior
These defaults apply **only** when:
- `APP_ENV=test`

They are fallback values, so they are overridden by:
- init parameters
- environment variables
- dotenv values
- file secrets

### Example
If:
- `APP_ENV=test`
- no `POSTGRES_DSN`
- no `REDIS_DSN`

then settings still load successfully using the built-in test defaults.

---

## 8. Application Settings Model

### Pydantic settings configuration

The `Settings` model uses:

```python
model_config = SettingsConfigDict(
    env_prefix="",
    case_sensitive=False,
    extra="ignore",
)
```

### Meaning

| Setting | Meaning |
|---|---|
| `env_prefix=""` | environment variables are read without a prefix |
| `case_sensitive=False` | env variable names are case-insensitive |
| `extra="ignore"` | unknown environment values do not cause validation errors |

### Environment variable naming
Because the model uses no prefix and case-insensitive lookup, these names are
resolved directly from the environment:

- `APP_ENV`
- `APP_PORT`
- `LOG_LEVEL`
- `POSTGRES_DSN`
- `REDIS_DSN`
- etc.

---

## 9. Application Settings Fields

The current application settings model contains the following fields.

### Core runtime settings

| Field | Type | Default | Environment variable |
|---|---|---|---|
| `app_env` | `str` | `"dev"` | `APP_ENV` |
| `app_port` | `int` | `8000` | `APP_PORT` |
| `log_level` | `str` | `"INFO"` | `LOG_LEVEL` |
| `postgres_dsn` | `str` | required | `POSTGRES_DSN` |
| `redis_dsn` | `str` | required except test fallback | `REDIS_DSN` |

### Instrument and symbol mapping settings

| Field | Type | Default | Environment variable |
|---|---|---|---|
| `primary_instrument_id` | `str` | `"BTC_USDT"` | `PRIMARY_INSTRUMENT_ID` |
| `primary_gateio_symbol` | `str` | `"BTC_USDT"` | `PRIMARY_GATEIO_SYMBOL` |
| `primary_tradingview_aliases` | `tuple[str, ...]` | `("BTCUSDT", "BTC/USDT", "BTC_USDT")` | `PRIMARY_TRADINGVIEW_ALIASES` |
| `primary_timeframe` | `str` | `"15m"` | `PRIMARY_TIMEFRAME` |

### Redis stream names

| Field | Type | Default | Environment variable |
|---|---|---|---|
| `market_events_stream` | `str` | `"market.events"` | `MARKET_EVENTS_STREAM` |
| `signal_events_stream` | `str` | `"signal.events"` | `SIGNAL_EVENTS_STREAM` |
| `system_events_stream` | `str` | `"system.events"` | `SYSTEM_EVENTS_STREAM` |

### TradingView webhook settings

| Field | Type | Default | Environment variable |
|---|---|---|---|
| `tradingview_webhook_secret` | `str` | `""` | `TRADINGVIEW_WEBHOOK_SECRET` |

### WebSocket settings

| Field | Type | Default | Environment variable |
|---|---|---|---|
| `gateio_ws_url` | `str` | `DEFAULT_GATEIO_WS_URL` | `GATEIO_WS_URL` |
| `ws_reconnect_delay` | `float` | `5.0` | `WS_RECONNECT_DELAY` |
| `ws_enabled` | `bool` | `True` | `WS_ENABLED` |
| `ws_currency_pair` | `str` | `"BTC_USDT"` | `WS_CURRENCY_PAIR` |

### Feed health settings

| Field | Type | Default | Environment variable |
|---|---|---|---|
| `feed_stale_timeout_seconds` | `float` | `60.0` | `FEED_STALE_TIMEOUT_SECONDS` |

---

## 10. Required vs Optional App Settings

### Required in normal profiles
These must be present in `dev` and `prod` unless supplied another way:

- `POSTGRES_DSN`
- `REDIS_DSN`

### Not required when `APP_ENV=test`
In the `test` profile, those DSNs have built-in fallback defaults.

### Optional with defaults
All other current fields have explicit defaults in the model.

---

## 11. How Application Settings Are Used

### FastAPI startup
`app/main.py` calls:

```python
settings = validate_settings()
setup_logging(settings.log_level)
```

It also uses:
- `settings.app_env`
- `settings.ws_enabled`

### WebSocket consumer
`app/modules/ingestion/ws_consumer.py` uses:

- `redis_dsn`
- `gateio_ws_url`
- `market_events_stream`
- `system_events_stream`
- `feed_stale_timeout_seconds`
- `ws_currency_pair`

### TradingView webhook
`app/api/tradingview.py` uses:

- `tradingview_webhook_secret`
- `redis_dsn`
- `signal_events_stream`
- `primary_instrument_id`
- `primary_gateio_symbol`
- `primary_tradingview_aliases`

### Backfill CLI
`app/modules/ingestion/backfill.py` uses:

- `postgres_dsn`
- `log_level`

### Alembic
`alembic/env.py` uses `_get_env_files()` and then reads:
- `POSTGRES_DSN`

That keeps migration env loading aligned with the application profile model.

---

## 12. Cached Settings Behavior

### Application settings cache
`get_settings()` is decorated with:

```python
@lru_cache
```

This means:
- settings are constructed once per process
- later calls reuse the same object

### Practical effect
Within one process:

```python
first = get_settings()
second = get_settings()
assert first is second
```

This behavior is explicitly tested in `tests/test_config.py`.

### Why this matters
Caching makes settings usage cheap and consistent, but it also means:
- tests must clear the cache when changing environment variables
- runtime code should treat settings as process-level configuration, not
  something that changes dynamically after startup

### In tests
The repository test suite uses:

```python
get_settings.cache_clear()
```

before and after relevant test cases.

---

## 13. Canonical Usage Pattern

For runtime code, the preferred pattern is:

```python
from app.core.config import get_settings

settings = get_settings()
```

For startup validation:
```python
from app.core.config import validate_settings

settings = validate_settings()
```

### Why this matters
Calling `Settings(...)` directly is possible, but the canonical helpers ensure:
- profile-based env file loading
- cached reuse where intended
- consistent behavior across modules

---

## 14. Dashboard Settings

The Streamlit dashboard has its own separate settings model.

### Module
- `app/dashboard/config.py`

### Main type
- `DashboardSettings`

### Access pattern

```python
from app.dashboard.config import get_dashboard_settings

settings = get_dashboard_settings()
```

### Cache
This function is also decorated with:

```python
@lru_cache
```

So dashboard settings are cached once per process.

---

## 15. Dashboard Environment File Behavior

Unlike the main application settings, dashboard settings use a fixed env file
configuration in the model itself:

```python
model_config = SettingsConfigDict(
    env_prefix="",
    case_sensitive=False,
    extra="ignore",
    env_file=(".env", ".env.dev"),
    env_file_encoding="utf-8",
)
```

### Important difference from app settings
The dashboard does **not** currently use `APP_ENV` profile switching.

It always reads:
- `.env`
- `.env.dev`

This is separate from the main application profile system.

### Practical implication
Even if the app runs with:
- `APP_ENV=test`
- or `APP_ENV=prod`

the dashboard settings model itself still resolves dotenv files from:
- `.env`
- `.env.dev`

unless values are overridden by environment variables.

---

## 16. Dashboard Settings Fields

| Field | Type | Default | Environment variable |
|---|---|---|---|
| `redis_dsn` | `str` | `redis://redis:6379/0` | `REDIS_DSN` |
| `market_events_stream` | `str` | `market.events` | `MARKET_EVENTS_STREAM` |
| `system_events_stream` | `str` | `system.events` | `SYSTEM_EVENTS_STREAM` |
| `signal_events_stream` | `str` | `signal.events` | `SIGNAL_EVENTS_STREAM` |
| `refresh_interval_seconds` | `float` | `3.0` | `REFRESH_INTERVAL_SECONDS` |
| `recent_event_limit` | `int` | `100` | `RECENT_EVENT_LIMIT` |
| `recent_system_event_limit` | `int` | `50` | `RECENT_SYSTEM_EVENT_LIMIT` |
| `recent_signal_event_limit` | `int` | `50` | `RECENT_SIGNAL_EVENT_LIMIT` |

### Dashboard usage
These settings are used by:
- `app/dashboard/dashboard_app.py`

for:
- Redis connection
- stream names
- refresh interval
- recent event counts

---

## 17. Example Environment Files

### `.env.example`
Current repository template:

```env
APP_ENV=dev
APP_PORT=8000
LOG_LEVEL=INFO
POSTGRES_DSN=postgresql+asyncpg://user:password@localhost:5432/app
REDIS_DSN=redis://localhost:6379/0
```

### `.env.test.example`
Current repository template:

```env
APP_ENV=test
APP_PORT=8000
LOG_LEVEL=INFO
POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app
REDIS_DSN=redis://127.0.0.1:6379/0
```

### Git policy
Real env files are currently ignored by Git:
- `.env`
- `.env.dev`
- `.env.test`
- `.env.prod`

Only example templates are committed.

---

## 18. Docker Compose Configuration Usage

The Docker Compose file supplies environment variables directly for the main app
and migration containers.

### `app` service
Provides:
- `APP_ENV=dev`
- `APP_PORT=8000`
- `LOG_LEVEL=INFO`
- `POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@postgres:5432/app`
- `REDIS_DSN=redis://redis:6379/0`
- `TRADINGVIEW_WEBHOOK_SECRET=${TRADINGVIEW_WEBHOOK_SECRET:-}`

### `migrate` service
Provides:
- `APP_ENV=dev`
- `POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@postgres:5432/app`
- `REDIS_DSN=redis://redis:6379/0`

### `dashboard` service
Provides:
- `REDIS_DSN=redis://redis:6379/0`
- `MARKET_EVENTS_STREAM=market.events`
- `SYSTEM_EVENTS_STREAM=system.events`
- `SIGNAL_EVENTS_STREAM=signal.events`

In Docker, these explicit environment variables typically override any values
coming from dotenv files.

---

## 19. CI Configuration Usage

GitHub Actions sets configuration explicitly for test runs.

Current CI environment includes:
- `APP_ENV=test`
- `APP_PORT=8000`
- `LOG_LEVEL=INFO`
- `POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app`
- `REDIS_DSN=redis://127.0.0.1:6379/0`

This matches the test profile design and avoids dependence on local env files.

---

## 20. Settings-Related Test Coverage

`tests/test_config.py` covers:

- env file selection for:
  - `dev`
  - `test`
  - `prod`
- invalid profile rejection
- env file precedence
- environment variable precedence over env files
- default values
- required field validation
- test profile DSN fallback behavior
- `get_settings()` cache behavior

These tests are the best reference for current expected settings resolution.

---

## 21. Current Implementation Notes

### Application and dashboard settings are separate systems
Although both use `pydantic-settings`, they are configured independently.

Key difference:
- app settings use dynamic profile-based env file selection
- dashboard settings use a fixed `(".env", ".env.dev")` env file list

---

### Env var names map automatically from field names
Because `env_prefix=""` and `case_sensitive=False` are used, field names map to
environment variables in the standard Pydantic way.

Examples:
- `app_port` ↔ `APP_PORT`
- `postgres_dsn` ↔ `POSTGRES_DSN`
- `feed_stale_timeout_seconds` ↔ `FEED_STALE_TIMEOUT_SECONDS`

---

### Unknown environment values are ignored
Because `extra="ignore"` is set, extra keys in env files or process env do not
cause settings validation failures.

This is convenient for shared env files, but it also means typos in unrelated
unused variables are silently ignored.

---

### `get_settings()` should be treated as process-scoped configuration
Because of `lru_cache`, runtime code should not expect environment changes to be
picked up automatically after first access.

If environment changes need to be reflected in tests, the cache must be cleared.

---

## 22. Short Summary

The current configuration layer is based on `pydantic-settings` and split into
two settings models:

- `Settings` in `app/core/config.py`
  - used by the FastAPI app and backend runtime code
  - supports `dev` / `test` / `prod` profile-based env files
  - provides CI-friendly fallback DSNs in the `test` profile
  - is cached via `get_settings()`

- `DashboardSettings` in `app/dashboard/config.py`
  - used only by the Streamlit dashboard
  - reads `.env` and `.env.dev`
  - is cached via `get_dashboard_settings()`

Environment variables override dotenv values, and application settings are
validated through normal Pydantic model construction.
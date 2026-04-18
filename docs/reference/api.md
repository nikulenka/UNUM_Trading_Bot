# API Reference

> This document describes the HTTP API currently implemented in the codebase.
> It is intended as an internal development reference.
>
> Scope:
> - only implemented endpoints
> - current behavior only
> - includes operational endpoints and the TradingView webhook

---

## 1. Overview

The current FastAPI application exposes a small HTTP API with two main roles:

1. **Operational endpoints**
   - liveness
   - readiness
   - ingestion status

2. **Signal ingestion**
   - TradingView webhook acceptance and publication to Redis Streams

The application is initialized in `app/main.py` and currently registers these
routers:

- `app/api/health.py`
- `app/api/ready.py`
- `app/api/status.py`
- `app/api/tradingview.py`

---

## 2. General Conventions

### Response format
All implemented endpoints return JSON responses.

### Authentication
There is no global API authentication layer.

The only endpoint-specific protection currently implemented is:

- `POST /alerts/tradingview`
  - validates a shared secret provided in the JSON body

### API versioning
There is currently no version prefix such as `/v1`.

### Error handling
FastAPI default error handling is used for most request validation errors,
except where the code explicitly converts errors into `HTTPException` or
`JSONResponse`.

### Content types
For request bodies, the only implemented write endpoint expects JSON:

- `Content-Type: application/json`

---

## 3. Endpoint Summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Basic liveness check |
| `GET` | `/ready` | Readiness check |
| `GET` | `/ingestion/status` | Current in-process feed status snapshot |
| `POST` | `/alerts/tradingview` | Accept TradingView webhook payload and publish a signal event to Redis |

---

## 4. Endpoints

---

## 4.1 `GET /health`

### Purpose
Basic liveness check for the FastAPI service.

### Source
- File: `app/api/health.py`

### Behavior
Returns a minimal success response if the application process is running and
able to serve requests.

### Response
**Status:** `200 OK`

```json
{
  "status": "ok"
}
```

### Notes
- This endpoint does not check PostgreSQL, Redis, or Gate.io connectivity.
- It should be treated strictly as a process liveness signal.

---

## 4.2 `GET /ready`

### Purpose
Readiness check intended to indicate whether the application is ready to serve.

### Source
- File: `app/api/ready.py`

### Behavior
The route currently performs a stubbed dependency check via
`is_database_connected()`.

Current implementation:

```python
def is_database_connected() -> bool:
    return True
```

Under normal execution, the endpoint returns a successful readiness response.

### Success response
**Status:** `200 OK`

```json
{
  "status": "ready",
  "database": "connected"
}
```

### Failure response
If the internal dependency check returns false:

**Status:** `503 Service Unavailable`

```json
{
  "status": "not_ready",
  "database": "disconnected"
}
```

If an unexpected exception occurs inside the route:

**Status:** `503 Service Unavailable`

```json
{
  "status": "not_ready"
}
```

### Notes
- The current implementation does **not** perform a real PostgreSQL check.
- It also does **not** check Redis availability.
- This endpoint should currently be treated as a placeholder readiness signal.

---

## 4.3 `GET /ingestion/status`

### Purpose
Returns the current feed-health snapshot from the in-memory feed status store.

### Source
- File: `app/api/status.py`
- Backing store: `app/core/feed_status.py`

### Behavior
The route returns the output of:

```python
feed_status_store.get_snapshot()
```

This reflects the current in-process state tracked by the live WebSocket
consumer and stale checker.

### Response shape
**Status:** `200 OK`

```json
{
  "status": "live",
  "last_message_at_utc": "2026-03-29T12:00:00+00:00",
  "entries_blocked": false
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `status` | string | One of `live`, `stale`, `down` |
| `last_message_at_utc` | string or `null` | ISO-8601 UTC timestamp of the last received live message |
| `entries_blocked` | boolean | Whether new entries should be blocked according to current feed health |

### Possible states

#### `live`
- Recent market data has been received.
- `entries_blocked = false`

#### `stale`
- No valid market data has been received within the configured stale timeout.
- `entries_blocked = true`

#### `down`
- Initial/default state, or explicitly set when the feed is considered down.
- `entries_blocked = true`

### Example responses

#### Initial/default state
```json
{
  "status": "down",
  "last_message_at_utc": null,
  "entries_blocked": true
}
```

#### Stale state
```json
{
  "status": "stale",
  "last_message_at_utc": "2026-03-29T11:58:00+00:00",
  "entries_blocked": true
}
```

#### Live state
```json
{
  "status": "live",
  "last_message_at_utc": "2026-03-29T12:00:00+00:00",
  "entries_blocked": false
}
```

### Notes
- This endpoint reports **in-memory process state**, not persisted state.
- The state resets when the FastAPI process restarts.
- The current response does **not** include backfill progress.

---

## 4.4 `POST /alerts/tradingview`

### Purpose
Accepts a TradingView webhook payload, validates it, resolves the incoming
symbol to an internal instrument, and publishes a normalized signal event to
Redis Streams.

### Source
- File: `app/api/tradingview.py`

### Side effect
On success, the endpoint publishes a signal event to the configured Redis stream:

- `settings.signal_events_stream`
- default: `signal.events`

### Request body

#### Required fields
| Field | Type | Description |
|---|---|---|
| `secret` | string | Shared secret that must match `TRADINGVIEW_WEBHOOK_SECRET` |
| `symbol` | string | Incoming TradingView symbol |
| `action` | string | Signal action; normalized to lowercase |

#### Optional fields
| Field | Type | Description |
|---|---|---|
| `price` | decimal-compatible value | Optional price value |
| `timeframe` | string | Optional timeframe label |
| `message` | string | Optional free text |
| `timestamp` | string, integer, or float | Optional source timestamp; normalized to string |

### Validation rules

#### `secret`
- must be present
- must be a non-empty string after trimming

#### `symbol`
- must be present
- must be a non-empty string after trimming

#### `action`
- must be present
- must be a non-empty string after trimming
- is normalized to lowercase before publication

#### `timeframe`, `message`
- if provided, values are trimmed
- empty strings are converted to `null`

#### `timestamp`
- if provided as number or string, it is normalized to a string
- empty string becomes `null`

#### Extra fields
Extra fields are forbidden.

The payload model uses:

```python
model_config = ConfigDict(extra="forbid")
```

So any unexpected field triggers a `422 Unprocessable Entity` response.

---

### Symbol resolution

The webhook does not accept arbitrary symbols. Incoming `symbol` is resolved
against configured settings.

The following values are treated as valid aliases for the primary instrument:

- `settings.primary_instrument_id`
- `settings.primary_gateio_symbol`
- all values in `settings.primary_tradingview_aliases`

With default settings, accepted aliases are effectively:

- `BTC_USDT`
- `BTCUSDT`
- `BTC/USDT`

If the normalized incoming symbol matches one of those aliases, the published
`instrument_id` becomes:

- `BTC_USDT`

If not, the request is rejected as unmapped.

---

### Successful request example

```http
POST /alerts/tradingview
Content-Type: application/json
```

```json
{
  "secret": "top-secret",
  "symbol": "BTCUSDT",
  "action": "BUY",
  "price": "50000.50",
  "timeframe": "15m",
  "message": "enter long",
  "timestamp": "2026-03-29T12:00:00Z"
}
```

### Success response
**Status:** `202 Accepted`

```json
{
  "status": "accepted",
  "event_id": "1743336000-0"
}
```

`event_id` is the Redis Stream entry ID returned by `XADD`.

---

### Published Redis event shape

On success, the handler publishes a stream entry with at least these fields:

| Field | Type | Description |
|---|---|---|
| `event_type` | string | Always `tradingview_signal` |
| `instrument_id` | string | Internal instrument identifier |
| `source_symbol` | string | Original incoming symbol |
| `action` | string | Lowercased action |
| `received_at_utc` | string | Server receive timestamp in ISO-8601 UTC format |
| `payload_hash` | string | SHA-256 hash of the payload excluding `secret` |

Optional fields are included when present:
- `price`
- `timeframe`
- `message`
- `timestamp`

### Example published event

```json
{
  "event_type": "tradingview_signal",
  "instrument_id": "BTC_USDT",
  "source_symbol": "BTCUSDT",
  "action": "buy",
  "received_at_utc": "2026-03-29T12:00:05+00:00",
  "payload_hash": "…",
  "price": "50000.50",
  "timeframe": "15m",
  "message": "enter long",
  "timestamp": "2026-03-29T12:00:00Z"
}
```

### Payload hashing behavior
The `payload_hash` is built from a canonical JSON representation of the payload:
- excluding `secret`
- excluding `null` fields
- sorted by key
- serialized with stable separators

This makes the hash independent of field order in the incoming request.

---

### Error responses

#### Invalid JSON
If the request body is not valid JSON:

**Status:** `400 Bad Request`

```json
{
  "detail": "invalid JSON payload"
}
```

---

#### Payload validation failure
If required fields are missing, empty, or extra fields are present:

**Status:** `422 Unprocessable Entity`

Example shape:

```json
{
  "detail": [
    {
      "type": "extra_forbidden",
      "loc": ["body", "unexpected"],
      "msg": "Extra inputs are not permitted",
      "input": "value"
    }
  ]
}
```

FastAPI / Pydantic error details are returned directly.

---

#### Webhook secret not configured
If `TRADINGVIEW_WEBHOOK_SECRET` is empty or unset:

**Status:** `503 Service Unavailable`

```json
{
  "detail": "trading webhook is not configured"
}
```

---

#### Invalid secret
If the provided `secret` does not match configuration:

**Status:** `403 Forbidden`

```json
{
  "detail": "invalid secret"
}
```

---

#### Unmapped symbol
If the incoming symbol does not map to the configured instrument:

**Status:** `422 Unprocessable Entity`

```json
{
  "detail": "unmapped symbol: ETHUSDT"
}
```

---

#### Redis publication failure
If publishing to Redis fails:

**Status:** `503 Service Unavailable`

```json
{
  "detail": "signal publication unavailable"
}
```

---

### Notes
- The Redis client is created per request and closed after publishing.
- The secret is not included in the published event payload.
- The route logs accepted and rejected requests, but intentionally avoids
  logging the secret value.

---

## 5. Current API Surface by Role

### Operational endpoints
- `GET /health`
- `GET /ready`
- `GET /ingestion/status`

### Signal ingestion endpoint
- `POST /alerts/tradingview`

There are no other HTTP write endpoints currently implemented.

---

## 6. Current Omissions

The following are not part of the current HTTP API:

- REST endpoints for historical backfill execution
- REST endpoints for reading candles from PostgreSQL
- REST endpoints for reading Redis stream contents
- authentication middleware
- versioned API namespaces
- webhook endpoints other than TradingView

These behaviors exist elsewhere in the system:
- backfill is a CLI, not an HTTP endpoint
- dashboard reads Redis directly, not through FastAPI

---

## 7. Source Files

| Concern | File |
|---|---|
| FastAPI app entry point | `app/main.py` |
| Health endpoint | `app/api/health.py` |
| Ready endpoint | `app/api/ready.py` |
| Ingestion status endpoint | `app/api/status.py` |
| TradingView webhook | `app/api/tradingview.py` |
| Feed status backing store | `app/core/feed_status.py` |
| Settings used by API | `app/core/config.py` |

---

## 8. Short Summary

The current API is intentionally small:

- `/health` answers whether the process is alive
- `/ready` is a placeholder readiness endpoint
- `/ingestion/status` exposes current in-memory feed state
- `/alerts/tradingview` accepts validated TradingView alerts and publishes them
  to Redis as normalized signal events
## Sprint Goal

Ship a minimal ingestion pipeline for **Gate.io spot BTC_USDT** with:

- historical **`15m` candles** backfilled into Postgres,
- live **ticker** and **trade** events published to Redis Streams,
- a basic feed-health signal that can block new entries globally,
- TradingView webhook alerts accepted, validated, mapped, and published.

---

## Scope Guardrails

To keep the sprint implementable, we'll use these limits:

- **Exchange:** Gate.io spot only
- **Primary instrument:** `BTC_USDT`
- **Historical timeframe:** `15m` only
- **Live channels:** ticker and trade only
- **Webhook format:** one JSON payload shape only
- **Queue:** Redis Streams
- **Feed status model:** `live`, `stale`, `down`
- **Entry blocking:** one **global** `entries_blocked` flag
- **Backfill runner:** one process at a time
- **Order book:** not in this sprint

---

## What Is Explicitly Out of This Sprint

The following are intentionally deferred:

- Gate.io order book and depth processing
- TradingView email ingestion
- More than one timeframe beyond `15m`
- More than one or two instruments
- Per-instrument entry gating
- Advanced feed-state models like `resyncing`, `degraded`, `failed`
- Multi-worker backfill coordination
- Multi-exchange abstractions
- Raw tick archival
- TradingView audit database tables
- Advanced alerting integrations
- Extended readiness model beyond a simple ingestion status endpoint

---

## Simplified Technical Decisions

These decisions avoid over-design.

### Instrument mapping
Use a **static config mapping**, not a full registry system.

Each configured instrument only needs:

- `instrument_id`
- Gate.io symbol
- allowed TradingView aliases

### Redis Streams
Use only three streams:

- `market.events`
- `signal.events`
- `system.events`

Each event should include an `event_type` field so one stream can carry multiple event kinds.

### Storage
Use only two new tables:

- `ohlcv_candles`
- `backfill_state`

### Feed health
Use only three statuses:

- `live`
- `stale`
- `down`

### Entry blocking
Use one global flag:

- `entries_blocked = true` if live market feed is stale or down
- `entries_blocked = false` if live market feed is healthy

### Candle policy
Persist **closed candles only**.

### TradingView auth
Validate a shared `secret` field in the **JSON body**.

---

## Minimal Data Contracts

These do not need to become a large architecture exercise. Just keep them consistent.
This decision is a technical debt for MVP, later it will be reworked.

### `market.events`
Required fields:

- `event_type` = `ticker` or `trade`
- `instrument_id`
- `source_symbol`
- `source_time_utc`
- `ingested_at_utc`
- `payload`

### `signal.events`
Required fields:

- `event_type` = `tradingview_signal`
- `instrument_id`
- `source_symbol`
- `action`
- `received_at_utc`
- `payload_hash`

### `system.events`
Required fields:

- `event_type` = `feed_status`
- `status`
- `entries_blocked`
- `updated_at_utc`
- `message` if useful

---

# Implementation Plan

## Step 1 — Minimal Config and Shared Plumbing

**Goal:** create just enough common plumbing so the ingestion pieces can work together.

### Implement
- [ ] Add config for the primary instrument:
  - `instrument_id`
  - Gate.io symbol
  - TradingView aliases
- [ ] Set the initial scope to:
  - instrument: `BTC_USDT`
  - timeframe: `15m`
- [ ] Add Redis Stream names to config:
  - `market.events`
  - `signal.events`
  - `system.events`
- [ ] Add a small in-memory feed status store with:
  - current feed `status`
  - `last_message_at`
  - `entries_blocked`
- [ ] Add `GET /status/ingestion`
- [ ] Keep `GET /health` unchanged

### `GET /status/ingestion` should show
- current feed status
- last live message time
- whether new entries are blocked
- backfill progress summary

---

## Step 2 — Historical Candles Backfill

**Goal:** backfill closed `15m` candles for `BTC_USDT` into Postgres and resume after interruption.

### Implement
- [ ] Add `ohlcv_candles` table with:
  - `instrument_id`
  - timeframe
  - candle open time
  - open, high, low, close
  - volume fields
- [ ] Add DB-level uniqueness on:
  - `instrument_id`
  - timeframe
  - candle open time
- [ ] Add `backfill_state` table with:
  - `instrument_id`
  - timeframe
  - requested start
  - requested end
  - last completed candle time
  - status
  - last error
- [ ] Build a REST client for Gate.io historical candles
- [ ] Normalize returned candles into internal format
- [ ] Skip still-open candles
- [ ] Backfill forward in time
- [ ] Update `backfill_state` after each successful batch
- [ ] Add one command to run backfill manually
- [ ] Assume one backfill runner at a time for this sprint

### Validation
- [ ] Run backfill for `BTC_USDT` `15m`
- [ ] Verify candles are written to Postgres
- [ ] Stop the process mid-run
- [ ] Restart the command
- [ ] Verify it resumes from the last saved candle
- [ ] Rerun the same range and verify no duplicate rows are created

---

## Step 3 — Live Ticker and Trade Ingestion

**Goal:** stream live Gate.io ticker and trade events into Redis Streams.

### Implement
- [ ] Add one WebSocket consumer for Gate.io spot market data
- [ ] Subscribe to:
  - ticker updates
  - trade updates
- [ ] Parse valid messages safely
- [ ] Ignore or log malformed messages without crashing the consumer
- [ ] Normalize each event with:
  - `event_type`
  - `instrument_id`
  - `source_symbol`
  - `source_time_utc`
  - `ingested_at_utc`
  - `payload`
- [ ] Publish all live events to `market.events`
- [ ] Track the last valid market message time
- [ ] Start the consumer with the app
- [ ] Stop the consumer cleanly with the app

### Validation
- [ ] Start the app with live ingestion enabled
- [ ] Verify ticker events appear in `market.events`
- [ ] Verify trade events appear in `market.events`
- [ ] Verify events carry a valid `instrument_id`
- [ ] Verify timestamps are normalized to UTC

---

## Step 4 — Basic Reconnect and Stale-Feed Detection

**Goal:** make the live feed safe enough to use without implementing a full feed-state platform.

### Implement
- [ ] Add reconnect with exponential backoff
- [ ] Retry automatically after socket disconnect
- [ ] Define a stale timeout based on **ticker** freshness
- [ ] If no valid ticker message arrives before the timeout:
  - mark feed status `stale`
  - set `entries_blocked = true`
- [ ] If the socket is disconnected:
  - mark feed status `down`
  - set `entries_blocked = true`
- [ ] When valid data resumes:
  - mark feed status `live`
  - set `entries_blocked = false`
- [ ] Publish feed-status changes to `system.events`
- [ ] Show current status in `GET /status/ingestion`

### Notes
- Do **not** use trade inactivity alone as the stale signal.
- For this sprint, use one **global** feed state, not per-instrument gating.

### Validation
- [ ] Kill the WebSocket connection and verify reconnect happens automatically
- [ ] Simulate no incoming ticker messages and verify status becomes `stale`
- [ ] Verify `entries_blocked` becomes `true` when feed is not healthy
- [ ] Verify feed status is published to `system.events`
- [ ] Verify `GET /status/ingestion` reflects the current state

---

## Step 5 — TradingView Webhook

**Goal:** accept one TradingView webhook format, validate it, map it to `instrument_id`, and publish it.

### Implement
- [ ] Add `POST /alerts/tradingview`
- [ ] Accept one JSON payload shape only
- [ ] Require these fields:
  - `secret`
  - `symbol`
  - `action`
- [ ] Optionally accept:
  - `price`
  - `timeframe`
  - `message`
  - `timestamp`
- [ ] Validate the `secret` from the JSON body
- [ ] Reject missing or invalid payloads clearly
- [ ] Map the TradingView `symbol` using the static alias config
- [ ] Reject unmapped symbols
- [ ] Publish accepted alerts to `signal.events`
- [ ] Add structured logs for accepted and rejected alerts
- [ ] Ensure the secret is never logged
- [ ] Set up a public HTTPS path for end-to-end TradingView testing

### Validation
- [ ] Send a valid alert and verify it is published to `signal.events`
- [ ] Send invalid JSON and verify rejection
- [ ] Send an invalid secret and verify rejection
- [ ] Send an unmapped symbol and verify rejection
- [ ] Verify no secret value appears in logs

---

## Step 6 — End-to-End Demo and Runbook

**Goal:** prove the vertical slice works and document how to operate it.

### Implement
- [ ] Write a short runbook covering:
  - how to run backfill
  - how to start live ingestion
  - how to check ingestion status
  - how to test the TradingView webhook
- [ ] Verify the full flow end to end:
  - historical candles to Postgres
  - live market events to Redis
  - feed status changes to Redis
  - TradingView signals to Redis

### Demo checklist
- [ ] Backfill `BTC_USDT` `15m` candles successfully
- [ ] Show live ticker/trade events arriving in `market.events`
- [ ] Show feed status changing in `system.events`
- [ ] Show `entries_blocked` changing when the feed becomes stale or down
- [ ] Show a TradingView alert arriving in `signal.events`

---

# Sprint Done Criteria

The sprint is done when all of these are true:

- [ ] `BTC_USDT` `15m` candles can be backfilled into Postgres
- [ ] Candle inserts are idempotent and resumable
- [ ] Live ticker and trade events flow into `market.events`
- [ ] Feed status changes flow into `system.events`
- [ ] The system can block new entries globally when the feed is stale or down
- [ ] TradingView alerts are accepted, validated, mapped, and published to `signal.events`
- [ ] `GET /status/ingestion` shows useful current state
- [ ] The team can run and demo the full flow locally

---

# Next Sprint Candidates

These are the items intentionally moved out of this sprint:

- Gate.io order book snapshot + incremental updates
- Order book gap detection and resync
- Per-instrument feed health and gating
- TradingView email ingestion
- Multi-worker backfill coordination
- Richer ingestion observability
- More symbols and more timeframes
- More exchanges

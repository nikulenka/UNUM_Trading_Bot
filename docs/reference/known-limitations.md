# Constraints and Future Changes

> This document records the current shape of the codebase and the next  
> changes we expect to make as development continues.

---

## API

### `GET /ready`

**Current state:**

- The endpoint returns `200 ready`.
- The underlying database connectivity check is currently stubbed.

**Planned change:**

- Replace the stub with real connectivity checks for PostgreSQL and Redis.
- Return `503` if one or more dependencies are unavailable.

**Notes:**

- This will make `/ready` suitable for deployment health checks.

---

### `GET /ingestion/status`

**Current state:**

- The endpoint returns the feed-status snapshot from the in-memory store.
- It does not include backfill progress.

**Planned change:**

- Extend the response to include backfill progress if that remains a useful operational signal.
- Keep the feed-health snapshot as the primary status output.

**Notes:**

- The sprint plan mentions backfill progress as part of the status view, so this is the most likely next enhancement if the endpoint is expanded.

---

## Feed Status

### In-memory feed status store

**Current state:**

- Feed health is tracked in-memory.
- The state resets on process restart.

**Planned change:**

- If the system needs cross-process or restart-resilient feed health, move the status to Redis or another shared store.
- Keep the in-memory version if single-process operation remains the target.

**Notes:**

- For the current architecture, the in-memory store is lightweight and simple.

---

### Duplicate `feed_status_store` definitions

**Current state:**

- `FeedStatusStore` is instantiated in both:
    - `app/core/feed_status.py`
    - `app/core/config.py`
- The active modules use the instance from `app/core/feed_status.py`.

**Planned change:**

- Remove the duplicate instance from `app/core/config.py`.
- Keep a single source of truth for feed state.

**Notes:**

- This reduces confusion for future imports and avoids accidental divergence.

---

### Status-change callbacks are not wired into any consumer

**Current state:**

- `FeedStatusStore` supports status-change callbacks.
- No code currently registers a callback.

**Planned change:**

- Either wire callbacks into a real consumer or remove the callback hook if it is not needed.
- Use the callback mechanism only if it serves a concrete event-publishing or observability need.

**Notes:**

- This is a useful extension point, but it is currently dormant.

---

## Ingestion

### WebSocket timestamp generation

**Current state:**

- WebSocket subscription messages use `datetime.now().timestamp()`.

**Planned change:**

- Normalize subscription timestamp generation to UTC-based datetime handling for consistency with the rest of the codebase.

**Notes:**

- The current implementation works, but the codebase generally prefers explicit UTC handling.

---

### TradingView webhook Redis client lifecycle

**Current state:**

- The webhook creates a new Redis client per request.
- The client is used once and then closed.

**Planned change:**

- Introduce a shared Redis client or connection pool for webhook publishing.
- Reuse that client across requests where appropriate.

**Notes:**

- The current pattern is acceptable for low-throughput usage.
- A pooled client will be a better fit if alert volume increases.

---

## Backfill

### Supported timeframe

**Current state:**

- Manual backfill currently supports only `15m`.

**Planned change:**

- Add additional timeframes only when the data model and operational flow are ready for them.

**Notes:**

- Keeping the first implementation narrow makes the pipeline easier to validate.

---

### One backfill state per instrument/timeframe

**Current state:**

- `BackfillState` is unique per `(instrument_id, timeframe)`.

**Planned change:**

- Keep the single-state model unless there is a concrete need for multiple concurrent backfill windows.
- If that need appears, expand the model deliberately rather than ad hoc.

**Notes:**

- The current shape is appropriate for a resumable, sequential backfill workflow.

---

### Single-process backfill execution

**Current state:**

- Backfill assumes one runner at a time.
- There is no distributed lock or process coordination.

**Planned change:**

- Add coordination only if the deployment model requires multiple concurrent backfill workers.

**Notes:**

- For now, the simpler assumption keeps the implementation easy to reason about.

---

## Dashboard

### Auto-refresh behavior

**Current state:**

- The dashboard attempts to use `st.autorefresh` if it is available.
- If the function is not present, the dashboard still works, but without auto-refresh.

**Planned change:**

- Decide whether to depend on a dedicated auto-refresh package or make refresh behavior fully explicit in the dependencies.
- If auto-refresh is important, document and pin the dependency.

**Notes:**

- The current implementation is defensive and degrades gracefully.

---

## Infrastructure

### Runtime Alembic installation in the migration container

**Current state:**

- The migration target in `Dockerfile` installs Alembic at container runtime.

**Planned change:**

- Move Alembic into the build image or a dedicated migration image with pinned dependencies already installed.
- Avoid network installation during container startup.

**Notes:**

- This will make migrations more reproducible and more predictable in CI/CD.

---

## Miscellaneous

### Root-level `main.py`

**Current state:**

- The root `main.py` is a placeholder script.
- The real FastAPI entry point is `app/main.py`.

**Planned change:**

- Remove the placeholder if it is no longer useful.
- If kept, label it clearly as non-application scaffolding.

**Notes:**

- This file has no impact on the running service.
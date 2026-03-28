# Trade Bot

## Environment Configuration

### Files stored in git:
- `.env.example` - template for development environment
- `.env.test.example` - template for test environment

### Files NOT stored in git:
- `.env` - local environment variables
- `.env.dev` - development environment variables
- `.env.test` - test environment variables  
- `.env.prod` - production environment variables

### How secrets are passed:
- Through environment variables
- Through CI secrets / deployment environment

### Configuration priority:
- Environment variables have priority over env files
- For `APP_ENV=test`, safe CI-compatible DSN defaults are used if not explicitly set

## Docker

### Start the full stack

```bash
docker compose up --build -d
```

This starts:
- `app` — FastAPI application on `http://localhost:8000`
- `postgres` — PostgreSQL with persistent data in the `postgres_data` volume
- `redis` — Redis

The `app` service starts only after `postgres` and `redis` report healthy.

### Check status

```bash
docker compose ps
docker compose logs -f app
```

### Health endpoints

- `http://localhost:8000/health`
- `http://localhost:8000/ready`

### Stop the stack

```bash
docker compose down
```

### Stop the stack and remove Postgres data

```bash
docker compose down -v
```

## Manual Backfill Script

The manual backfill runner lives in `app/modules/ingestion/backfill.py`.

It backfills closed `BTC_USDT` `15m` candles into Postgres and is intentionally slow by default:
- `--request-delay-seconds` defaults to `3.0`
- `--batch-limit` defaults to `100`
- it skips still-open candles
- it resumes from the saved backfill state when one already exists

Make sure `POSTGRES_DSN` is available in your environment before running it.

Example:

```bash
uv run python -m app.modules.ingestion.backfill --start-utc 2026-03-25T00:00:00Z --end-utc 2026-03-26T00:00:00Z --request-delay-seconds 5 --batch-limit 50
```

## CI

GitHub Actions uses:
- Python `3.13`
- pinned `uv` `0.5.30`
- `uv sync --frozen`

CI starts real `postgres` and `redis`
CI waits explicitly for both services before `pytest`

### Sprint 1 test scope

included:
- smoke
- unit
- lightweight integration

excluded:
- e2e
- load

CI command:
```bash
pytest -m "(smoke or unit or integration) and not e2e and not load"
```

## Releases

Release tags must be created from commits already merged into `main`

Tag format:
```bash
vX.Y.Z
```

Pushing a release tag publishes the Docker image to GHCR:
- `ghcr.io/<owner>/<repo>:vX.Y.Z`
- `ghcr.io/<owner>/<repo>:latest`

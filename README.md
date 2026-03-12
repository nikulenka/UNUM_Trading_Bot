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

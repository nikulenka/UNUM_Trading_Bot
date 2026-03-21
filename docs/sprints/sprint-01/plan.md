# Sprint 1

**Updated plan for the first sprint.**

## Sprint Tasks

- Application starts stably.
- Configuration is validated at startup (`fail-fast`).
- Local infrastructure is spun up with a single command.
- CI controls quality and versioning.
- Project uses `uv` for dependency management and build reproducibility.
- Separate `liveness` and `readiness` checks added (`/health` and `/ready`).

## Sprint Result

The project runs locally, `/health` and `/ready` endpoints are accessible, every PR is checked automatically, dependencies are pinned via `pyproject.toml` and `uv.lock`, and CI tests run with real `Postgres` and `Redis` services.

---

## Task 1 (Skeleton Initialization)

### Scope
Project structure setup + FastAPI application + asynchronous execution environment + initial `uv` initialization.

### Subtasks
- [x] Create repository structure.
- [x] Add FastAPI entry point in `app/main.py`.
- [x] Add liveness check endpoint `GET /health`.
- [x] Add readiness check endpoint `GET /ready`.
- [x] Configure basic logging.
- [x] Add smoke tests for `/health` and `/ready`.
- [x] Initialize project via `uv` and add `pyproject.toml`.
- [x] Add basic dependencies via `uv`.
- [x] Commit lock file `uv.lock`.

### File Structure
```text
app/
  main.py
  api/
    health.py
    ready.py
  core/
    config.py
    logging.py
  modules/
    ingestion/
    strategy/
    execution/
    risk/
    ml/
    persistence/
docs/
	sprints/
		sprint-01
	templates/
tests/
  test_health.py
  test_ready.py
  test_config.py
.env.example
.env.dev
.env.test
.env.prod
pyproject.toml
uv.lock
Dockerfile
docker-compose.yml
.github/workflows/ci.yml
README.md
```

### Definition of Done (DoD)
- `uvicorn app.main:app --reload` starts successfully.
- `GET /health` returns `200` and `{"status":"ok"}`.
- `GET /ready` returns:
  - `200` if `Postgres` and `Redis` are available.
  - `503` if at least one dependency is unavailable.
- Smoke tests pass successfully locally and in CI.
- `pyproject.toml` and `uv.lock` are present in the repository.

## Task 2 (Configuration)

### Scope
Typed configuration + environment profiles + `fail-fast` validation + reading env files via `pydantic-settings`.

### Subtasks
- Implement settings model using `pydantic-settings`.
- Add profile switcher (`dev`, `test`, `prod`).
- Configure reading variables from env files (`.env`, `.env.dev`, `.env.test`, `.env.prod`).
- Define source priority: environment variables higher than values from env files.
- Define mandatory variables and default values.
- Add validation at startup (hard stop if mandatory fields are missing).
- Add unit tests for loading and validating configuration from env files and environment variables.
- For `test` profile, keep working DSNs compatible with CI services.
- Commit env file storage policy:
  - Only `.env.example` (and optionally safe `.env.test.example`) stored in repository.
  - Real `.env`, `.env.dev`, `.env.prod` not committed.
  - Secrets passed via CI/Secrets environment variables.

### Minimal Configuration Keys
- `APP_ENV`
- `APP_PORT`
- `LOG_LEVEL`
- `POSTGRES_DSN`
- `REDIS_DSN`
*(Exchange keys are optional at this stage, before working on the `ingestion` module.)*

### Definition of Done (DoD)
- Incorrect or missing configuration stops application startup.
- `dev`/`test`/`prod` profiles load correctly.
- Configuration is read from env files via `pydantic-settings`.
- Tests confirm validation correctness and source priority.
- Env file policy is adhered to; sensitive data does not enter the repository.

## Task 3 (Docker Compose Stack)

### Scope
Local environment startup with a single command (application + `Postgres` + `Redis`) with service dependency management.

### Subtasks
- Create `Dockerfile` for the application.
- Create `docker-compose.yml` with three services.
- Add `depends_on` for `app` with dependencies on `postgres` and `redis`.
- Add `healthchecks` for `postgres` and `redis`.
- Configure `app` startup after dependent services are ready.
- Configure restart policies.
- Configure persistent volume for `Postgres`.
- Configure application healthcheck via `/ready`.
- Add startup instructions to `README`.

### Definition of Done (DoD)
- `docker compose up --build` starts all services.
- Application connects to `Postgres`/`Redis`.
- `depends_on` and service readiness checks configured in `docker-compose`.
- `Postgres` data persists after container restart (volume works).

## Task 4 (CI Pipeline)

### Scope
Automated quality control for every push/PR + usage of `uv` and dependency caching.

### Subtasks
- Create workflow in GitHub Actions.
- Install `uv` in CI.
- Add step `uv sync --frozen` to install dependencies from `uv.lock`.
- Configure `uv` dependency caching in GitHub Actions (cache by `uv.lock` key).
- Spin up real `postgres` and `redis` as services in CI for tests.
- Run linter (`ruff`).
- Run tests (`pytest`).
- Build Docker image.
- Configure version tagging strategy in main branch.
- Pin tool versions in CI:
  - Python version `3.13`
  - `uv` version (specific pinned release).
- Add explicit wait step for `postgres` and `redis` readiness before `pytest`.
- Explicitly define Sprint 1 test boundaries:
  - smoke, unit, lightweight integration tests run;
  - heavy e2e/load tests are not included in Sprint 1.
- Commit artifact strategy:
  - Tag format: `vX.Y.Z`
  - Publish Docker image to selected registry.

### Definition of Done (DoD)
- PR is rejected if linter or tests fail.
- CI uses `uv.lock` for reproducible dependency installation.
- Dependency cache in GitHub Actions accelerates repeated builds.
- Build in `main` branch creates tagged artifact.
- Branch protection configured requiring successful CI before merge.
- CI passes stably without flakes related to early test startup before services are ready.
- Python/`uv` versions in CI are pinned and reproducible.
- Tagging and image publication follow approved version format.

---

## Overall Sprint DoD

- Application runs locally and in Docker.
- `/health` and `/ready` endpoints are accessible.
- Configuration is typed, validated, and read from env files via `pydantic-settings`.
- Local infrastructure is reproducible with a single command.
- `depends_on` and service readiness checks configured in `docker-compose`.
- CI blocks incorrect merges, uses `uv` with lock file, caches dependencies, and creates versioned artifacts.
- Python and `uv` versions are pinned in CI.
- `postgres`/`redis` readiness check performed before tests.
- Sprint 01 test scope boundaries documented (no heavy e2e).
- Env file and secrets policy adhered to.
- Artifact versioning and image publication formalized.

## Current Risks

- Excessive configuration complexity at early stage (keep minimal key set).
- CI instability due to `postgres`/`redis` network delays (control healthcheck/timeout/retry).
- Docker network configuration errors (use explicit service names and DSNs).
- Dependency inconsistency if lock file skipped (`uv.lock` usage is mandatory).

**Realistic Estimate:** 4-7 business days.

## Recommendations

1. **Fail-fast vs CI:** Accepted; real services are spun up in CI.
2. **Event Loop:** Considered as an architectural note; `Redis` initially considered as broker; full worker will be in a separate sprint.
3. **Healthcheck:** Accepted; `/ready` added with dependency check.
4. **Heavy ML Dependencies as Blocker:** Not accepted as mandatory for Sprint 1, as current stack is CPU-only + `xgboost`; image optimizations remain a task for next prioritization.

---

## Acceptance Checklist for Sprint 01

### Block 1: Project Initialization and Basic Application (Task 1)
- Directory structure created according to monolith domain.
- Dependency management initialized via `uv`; `pyproject.toml` and `uv.lock` present in root.
- Entry point created in `app/main.py`, basic logging configured.
- `GET /health` returns `200` and `{"status":"ok"}`.
- `GET /ready` validly reflects `postgres`/`redis` availability.
- Local startup `uvicorn app.main:app --reload` passes without errors.
- Smoke tests `/health` and `/ready` pass locally and in CI.

### Block 2: Application Configuration (Task 2)
- Typed configuration implemented via `pydantic-settings`.
- Environment profile support (`dev`, `test`, `prod`) configured.
- Source priority adhered to: env vars > `.env` files.
- `Fail-fast` validation works for mandatory keys.
- Unit tests on configuration loading and validation pass.
- `test` profile works correctly in CI.
- No real secrets or working `.env` files present in repository.
- Current `.env.example` (and optionally `.env.test.example`) present.

### Block 3: Docker Compose Infrastructure (Task 3)
- `Dockerfile` for FastAPI application created.
- `docker-compose.yml` contains services `app`, `postgres`, `redis`.
- `depends_on` and `healthchecks` configured correctly.
- Container restart policies configured.
- Persistent volume configured for `Postgres`.
- Startup instructions added to `README.md`.
- `docker compose up --build` spins up infrastructure without manual steps.

### Block 4: CI/CD Pipeline in GitHub Actions (Task 4)
- Workflow runs on push and PR.
- CI uses `uv sync --frozen` and `uv.lock`.
- Dependency caching configured by `uv.lock` key.
- Real services `postgres` and `redis` spin up in CI.
- `ruff` and `pytest` run.
- Docker image build and versioned artifact formation performed in `main`.
- Branch protection enabled on `main` (required checks).
- Python and `uv` versions pinned.
- Wait step for `Postgres`/`Redis` readiness performed before `pytest`.
- Release tag format and Docker image registry publication fixed and adhered to.
- Sprint 01 test scope boundaries (smoke/unit/light integration) reflected in workflow/documentation.

---

### Rule to Eliminate Ambiguity

If `pytest` runs on the GitHub Actions runner host (standard job without `container:`), use:
```bash
POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app
REDIS_DSN=redis://127.0.0.1:6379/0
```

If job runs inside a container (`container:`), use service hostnames (`postgres`, `redis`).

Before running tests, add a readiness wait step (wait-for/retry) for `Postgres` and `Redis` to reduce flakes during service startup.
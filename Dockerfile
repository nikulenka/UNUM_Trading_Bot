FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ARG UV_VERSION=0.5.30
RUN pip install --no-cache-dir uv==${UV_VERSION}

COPY pyproject.toml uv.lock ./

RUN uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && rm requirements.txt

COPY app ./app

FROM base AS app-runtime

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]

FROM base AS dashboard

EXPOSE 8501

CMD ["sh", "-c", "streamlit run app/dashboard/app.py --server.address 0.0.0.0 --server.port ${DASHBOARD_PORT:-8501}"]

FROM base AS migrate

RUN python -m pip install --no-cache-dir "alembic>=1.18.4"

COPY alembic.ini ./
COPY alembic ./alembic

CMD ["python", "-m", "alembic", "-c", "/app/alembic.ini", "upgrade", "head"]

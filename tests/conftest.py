import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_PORT", "8000")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault(
    "POSTGRES_DSN",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app",
)
os.environ.setdefault("REDIS_DSN", "redis://127.0.0.1:6379/0")

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
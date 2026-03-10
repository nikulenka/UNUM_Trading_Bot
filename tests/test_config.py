from app.core.config import Settings, get_settings


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql+asyncpg://user:pass@localhost:5432/test_db")
    monkeypatch.setenv("REDIS_DSN", "redis://localhost:6379/1")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.app_port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.postgres_dsn == "postgresql+asyncpg://user:pass@localhost:5432/test_db"
    assert settings.redis_dsn == "redis://localhost:6379/1"


def test_get_settings_is_cached(monkeypatch):
    get_settings.cache_clear()

    monkeypatch.setenv("APP_ENV", "test")

    first = get_settings()
    second = get_settings()

    assert first is second
    assert first.app_env == "test"

    get_settings.cache_clear()

import pytest
from pydantic import ValidationError

import app.core.config as config_module
from app.core.config import Settings, get_settings, validate_settings


@pytest.fixture
def clear_cache(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("REDIS_DSN", raising=False)
    yield
    get_settings.cache_clear()


def test_get_env_files_dev_profile(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    result = config_module._get_env_files()
    assert result == (".env", ".env.dev")


def test_get_env_files_test_profile(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    result = config_module._get_env_files()
    assert result == (".env", ".env.test")


def test_get_env_files_prod_profile(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    result = config_module._get_env_files()
    assert result == (".env", ".env.prod")


def test_get_env_files_invalid_profile(monkeypatch):
    monkeypatch.setenv("APP_ENV", "stage")
    with pytest.raises(ValueError, match="Invalid APP_ENV profile 'stage'"):
        config_module._get_env_files()


def test_settings_load_from_env_files(tmp_path, monkeypatch, clear_cache):
    # Create .env file
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_DSN=postgresql+asyncpg://base:base@localhost:5432/base_db\n"
        "REDIS_DSN=redis://localhost:6379/0\n"
        "APP_PORT=7000\n"
        "LOG_LEVEL=WARNING\n"
    )
    
    # Create .env.test file
    env_test_file = tmp_path / ".env.test"
    env_test_file.write_text(
        "APP_PORT=9000\n"
        "LOG_LEVEL=DEBUG\n"
    )
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    
    settings = Settings(_env_file=config_module._get_env_files())  # type: ignore[call-arg]
    
    assert settings.app_env == "test"
    assert settings.app_port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.postgres_dsn == "postgresql+asyncpg://base:base@localhost:5432/base_db"
    assert settings.redis_dsn == "redis://localhost:6379/0"


def test_env_vars_priority_over_env_files(tmp_path, monkeypatch, clear_cache):
    # Create .env file
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_DSN=postgresql+asyncpg://file:file@localhost:5432/file_db\n"
        "REDIS_DSN=redis://localhost:6379/1\n"
        "APP_PORT=7000\n"
        "LOG_LEVEL=WARNING\n"
    )
    
    # Create .env.dev file
    env_dev_file = tmp_path / ".env.dev"
    env_dev_file.write_text(
        "APP_PORT=8000\n"
        "LOG_LEVEL=INFO\n"
    )
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("APP_PORT", "9999")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql+asyncpg://env:env@localhost:5432/env_db")
    monkeypatch.setenv("REDIS_DSN", "redis://localhost:6379/2")
    
    settings = Settings(_env_file=config_module._get_env_files())  # type: ignore[call-arg]
    
    assert settings.app_port == 9999
    assert settings.log_level == "ERROR"
    assert settings.postgres_dsn == "postgresql+asyncpg://env:env@localhost:5432/env_db"
    assert settings.redis_dsn == "redis://localhost:6379/2"


def test_default_values(tmp_path, monkeypatch, clear_cache):
    # Create .env file with only required fields
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_DSN=postgresql+asyncpg://test:test@localhost:5432/test_db\n"
        "REDIS_DSN=redis://localhost:6379/0\n"
    )
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "dev")
    # Don't set APP_PORT, LOG_LEVEL
    
    settings = Settings(_env_file=config_module._get_env_files())  # type: ignore[call-arg]
    
    assert settings.app_env == "dev"
    assert settings.app_port == 8000
    assert settings.log_level == "INFO"


def test_required_fields_missing(tmp_path, monkeypatch, clear_cache):
    # Create empty .env file
    env_file = tmp_path / ".env"
    env_file.write_text("")
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("REDIS_DSN", raising=False)
    
    with pytest.raises(ValidationError):
        Settings(_env_file=config_module._get_env_files())  # type: ignore[call-arg]


def test_validate_settings_success(tmp_path, monkeypatch, clear_cache):
    # Create .env file with required fields
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_DSN=postgresql+asyncpg://test:test@localhost:5432/test_db\n"
        "REDIS_DSN=redis://localhost:6379/0\n"
    )
    
    monkeypatch.chdir(tmp_path)
    
    settings = validate_settings()
    assert isinstance(settings, Settings)


def test_validate_settings_failure(tmp_path, monkeypatch, clear_cache):
    # Create empty .env file
    env_file = tmp_path / ".env"
    env_file.write_text("")
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("REDIS_DSN", raising=False)
    
    with pytest.raises(ValidationError):
        validate_settings()


def test_test_profile_uses_ci_compatible_default_dsns(tmp_path, monkeypatch, clear_cache):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    
    settings = Settings(_env_file=config_module._get_env_files())  # type: ignore[call-arg]
    
    assert settings.app_env == "test"
    assert settings.postgres_dsn == "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app"
    assert settings.redis_dsn == "redis://127.0.0.1:6379/0"


def test_get_settings_is_cached(tmp_path, monkeypatch, clear_cache):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")

    first = get_settings()
    second = get_settings()

    assert first is second
    assert first.app_env == "test"

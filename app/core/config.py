from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    app_port: int = 8000
    log_level: str = "INFO"
    postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app"
    redis_dsn: str = "redis://127.0.0.1:6379/0"

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

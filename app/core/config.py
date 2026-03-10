import os
from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource

SUPPORTED_PROFILES = ("dev", "test", "prod")


def _get_env_files() -> tuple[str, ...]:
    profile = os.getenv("APP_ENV", "dev")
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"Invalid APP_ENV profile '{profile}'. Supported profiles: {SUPPORTED_PROFILES}")
    
    return (".env", f".env.{profile}")


def _get_test_profile_defaults() -> dict[str, str]:
    if os.getenv("APP_ENV", "dev") != "test":
        return {}
    
    return {
        "POSTGRES_DSN": "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app",
        "REDIS_DSN": "redis://127.0.0.1:6379/0",
    }


class Settings(BaseSettings):
    app_env: str = "dev"
    app_port: int = 8000
    log_level: str = "INFO"
    postgres_dsn: str
    redis_dsn: str

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    def __init__(self, **values: Any) -> None:
        defaults = _get_test_profile_defaults()
        for key, default_value in defaults.items():
            if key not in values:
                values[key] = default_value
        super().__init__(**values)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


def validate_settings() -> Settings:
    return get_settings()


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=_get_env_files())

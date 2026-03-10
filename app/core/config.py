import os
from functools import lru_cache

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
)

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
        "postgres_dsn": "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app",
        "redis_dsn": "redis://127.0.0.1:6379/0",
    }


class TestProfileDefaultsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field, field_name: str):
        defaults = _get_test_profile_defaults()
        value = defaults.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, str]:
        return _get_test_profile_defaults()


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
            TestProfileDefaultsSource(settings_cls),
        )


def validate_settings() -> Settings:
    return get_settings()


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=_get_env_files())  # type: ignore[call-arg]

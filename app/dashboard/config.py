from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    redis_dsn: str = "redis://redis:6379/0"
    market_events_stream: str = "market.events"
    system_events_stream: str = "system.events"
    signal_events_stream: str = "signal.events"
    refresh_interval_seconds: float = 3.0
    recent_event_limit: int = 100
    recent_system_event_limit: int = 50
    recent_signal_event_limit: int = 50

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_file=(".env", ".env.dev"),
        env_file_encoding="utf-8",
    )


@lru_cache
def get_dashboard_settings() -> DashboardSettings:
    return DashboardSettings()

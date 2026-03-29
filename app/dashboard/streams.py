from __future__ import annotations

import json
from typing import Any

import redis


def create_redis_client(redis_dsn: str) -> redis.Redis:
    if not redis_dsn:
        raise ValueError("redis_dsn must not be empty")

    return redis.Redis.from_url(redis_dsn, decode_responses=True)


def read_recent_events(
    client: redis.Redis,
    stream_name: str,
    *,
    count: int = 100,
) -> list[dict[str, Any]]:
    if not stream_name:
        raise ValueError("stream_name must not be empty")

    if count <= 0:
        raise ValueError("count must be greater than zero")

    rows = client.xrevrange(stream_name, max="+", min="-", count=count)
    events: list[dict[str, Any]] = []

    for message_id, fields in reversed(rows):
        event: dict[str, Any] = {"id": message_id}
        for key, value in fields.items():
            event[key] = _normalize_value(key, value)
        events.append(event)

    return events


def _normalize_value(key: str, value: Any) -> Any:
    if key == "payload" and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    if key == "entries_blocked":
        return _parse_bool(value)

    return value


def _parse_bool(value: Any) -> bool | Any:
    if isinstance(value, bool):
        return value

    if not isinstance(value, str):
        return value

    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False

    return value


__all__ = [
    "create_redis_client",
    "read_recent_events",
]

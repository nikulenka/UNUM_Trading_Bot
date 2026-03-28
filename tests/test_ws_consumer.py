from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.feed_status import FeedStatus, feed_status_store
from app.modules.ingestion.ws_consumer import _run_stale_checker_once


class FakeRedisClient:
    def __init__(self) -> None:
        self.xadd_calls: list[tuple[str, dict]] = []

    async def xadd(self, stream_name: str, mapping: dict, maxlen: int | None = None) -> str:
        self.xadd_calls.append((stream_name, mapping))
        return "1234567890-0"


@pytest.fixture
def reset_feed_status():
    """Reset the global feed_status_store for each test."""
    # Reset state
    feed_status_store._state.status = FeedStatus.LIVE
    feed_status_store._state.last_message_at = datetime.now(UTC)
    feed_status_store._state.entries_blocked = False
    feed_status_store.set_stale_timeout(60.0)
    yield
    # Cleanup: reset after test
    feed_status_store._state.status = FeedStatus.DOWN
    feed_status_store._state.last_message_at = None
    feed_status_store._state.entries_blocked = True


def test_stale_checker_publishes_when_stale(reset_feed_status) -> None:
    """Verify stale checker publishes feed_status event when feed becomes stale."""
    redis_client = FakeRedisClient()
    
    # Set last_message_at to 70 seconds ago (past 60s timeout)
    feed_status_store._state.last_message_at = datetime.now(UTC) - timedelta(seconds=70)
    feed_status_store._state.status = FeedStatus.LIVE
    feed_status_store._state.entries_blocked = False
    
    # Run stale checker once
    asyncio.run(_run_stale_checker_once(redis_client, "system.events"))
    
    # Should have published to system.events
    assert len(redis_client.xadd_calls) == 1
    stream_name, event = redis_client.xadd_calls[0]
    assert stream_name == "system.events"
    assert event["event_type"] == "feed_status"
    assert event["status"] == "stale"
    assert event["entries_blocked"] == "True"
    assert "stale" in event["message"].lower()
    
    # Feed status should be updated
    snapshot = feed_status_store.get_snapshot()
    assert snapshot["status"] == "stale"
    assert snapshot["entries_blocked"] is True


def test_stale_checker_no_publish_when_live(reset_feed_status) -> None:
    """Verify stale checker does not publish when feed is live."""
    redis_client = FakeRedisClient()
    
    # Set last_message_at to now (within timeout)
    feed_status_store._state.last_message_at = datetime.now(UTC)
    feed_status_store._state.status = FeedStatus.LIVE
    feed_status_store._state.entries_blocked = False
    
    # Run stale checker once
    asyncio.run(_run_stale_checker_once(redis_client, "system.events"))
    
    # Should not have published (feed is still live)
    assert len(redis_client.xadd_calls) == 0
    
    snapshot = feed_status_store.get_snapshot()
    assert snapshot["status"] == "live"
    assert snapshot["entries_blocked"] is False


def test_stale_checker_handles_redis_error(reset_feed_status) -> None:
    """Verify stale checker handles Redis errors gracefully."""
    redis_client = FakeRedisClient()
    redis_client.xadd = AsyncMock(side_effect=Exception("Redis connection error"))
    
    # Set to stale state
    feed_status_store._state.last_message_at = datetime.now(UTC) - timedelta(seconds=70)
    
    # Should not raise, just log error
    asyncio.run(_run_stale_checker_once(redis_client, "system.events"))


def test_feed_status_stale_timeout_configuration(reset_feed_status) -> None:
    """Verify stale timeout can be configured."""
    assert feed_status_store.get_stale_timeout() == 60.0
    
    feed_status_store.set_stale_timeout(30.0)
    assert feed_status_store.get_stale_timeout() == 30.0
    
    feed_status_store.set_stale_timeout(120.5)
    assert feed_status_store.get_stale_timeout() == 120.5

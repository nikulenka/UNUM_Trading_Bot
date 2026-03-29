from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.api.status import get_status
from app.core.feed_status import FeedStatus, feed_status_store


@pytest.fixture(autouse=True)
def reset_feed_status_state():
    original_status = feed_status_store._state.status
    original_last_message_at = feed_status_store._state.last_message_at
    original_entries_blocked = feed_status_store._state.entries_blocked

    yield

    feed_status_store._state.status = original_status
    feed_status_store._state.last_message_at = original_last_message_at
    feed_status_store._state.entries_blocked = original_entries_blocked


@pytest.mark.unit
def test_get_status_returns_global_feed_status_snapshot() -> None:
    current_time = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    feed_status_store._state.status = FeedStatus.STALE
    feed_status_store._state.last_message_at = current_time
    feed_status_store._state.entries_blocked = True

    result = asyncio.run(get_status())

    assert result == {
        "status": "stale",
        "last_message_at_utc": current_time.isoformat(),
        "entries_blocked": True,
    }

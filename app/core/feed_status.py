# app/core/feed_status.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Optional

class FeedStatus(str, Enum):
    """Enumeration of possible feed statuses."""

    LIVE = "live"
    STALE = "stale"
    DOWN = "down"

@dataclass
class FeedStatusState:
    """Dataclass representing the current feed status state."""

    status: FeedStatus = FeedStatus.DOWN
    last_message_at: Optional[datetime] = None
    entries_blocked: bool = True

class FeedStatusStore:
    """Simple global in-memory store.

    Not persisted; resets on process restart.
    Thread-safe operations using lock.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._state = FeedStatusState()

    def get_snapshot(self) -> dict:
        """Return current feed status as a dictionary.

        Returns:
            dict: Dictionary containing:
                - status: Current status value
                - last_message_at_utc: Timestamp or None
                - entries_blocked: Boolean flag
        """
        with self._lock:
            return {
                "status": self._state.status.value,
                "last_message_at_utc": (
                    self._state.last_message_at.isoformat()
                    if self._state.last_message_at
                    else None
                ),
                "entries_blocked": self._state.entries_blocked,
            }

    def mark_message_received(self) -> None:
        """Call this whenever a valid live ticker message arrives."""
        now = datetime.now(timezone.utc)
        with self._lock:
            self._state.last_message_at = now
            self._state.status = FeedStatus.LIVE
            self._state.entries_blocked = False

    def set_stale(self) -> None:
        """Call when ticker freshness timeout triggers."""
        with self._lock:
            self._state.status = FeedStatus.STALE
            self._state.entries_blocked = True

    def set_down(self) -> None:
        """Call when websocket disconnects / cannot reconnect."""
        with self._lock:
            self._state.status = FeedStatus.DOWN
            self._state.entries_blocked = True

    def set_status(self, status: FeedStatus) -> None:
        """Optional generic helper to set status.

        Args:
            status: Desired FeedStatus to set
        """
        if status == FeedStatus.LIVE:
            self.mark_message_received()
        elif status == FeedStatus.STALE:
            self.set_stale()
        else:
            self.set_down()
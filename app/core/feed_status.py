# app/core/feed_status.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Optional, Callable

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
    _status_change_callbacks: list[Callable[FeedStatus, None]] = field(default_factory=list)

class FeedStatusStore:
    """Simple global in-memory store.

    Not persisted; resets on process restart.
    Thread-safe operations using lock.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._state = FeedStatusState()
        self._stale_timeout_seconds: float = 60.0

    def set_stale_timeout(self, timeout_seconds: float) -> None:
        """Configure the stale timeout threshold."""
        with self._lock:
            self._stale_timeout_seconds = timeout_seconds

    def get_stale_timeout(self) -> float:
        """Get the current stale timeout threshold."""
        with self._lock:
            return self._stale_timeout_seconds

    def register_status_change_callback(self, callback: Callable[FeedStatus, None]) -> None:
        """Register a callback to be invoked when status changes."""
        with self._lock:
            self._state._status_change_callbacks.append(callback)

    def _notify_status_change(self, new_status: FeedStatus) -> None:
        """Notify all registered callbacks of status change."""
        for callback in self._state._status_change_callbacks:
            try:
                callback(new_status)
            except Exception:
                pass  # Don't let callback errors break status tracking

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
            old_status = self._state.status
            self._state.last_message_at = now
            self._state.status = FeedStatus.LIVE
            self._state.entries_blocked = False
            if old_status != FeedStatus.LIVE:
                self._notify_status_change(FeedStatus.LIVE)

    def check_stale(self) -> bool:
        """Check if feed is stale based on last message time.

        Returns:
            bool: True if feed is stale (no message within timeout), False otherwise.
        """
        with self._lock:
            if self._state.last_message_at is None:
                return True
            
            elapsed = (datetime.now(timezone.utc) - self._state.last_message_at).total_seconds()
            if elapsed > self._stale_timeout_seconds:
                if self._state.status != FeedStatus.STALE:
                    self._state.status = FeedStatus.STALE
                    self._state.entries_blocked = True
                    self._notify_status_change(FeedStatus.STALE)
                return True
            return False

    def set_stale(self) -> None:
        """Call when ticker freshness timeout triggers."""
        with self._lock:
            old_status = self._state.status
            self._state.status = FeedStatus.STALE
            self._state.entries_blocked = True
            if old_status != FeedStatus.STALE:
                self._notify_status_change(FeedStatus.STALE)

    def set_down(self) -> None:
        """Call when websocket disconnects / cannot reconnect."""
        with self._lock:
            old_status = self._state.status
            self._state.status = FeedStatus.DOWN
            self._state.entries_blocked = True
            if old_status != FeedStatus.DOWN:
                self._notify_status_change(FeedStatus.DOWN)

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


# Global singleton feed status store
feed_status_store = FeedStatusStore()

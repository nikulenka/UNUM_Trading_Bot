from __future__ import annotations

from app.dashboard.streams import read_recent_events


class FakeRedisClient:
    def __init__(self, rows: list[tuple[str, dict[str, str]]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str, str, int]] = []

    def xrevrange(self, stream_name: str, max: str, min: str, count: int):
        self.calls.append((stream_name, max, min, count))
        return self.rows


def test_read_recent_events_parses_payload_and_booleans() -> None:
    client = FakeRedisClient(
        [
            (
                "2-0",
                {
                    "event_type": "feed_status",
                    "status": "stale",
                    "entries_blocked": "true",
                    "updated_at_utc": "2026-03-25T00:00:02+00:00",
                    "message": "Feed marked stale",
                    "payload": "{\"reason\": \"timeout\"}",
                },
            ),
            (
                "1-0",
                {
                    "event_type": "ticker",
                    "instrument_id": "BTC_USDT",
                    "payload": "{\"last\": \"50000.00\"}",
                },
            ),
        ]
    )

    events = read_recent_events(client, "market.events", count=2)

    assert client.calls == [("market.events", "+", "-", 2)]
    assert [event["id"] for event in events] == ["1-0", "2-0"]
    assert events[0]["payload"] == {"last": "50000.00"}
    assert events[1]["entries_blocked"] is True
    assert events[1]["payload"] == {"reason": "timeout"}

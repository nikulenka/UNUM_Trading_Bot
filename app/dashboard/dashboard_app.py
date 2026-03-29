from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app.dashboard.config import get_dashboard_settings
from app.dashboard.streams import create_redis_client, read_recent_events

@st.cache_resource
def _get_redis_client(redis_dsn: str):
    return create_redis_client(redis_dsn)


def _build_price_frame(events: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue

        event_type = str(event.get("event_type", "")).lower()
        if event_type == "ticker":
            price = payload.get("last")
        elif event_type == "trade":
            price = payload.get("price")
        else:
            continue

        if price in (None, ""):
            continue

        timestamp = event.get("source_time_utc") or event.get("ingested_at_utc")
        rows.append(
            {
                "timestamp": timestamp,
                "price": price,
                "event_type": event_type,
                "instrument_id": event.get("instrument_id"),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    return frame.dropna(subset=["timestamp", "price"]).sort_values("timestamp")


def _select_columns(frame: pd.DataFrame, preferred_columns: tuple[str, ...]) -> pd.DataFrame:
    columns = [column for column in preferred_columns if column in frame.columns]
    return frame[columns] if columns else frame


def _render_market_tab(market_events: list[dict[str, Any]], price_frame: pd.DataFrame) -> None:
    if not market_events:
        st.info("No market events have been received yet.")
        return

    st.dataframe(
        _select_columns(
            pd.DataFrame(market_events),
            (
                "id",
                "event_type",
                "instrument_id",
                "source_symbol",
                "source_time_utc",
                "ingested_at_utc",
                "payload",
            ),
        ),
        use_container_width=True,
    )

    if price_frame.empty:
        st.info("No price points available for charting yet.")
        return

    st.subheader("Price history")
    st.line_chart(price_frame.set_index("timestamp")["price"])


def _render_system_tab(system_events: list[dict[str, Any]]) -> None:
    if not system_events:
        st.info("No system events have been received yet.")
        return

    latest = system_events[-1]
    status = str(latest.get("status", "unknown")).lower()
    entries_blocked = bool(latest.get("entries_blocked", False))
    updated_at = str(latest.get("updated_at_utc") or "—")

    status_columns = st.columns(3)
    status_columns[0].metric("Status", status.title())
    status_columns[1].metric("Entries blocked", "yes" if entries_blocked else "no")
    status_columns[2].metric("Updated at UTC", updated_at)

    if status == "live":
        st.success("Feed is live.")
    elif status == "stale":
        st.warning("Feed is stale.")
    elif status == "down":
        st.error("Feed is down.")
    else:
        st.info("Feed status is unknown.")

    st.dataframe(
        _select_columns(
            pd.DataFrame(system_events),
            ("id", "status", "entries_blocked", "updated_at_utc", "message"),
        ),
        use_container_width=True,
    )


def _render_signals_tab(signal_events: list[dict[str, Any]]) -> None:
    if not signal_events:
        st.info("No signal events have been received yet.")
        return

    st.dataframe(
        _select_columns(
            pd.DataFrame(signal_events),
            (
                "id",
                "event_type",
                "instrument_id",
                "source_symbol",
                "action",
                "received_at_utc",
                "payload_hash",
            ),
        ),
        use_container_width=True,
    )


def main() -> None:
    settings = get_dashboard_settings()
    st.set_page_config(page_title="Trade Bot Dashboard", layout="wide")

    refresh_interval_ms = max(1000, int(settings.refresh_interval_seconds * 1000))
    autorefresh = getattr(st, "autorefresh", None)
    if callable(autorefresh):
        autorefresh(interval=refresh_interval_ms, key="dashboard_refresh")

    st.title("Trade Bot Dashboard")
    st.caption("Minimal Redis Streams dashboard running inside Docker Compose.")
    st.caption("This dashboard reads Redis directly and stays isolated from the FastAPI app process.")

    st.sidebar.header("Sources")
    st.sidebar.write(f"Redis DSN: {settings.redis_dsn}")
    st.sidebar.write(f"Market stream: {settings.market_events_stream}")
    st.sidebar.write(f"System stream: {settings.system_events_stream}")
    st.sidebar.write(f"Signal stream: {settings.signal_events_stream}")
    st.sidebar.write(f"Refresh interval: {settings.refresh_interval_seconds:.1f}s")

    redis_client = _get_redis_client(settings.redis_dsn)

    try:
        redis_client.ping()
        market_events = read_recent_events(
            redis_client,
            settings.market_events_stream,
            count=settings.recent_event_limit,
        )
        system_events = read_recent_events(
            redis_client,
            settings.system_events_stream,
            count=settings.recent_system_event_limit,
        )
        signal_events = read_recent_events(
            redis_client,
            settings.signal_events_stream,
            count=settings.recent_signal_event_limit,
        )
    except Exception as exc:
        st.error(f"Unable to load dashboard data from Redis: {exc}")
        st.stop()

    price_frame = _build_price_frame(market_events)

    if system_events:
        latest_system_event = system_events[-1]
        feed_status = str(latest_system_event.get("status", "unknown")).title()
        entries_blocked = "yes" if bool(latest_system_event.get("entries_blocked", False)) else "no"
    else:
        feed_status = "Unknown"
        entries_blocked = "Unknown"

    summary_columns = st.columns(4)
    summary_columns[0].metric("Feed status", feed_status)
    summary_columns[1].metric("Entries blocked", entries_blocked)
    summary_columns[2].metric("Market events", len(market_events))
    summary_columns[3].metric("Price points", len(price_frame))

    market_tab, system_tab, signals_tab = st.tabs(["Market", "System", "Signals"])

    with market_tab:
        _render_market_tab(market_events, price_frame)

    with system_tab:
        _render_system_tab(system_events)

    with signals_tab:
        _render_signals_tab(signal_events)


if __name__ == "__main__":
    main()

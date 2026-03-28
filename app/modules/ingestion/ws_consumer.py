from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.feed_status import feed_status_store, FeedStatus
from app.modules.ingestion.gateio_ws import GateIOWebSocketClient

logger = logging.getLogger(__name__)


async def run_ws_consumer() -> None:
    """Run WebSocket consumer and stream events to Redis."""
    settings = get_settings()
    client = GateIOWebSocketClient(base_url=settings.gateio_ws_url)

    redis_client = redis.from_url(
        settings.redis_dsn,
        decode_responses=True,
    )

    # Configure stale timeout
    feed_status_store.set_stale_timeout(settings.feed_stale_timeout_seconds)

    logger.info(f"Connecting to Redis stream: {settings.market_events_stream}")
    logger.info(f"Feed stale timeout: {settings.feed_stale_timeout_seconds} seconds")

    # Start stale checker background task
    stale_checker_task = asyncio.create_task(
        _run_stale_checker(redis_client, settings.system_events_stream)
    )

    try:
        async for event in client.subscribe_market_data(
            currency_pair=settings.ws_currency_pair,
        ):
            try:
                # Update feed status (tracks last message time)
                feed_status_store.mark_message_received()

                # Write to Redis stream
                await redis_client.xadd(
                    settings.market_events_stream,
                    event,
                    maxlen=10000,
                )

                logger.info(f"Streamed {event['event_type']} event: {event['source_time_utc']}")

            except redis.RedisError as exc:
                logger.error(f"Redis error: {exc}")
            except Exception as exc:
                logger.error(f"Error processing event: {exc}")
    finally:
        # Cancel stale checker on exit
        stale_checker_task.cancel()
        try:
            await stale_checker_task
        except asyncio.CancelledError:
            pass
        await redis_client.aclose()


async def _run_stale_checker(redis_client: redis.Redis, stream_name: str) -> None:
    """Background task that periodically checks for stale feed and publishes status events."""
    while True:
        await asyncio.sleep(10.0)  # Check every 10 seconds
        
        try:
            is_stale = feed_status_store.check_stale()
            if is_stale:
                snapshot = feed_status_store.get_snapshot()
                status_event = {
                    "event_type": "feed_status",
                    "status": snapshot["status"],
                    "entries_blocked": str(snapshot["entries_blocked"]),
                    "updated_at_utc": datetime.now(UTC).isoformat(),
                    "message": "Feed marked stale - no ticker message within timeout",
                }
                await redis_client.xadd(stream_name, status_event, maxlen=1000)
                logger.warning("Feed status changed to STALE")
        except redis.RedisError as exc:
            logger.error(f"Redis error in stale checker: {exc}")
        except Exception as exc:
            logger.error(f"Error in stale checker: {exc}")


async def _run_stale_checker_once(redis_client: redis.Redis, stream_name: str) -> None:
    """Check stale status once and publish if needed. Used for testing."""
    try:
        is_stale = feed_status_store.check_stale()
        if is_stale:
            snapshot = feed_status_store.get_snapshot()
            status_event = {
                "event_type": "feed_status",
                "status": snapshot["status"],
                "entries_blocked": str(snapshot["entries_blocked"]),
                "updated_at_utc": datetime.now(UTC).isoformat(),
                "message": "Feed marked stale - no ticker message within timeout",
            }
            await redis_client.xadd(stream_name, status_event, maxlen=1000)
            logger.warning("Feed status changed to STALE")
    except redis.RedisError as exc:
        logger.error(f"Redis error in stale checker: {exc}")
    except Exception as exc:
        logger.error(f"Error in stale checker: {exc}")


def _publish_feed_status_change(
    redis_client: redis.Redis,
    stream_name: str,
    new_status: FeedStatus,
) -> None:
    """Publish feed status change event to system.events stream."""
    # snapshot = feed_status_store.get_snapshot()
    # status_event = {
    #     "event_type": "feed_status",
    #     "status": snapshot["status"],
    #     "entries_blocked": str(snapshot["entries_blocked"]),
    #     "updated_at_utc": datetime.now(UTC).isoformat(),
    #     "message": f"Feed status changed to {new_status.value}",
    # }
    # Note: This is synchronous - used for callback-based publishing
    # For async context, use asyncio.create_task with async version
    logger.info(f"Feed status changed to {new_status.value}")

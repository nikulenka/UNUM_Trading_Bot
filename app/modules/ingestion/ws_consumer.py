from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.feed_status import feed_status_store, FeedStatus
from app.modules.ingestion.gateio_ws import GateIOWebSocketClient

logger = logging.getLogger(__name__)


async def _process_market_event(
    redis_client: redis.Redis,
    *,
    market_stream_name: str,
    system_stream_name: str,
    event: dict[str, object],
) -> None:
    previous_status = str(feed_status_store.get_snapshot()["status"])
    feed_status_store.mark_message_received()

    await redis_client.xadd(
        market_stream_name,
        event,
        maxlen=10000,
    )

    if previous_status != FeedStatus.LIVE.value:
        await _publish_feed_status_event(
            redis_client,
            system_stream_name,
            message="Feed marked live - market data messages resumed",
        )
        logger.info("Feed status changed to LIVE")


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
                await _process_market_event(
                    redis_client,
                    market_stream_name=settings.market_events_stream,
                    system_stream_name=settings.system_events_stream,
                    event=event,
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
                await _publish_feed_status_event(
                    redis_client,
                    stream_name,
                    message="Feed marked stale - no ticker message within timeout",
                )
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
            await _publish_feed_status_event(
                redis_client,
                stream_name,
                message="Feed marked stale - no ticker message within timeout",
            )
            logger.warning("Feed status changed to STALE")
    except redis.RedisError as exc:
        logger.error(f"Redis error in stale checker: {exc}")
    except Exception as exc:
        logger.error(f"Error in stale checker: {exc}")


async def _publish_feed_status_event(
    redis_client: redis.Redis,
    stream_name: str,
    *,
    message: str,
) -> None:
    """Publish a feed status event to the system stream."""
    snapshot = feed_status_store.get_snapshot()
    status_event = {
        "event_type": "feed_status",
        "status": snapshot["status"],
        "entries_blocked": str(snapshot["entries_blocked"]),
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "message": message,
    }
    await redis_client.xadd(stream_name, status_event, maxlen=1000)

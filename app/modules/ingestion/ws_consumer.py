from __future__ import annotations

import logging

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.feed_status import feed_status_store
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

    logger.info(f"Connecting to Redis stream: {settings.market_events_stream}")

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

    await redis_client.close()

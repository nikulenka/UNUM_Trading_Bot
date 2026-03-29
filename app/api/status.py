import logging

from fastapi import APIRouter

from app.core.feed_status import feed_status_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ingestion/status")
async def get_status() -> dict:
    """Endpoint to get the current feed ingestion status."""
    logger.debug("Ingestion status check started")
    return feed_status_store.get_snapshot()

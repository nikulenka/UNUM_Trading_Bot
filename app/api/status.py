import logging

from fastapi import APIRouter

from app.core.feed_status import FeedStatusStore

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/ingestion/status")
async def get_status() -> dict:
    """Endpoint to get the current feed ingestion status.

    Returns:
        dict: The current status of the feed ingestion.
    """
    logger.debug("Ingestion status check started")
    store = FeedStatusStore()

    return store.get_snapshot()

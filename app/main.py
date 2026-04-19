from fastapi import FastAPI

import asyncio
import logging
from contextlib import asynccontextmanager

from app.api.health import router as health_router
from app.api.ready import router as ready_router
from app.api.status import router as status_router
from app.api.tradingview import router as tradingview_router
from app.core.config import validate_settings
from app.core.logging import setup_logging
from app.modules.ingestion.ws_consumer import run_ws_consumer

setup_logging("INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = validate_settings()
    setup_logging(settings.log_level)
    logger.info(f"Application startup initiated with profile: {settings.app_env}")

    # Start WebSocket consumer as background task
    ws_task = None
    if settings.ws_enabled:
        ws_task = asyncio.create_task(run_ws_consumer())
        logger.info("WebSocket consumer started")

    yield

    # Cleanup
    if ws_task:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
        logger.info("WebSocket consumer stopped")

    logger.info("Application shutdown completed")


app = FastAPI(title="AI Bot", lifespan=lifespan)

app.include_router(health_router)
app.include_router(ready_router)
app.include_router(status_router)
app.include_router(tradingview_router)

logger.info("Application configured successfully")

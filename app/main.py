import uvicorn
from fastapi import FastAPI

import logging
from contextlib import asynccontextmanager

from app.api.health import router as health_router
from app.api.ready import router as ready_router
from app.core.config import get_settings, validate_settings
from app.core.logging import setup_logging

setup_logging("INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = validate_settings()
    setup_logging(settings.log_level)
    logger.info(f"Application startup initiated with profile: {settings.app_env}")
    yield
    logger.info("Application shutdown completed")


app = FastAPI(title="AI Bot", lifespan=lifespan)

app.include_router(health_router)
app.include_router(ready_router)

logger.info("Application configured successfully")

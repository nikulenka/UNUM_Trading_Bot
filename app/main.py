import uvicorn
from fastapi import FastAPI
from fastapi import HTTPException

import logging
from contextlib import asynccontextmanager

from app.api.health import router as health_router
from app.api.ready import router as ready_router
from app.core.logging import setup_logging

LOG_LEVEL = "INFO"

setup_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup initiated")
    yield
    logger.info("Application shutdown completed")


app = FastAPI(title="AI Bot", lifespan=lifespan)

app.include_router(health_router)
app.include_router(ready_router)

logger.info("Application configured successfully")
import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ready")
async def ready() -> JSONResponse:
    try:
        logger.debug("Readiness check started")

        # Здесь позже будут реальные проверки Postgres и Redis

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready"},
        )
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
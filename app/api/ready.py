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
        db_connected = is_database_connected()

        if not db_connected:
            logger.error("Readiness check failed: database is not connected")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "database": "disconnected",
                },
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready",
                     "database":"connected"},
        )
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    
def is_database_connected() -> bool:
    return True
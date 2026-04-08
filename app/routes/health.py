from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health_service import get_health_status

router = APIRouter(tags=["Health"])


@router.get("/", response_model=HealthResponse, summary="Health check")
async def health_check() -> HealthResponse:
    return await get_health_status()

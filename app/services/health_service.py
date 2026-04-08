from app.schemas.health import HealthResponse


async def get_health_status() -> HealthResponse:
    return HealthResponse()

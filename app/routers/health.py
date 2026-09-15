"""Liveness check. Intentionally NOT behind API-key auth -- load balancers, container
orchestrators (Docker, Kubernetes) and uptime monitors need to hit this endpoint anonymously.
"""

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Returns 200 with `{\"status\": \"ok\"}` if the service process is up. "
    "Does not touch the database, so it stays fast and cheap for frequent polling.",
)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")

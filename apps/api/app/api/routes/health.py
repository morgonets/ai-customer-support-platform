from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.database import database_from_app_state
from app.core.errors import ApiError

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["api"]
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Check process health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", service="api", environment=settings.environment)


@router.get("/ready", response_model=HealthResponse, summary="Check dependency readiness")
async def readiness(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> HealthResponse:
    try:
        await database_from_app_state(request.app.state).ping()
    except SQLAlchemyError as exc:
        raise ApiError(
            status_code=503,
            code="dependency_unavailable",
            message="A required service is unavailable.",
        ) from exc
    return HealthResponse(status="ok", service="api", environment=settings.environment)

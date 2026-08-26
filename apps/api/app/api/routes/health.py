from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["api"]
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Check process health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", service="api", environment=settings.environment)

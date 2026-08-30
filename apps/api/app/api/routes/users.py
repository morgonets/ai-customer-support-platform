from fastapi import APIRouter
from pydantic import BaseModel

from app.api.dependencies import CurrentActor

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class CurrentUserResponse(BaseModel):
    id: str
    email: str | None


@router.get("/me", response_model=CurrentUserResponse, summary="Get the authenticated user")
def get_current_user(actor: CurrentActor) -> CurrentUserResponse:
    return CurrentUserResponse(id=str(actor.user_id), email=actor.email)

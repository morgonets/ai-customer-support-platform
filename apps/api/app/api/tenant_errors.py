from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import ApiError, api_error_handler
from app.tenants.errors import (
    LastOwnerRequiredError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    MembershipUserNotFoundError,
    OrganizationNotFoundError,
    TenantAuthorizationError,
    TenantError,
)


async def tenant_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, TenantError):
        raise exc

    if isinstance(exc, OrganizationNotFoundError):
        api_error = ApiError(
            status_code=404,
            code="organization_not_found",
            message="The organization was not found.",
        )
    elif isinstance(exc, MembershipNotFoundError):
        api_error = ApiError(
            status_code=404,
            code="membership_not_found",
            message="The membership was not found.",
        )
    elif isinstance(exc, TenantAuthorizationError):
        api_error = ApiError(
            status_code=403,
            code="insufficient_role",
            message="Your organization role does not allow this action.",
        )
    elif isinstance(exc, MembershipAlreadyExistsError):
        api_error = ApiError(
            status_code=409,
            code="membership_already_exists",
            message="The user is already a member of this organization.",
        )
    elif isinstance(exc, MembershipUserNotFoundError):
        api_error = ApiError(
            status_code=404,
            code="membership_user_not_found",
            message="The user was not found.",
        )
    elif isinstance(exc, LastOwnerRequiredError):
        api_error = ApiError(
            status_code=409,
            code="last_owner_required",
            message="The organization must retain at least one owner.",
        )
    else:  # pragma: no cover - forces exhaustive review when a new domain error is added.
        raise exc
    return await api_error_handler(request, api_error)

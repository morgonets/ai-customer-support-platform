class TenantError(Exception):
    """Base class for expected organization-domain failures."""


class OrganizationNotFoundError(TenantError):
    pass


class MembershipNotFoundError(TenantError):
    pass


class TenantAuthorizationError(TenantError):
    pass


class MembershipAlreadyExistsError(TenantError):
    pass


class MembershipUserNotFoundError(TenantError):
    pass


class LastOwnerRequiredError(TenantError):
    pass

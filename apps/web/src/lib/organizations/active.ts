export const ACTIVE_ORGANIZATION_COOKIE = "active_organization_id";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function validOrganizationId(value: string | undefined): string | null {
  return value !== undefined && uuidPattern.test(value) ? value.toLowerCase() : null;
}

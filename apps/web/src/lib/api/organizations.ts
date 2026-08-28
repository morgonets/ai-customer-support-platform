import { productApiRequest } from "./client";

export type OrganizationRole = "owner" | "admin" | "member";

export interface Organization {
  created_at: string;
  id: string;
  name: string;
  role: OrganizationRole;
  updated_at: string;
}

export interface Membership {
  created_at: string;
  display_name: string | null;
  id: string;
  organization_id: string;
  role: OrganizationRole;
  updated_at: string;
  user_id: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function role(value: unknown): OrganizationRole {
  if (value === "owner" || value === "admin" || value === "member") {
    return value;
  }
  throw new Error("The product API returned an invalid organization role");
}

function stringField(record: Record<string, unknown>, name: string): string {
  const value = record[name];
  if (typeof value !== "string") {
    throw new Error(`The product API returned an invalid ${name}`);
  }
  return value;
}

export function parseOrganization(value: unknown): Organization {
  if (!isRecord(value)) {
    throw new Error("The product API returned an invalid organization");
  }
  return {
    id: stringField(value, "id"),
    name: stringField(value, "name"),
    role: role(value.role),
    created_at: stringField(value, "created_at"),
    updated_at: stringField(value, "updated_at"),
  };
}

export function parseMembership(value: unknown): Membership {
  if (!isRecord(value)) {
    throw new Error("The product API returned an invalid membership");
  }
  const displayName = value.display_name;
  if (displayName !== null && typeof displayName !== "string") {
    throw new Error("The product API returned an invalid display_name");
  }
  return {
    id: stringField(value, "id"),
    organization_id: stringField(value, "organization_id"),
    user_id: stringField(value, "user_id"),
    display_name: displayName,
    role: role(value.role),
    created_at: stringField(value, "created_at"),
    updated_at: stringField(value, "updated_at"),
  };
}

function parseArray<T>(value: unknown, parser: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) {
    throw new Error("The product API returned an invalid collection");
  }
  return value.map(parser);
}

export async function listOrganizations(accessToken: string): Promise<Organization[]> {
  return parseArray(
    await productApiRequest("/api/v1/organizations", accessToken),
    parseOrganization,
  );
}

export async function createOrganization(accessToken: string, name: string): Promise<Organization> {
  return parseOrganization(
    await productApiRequest("/api/v1/organizations", accessToken, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  );
}

export async function getOrganization(
  accessToken: string,
  organizationId: string,
): Promise<Organization> {
  return parseOrganization(
    await productApiRequest(`/api/v1/organizations/${organizationId}`, accessToken),
  );
}

export async function listMemberships(
  accessToken: string,
  organizationId: string,
): Promise<Membership[]> {
  return parseArray(
    await productApiRequest(`/api/v1/organizations/${organizationId}/memberships`, accessToken),
    parseMembership,
  );
}

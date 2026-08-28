import { beforeEach, describe, expect, it, vi } from "vitest";

import { productApiRequest } from "./client";
import {
  createOrganization,
  getOrganization,
  listMemberships,
  listOrganizations,
  parseMembership,
  parseOrganization,
} from "./organizations";

vi.mock("./client", () => ({ productApiRequest: vi.fn() }));

const organization = {
  id: "organization-id",
  name: "Example",
  role: "owner",
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
} as const;

const membership = {
  id: "membership-id",
  organization_id: "organization-id",
  user_id: "user-id",
  display_name: "Example Person",
  role: "member",
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
} as const;

beforeEach(() => {
  vi.mocked(productApiRequest).mockReset();
});

describe("organization product API", () => {
  it("parses and requests organization operations", async () => {
    vi.mocked(productApiRequest)
      .mockResolvedValueOnce([organization])
      .mockResolvedValueOnce(organization)
      .mockResolvedValueOnce({ ...organization, role: "admin" });

    await expect(listOrganizations("token")).resolves.toEqual([organization]);
    await expect(createOrganization("token", "Example")).resolves.toEqual(organization);
    await expect(getOrganization("token", "organization-id")).resolves.toMatchObject({
      role: "admin",
    });
    expect(productApiRequest).toHaveBeenNthCalledWith(2, "/api/v1/organizations", "token", {
      method: "POST",
      body: JSON.stringify({ name: "Example" }),
    });
  });

  it("parses and requests membership listing", async () => {
    vi.mocked(productApiRequest).mockResolvedValue([
      membership,
      { ...membership, display_name: null },
    ]);

    const memberships = await listMemberships("token", "organization-id");

    expect(memberships).toHaveLength(2);
    expect(memberships[1]?.display_name).toBeNull();
  });

  it.each([null, [], "invalid"])("rejects malformed organization values", (value) => {
    expect(() => parseOrganization(value)).toThrow("invalid organization");
  });

  it("rejects malformed organization fields and roles", () => {
    expect(() => parseOrganization({ ...organization, name: null })).toThrow("invalid name");
    expect(() => parseOrganization({ ...organization, role: "billing_admin" })).toThrow(
      "invalid organization role",
    );
    expect(parseOrganization({ ...organization, role: "member" }).role).toBe("member");
  });

  it("rejects malformed membership values and display names", () => {
    expect(() => parseMembership(null)).toThrow("invalid membership");
    expect(() => parseMembership({ ...membership, display_name: 7 })).toThrow(
      "invalid display_name",
    );
  });

  it("rejects a malformed collection", async () => {
    vi.mocked(productApiRequest).mockResolvedValue({ not: "an array" });

    await expect(listOrganizations("token")).rejects.toThrow("invalid collection");
  });
});

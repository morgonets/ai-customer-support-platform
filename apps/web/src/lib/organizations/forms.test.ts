import { describe, expect, it } from "vitest";

import { organizationName, selectedOrganizationId } from "./forms";

describe("organization forms", () => {
  it("trims a bounded name and reads the selected ID", () => {
    const data = new FormData();
    data.set("name", "  Example Organization  ");
    data.set("organization_id", "organization-id");

    expect(organizationName(data)).toBe("Example Organization");
    expect(selectedOrganizationId(data)).toBe("organization-id");
  });

  it("rejects absent, non-string, empty, and oversized names", () => {
    expect(organizationName(new FormData())).toBeNull();
    const blobData = new FormData();
    blobData.set("name", new Blob());
    blobData.set("organization_id", new Blob());
    expect(organizationName(blobData)).toBeNull();
    expect(selectedOrganizationId(blobData)).toBeNull();
    const emptyData = new FormData();
    emptyData.set("name", "   ");
    expect(organizationName(emptyData)).toBeNull();
    const oversizedData = new FormData();
    oversizedData.set("name", "x".repeat(101));
    expect(organizationName(oversizedData)).toBeNull();
  });
});

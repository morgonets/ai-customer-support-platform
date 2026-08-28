import { describe, expect, it } from "vitest";

import { validOrganizationId } from "./active";

describe("validOrganizationId", () => {
  it("normalizes a valid UUID", () => {
    expect(validOrganizationId("20000000-0000-4000-8000-0000000000AB")).toBe(
      "20000000-0000-4000-8000-0000000000ab",
    );
  });

  it.each([undefined, "", "not-a-uuid", "20000000-0000-0000-0000-000000000001"])(
    "rejects invalid organization IDs",
    (value) => {
      expect(validOrganizationId(value)).toBeNull();
    },
  );
});

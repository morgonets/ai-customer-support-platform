import { describe, expect, it } from "vitest";

import { organizationErrorMessage } from "./messages";

describe("organizationErrorMessage", () => {
  it("maps only known public codes", () => {
    expect(organizationErrorMessage("invalid_name")).toContain("between 1 and 100");
    expect(organizationErrorMessage("unknown")).toBeNull();
    expect(organizationErrorMessage(undefined)).toBeNull();
  });
});

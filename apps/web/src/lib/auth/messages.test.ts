import { describe, expect, it } from "vitest";

import { authErrorMessage } from "./messages";

describe("authErrorMessage", () => {
  it("maps a known safe code", () => {
    expect(authErrorMessage("invalid_credentials")).toBe("The email or password is incorrect.");
  });

  it("does not reflect unknown input", () => {
    expect(authErrorMessage("<script>alert(1)</script>")).toBeNull();
    expect(authErrorMessage(undefined)).toBeNull();
  });
});

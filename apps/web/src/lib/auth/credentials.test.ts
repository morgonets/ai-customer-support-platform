import { describe, expect, it } from "vitest";

import { parseCredentials, parseEmail, parseNewPassword } from "./credentials";

function formData(values: Record<string, string | Blob>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(values)) {
    data.set(name, value);
  }
  return data;
}

describe("auth form validation", () => {
  it("normalizes valid credentials", () => {
    expect(
      parseCredentials(formData({ email: " Person@Example.COM ", password: " password1 " })),
    ).toEqual({ email: "person@example.com", password: " password1 " });
  });

  it.each([
    formData({ email: "not-an-email", password: "password1" }),
    formData({ email: "person@example.com", password: "short" }),
    formData({ password: "password1" }),
    formData({ email: new Blob(), password: "password1" }),
    formData({ email: "person@example.com", password: new Blob() }),
  ])("rejects invalid credentials", (data) => {
    expect(parseCredentials(data)).toBeNull();
  });

  it("accepts only plausible email values", () => {
    expect(parseEmail(formData({ email: " Person@Example.COM " }))).toBe("person@example.com");
    expect(parseEmail(formData({ email: "invalid" }))).toBeNull();
    expect(parseEmail(formData({ email: new Blob() }))).toBeNull();
  });

  it("requires a bounded provider-compatible password shape", () => {
    expect(parseNewPassword(formData({ password: "support8" }))).toBe("support8");
    expect(parseNewPassword(formData({ password: "onlyletters" }))).toBeNull();
    expect(parseNewPassword(formData({ password: "12345678" }))).toBeNull();
    expect(parseNewPassword(formData({ password: "a1" }))).toBeNull();
    expect(parseNewPassword(formData({ password: new Blob() }))).toBeNull();
  });
});

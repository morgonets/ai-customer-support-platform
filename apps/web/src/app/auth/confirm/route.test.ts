import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const authMocks = vi.hoisted(() => ({
  exchangeCodeForSession: vi.fn(),
  verifyOtp: vi.fn(),
}));

vi.mock("@/lib/supabase/server", () => ({
  createServerSupabaseClient: vi.fn().mockResolvedValue({ auth: authMocks }),
}));

function request(search = ""): NextRequest {
  return new NextRequest(`http://localhost:3000/auth/confirm${search}`);
}

beforeEach(() => {
  authMocks.exchangeCodeForSession.mockReset();
  authMocks.verifyOtp.mockReset();
});

describe("GET /auth/confirm", () => {
  it("exchanges a PKCE code and permits the recovery destination", async () => {
    authMocks.exchangeCodeForSession.mockResolvedValue({ error: null });

    const response = await GET(request("?code=provider-code&next=/reset-password"));

    expect(authMocks.exchangeCodeForSession).toHaveBeenCalledWith("provider-code");
    expect(response.headers.get("location")).toBe("http://localhost:3000/reset-password");
  });

  it("verifies an allowlisted email OTP type", async () => {
    authMocks.verifyOtp.mockResolvedValue({ error: null });

    const response = await GET(request("?token_hash=provider-token&type=signup"));

    expect(authMocks.verifyOtp).toHaveBeenCalledWith({
      token_hash: "provider-token",
      type: "signup",
    });
    expect(response.headers.get("location")).toBe("http://localhost:3000/app");
  });

  it("rejects failed exchanges and disallowed redirect destinations", async () => {
    authMocks.exchangeCodeForSession.mockResolvedValue({ error: new Error("invalid code") });

    const response = await GET(request("?code=bad-code&next=https://attacker.example"));

    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login?error=confirmation_failed",
    );
  });

  it.each(["", "?token_hash=provider-token&type=magiclink", "?token_hash=provider-token"])(
    "rejects missing or unsupported confirmation input",
    async (search) => {
      const response = await GET(request(search));

      expect(authMocks.verifyOtp).not.toHaveBeenCalled();
      expect(response.headers.get("location")).toBe(
        "http://localhost:3000/login?error=confirmation_failed",
      );
    },
  );

  it("rejects an invalid email OTP", async () => {
    authMocks.verifyOtp.mockResolvedValue({ error: new Error("invalid token") });

    const response = await GET(request("?token_hash=bad-token&type=recovery"));

    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login?error=confirmation_failed",
    );
  });
});

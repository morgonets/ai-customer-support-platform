import type { SupabaseClient } from "@supabase/supabase-js";
import { describe, expect, it, vi } from "vitest";

import { getAuthenticatedIdentity } from "./identity";

function clientReturning(result: unknown): SupabaseClient {
  return {
    auth: { getClaims: vi.fn().mockResolvedValue(result) },
  } as unknown as SupabaseClient;
}

describe("getAuthenticatedIdentity", () => {
  it("returns verified identity claims", async () => {
    const identity = await getAuthenticatedIdentity(
      clientReturning({
        data: { claims: { sub: "user-id", email: "person@example.com" } },
        error: null,
      }),
    );

    expect(identity).toEqual({ userId: "user-id", email: "person@example.com" });
  });

  it("allows an authenticated identity without an email claim", async () => {
    const identity = await getAuthenticatedIdentity(
      clientReturning({ data: { claims: { sub: "user-id", email: 7 } }, error: null }),
    );

    expect(identity).toEqual({ userId: "user-id", email: null });
  });

  it.each([
    { data: null, error: null },
    { data: null, error: new Error("invalid token") },
    { data: { claims: { sub: "" } }, error: null },
    { data: { claims: { sub: 7 } }, error: null },
  ])("fails closed for unverified or invalid claims", async (result) => {
    await expect(getAuthenticatedIdentity(clientReturning(result))).resolves.toBeNull();
  });
});

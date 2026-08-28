import { afterEach, describe, expect, it, vi } from "vitest";

import { getAppUrl, getSupabasePublicConfig } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Supabase configuration", () => {
  it("returns configured public values and canonical app origin", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "http://127.0.0.1:54321");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "local-publishable-key");
    vi.stubEnv("APP_URL", "http://localhost:3000");

    expect(getSupabasePublicConfig()).toEqual({
      url: "http://127.0.0.1:54321",
      publishableKey: "local-publishable-key",
    });
    expect(getAppUrl()).toBe("http://localhost:3000");
  });

  it.each(["", "replace-with-local-publishable-key"])(
    "rejects missing or placeholder browser configuration",
    (value) => {
      vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "http://127.0.0.1:54321");
      vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", value);

      expect(() => getSupabasePublicConfig()).toThrow("must be configured");
    },
  );

  it("rejects an application URL with path state", () => {
    vi.stubEnv("APP_URL", "https://support.example.com/not-an-origin?unsafe=true#fragment");

    expect(() => getAppUrl()).toThrow("must be an origin");
  });
});

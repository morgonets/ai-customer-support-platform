import { afterEach, describe, expect, it, vi } from "vitest";

import { getApiBaseUrl } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getApiBaseUrl", () => {
  it("prefers the server-only internal URL", () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");

    expect(getApiBaseUrl()).toBe("http://api:8000");
  });

  it("uses the public URL during host development", () => {
    vi.stubEnv("API_INTERNAL_URL", "");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");

    expect(getApiBaseUrl()).toBe("http://localhost:8000");
  });

  it.each(["", "replace-with-api-url"])("rejects missing or placeholder values", (value) => {
    vi.stubEnv("API_INTERNAL_URL", value);
    vi.stubEnv("NEXT_PUBLIC_API_URL", value);

    expect(() => getApiBaseUrl()).toThrow("must be configured");
  });

  it("rejects URL path state", () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.example.com/api?unsafe=true#fragment");

    expect(() => getApiBaseUrl()).toThrow("must be an origin");
  });
});

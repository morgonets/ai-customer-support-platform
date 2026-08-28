import { afterEach, describe, expect, it, vi } from "vitest";

import { ProductApiError, productApiRequest } from "./client";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function jsonResponse(value: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(value), {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
}

describe("productApiRequest", () => {
  it("sends the verified bearer token and parses success JSON", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "organization-id" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      productApiRequest("/api/v1/organizations", "access-token", {
        method: "POST",
        body: JSON.stringify({ name: "Example" }),
      }),
    ).resolves.toEqual({ id: "organization-id" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe("http://localhost:8000/api/v1/organizations");
    expect(init.cache).toBe("no-store");
    expect(headers.get("Authorization")).toBe("Bearer access-token");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("handles an empty success response without adding a content type", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(productApiRequest("/api/v1/organizations", "token")).resolves.toBeNull();
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("returns a stable typed API failure", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: "organization_not_found", request_id: "request-id" } },
            { status: 404 },
          ),
        ),
    );

    const error = await productApiRequest("/api/v1/organizations/id", "token").catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ProductApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "organization_not_found",
      requestId: "request-id",
      name: "ProductApiError",
    });
  });

  it.each([
    jsonResponse({}, { status: 500 }),
    jsonResponse({ error: { code: 7, request_id: 8 } }, { status: 500 }),
    new Response("not-json", { status: 502 }),
  ])("falls back safely for malformed error responses", async (response) => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expect(productApiRequest("/api/v1/organizations", "token")).rejects.toMatchObject({
      code: "api_error",
      requestId: null,
    });
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProductApiError, productApiResponse } from "@/lib/api/client";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";

import { GET } from "./route";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  productApiResponse: vi.fn(),
}));
vi.mock("@/lib/auth/access-token", () => ({ getVerifiedAccessToken: vi.fn() }));

const organizationId = "20000000-0000-4000-8000-000000000001";
const sourceId = "40000000-0000-4000-8000-000000000001";

function context(organization = organizationId, source = sourceId) {
  return { params: Promise.resolve({ organizationId: organization, sourceId: source }) };
}

beforeEach(() => {
  vi.mocked(productApiResponse).mockReset();
  vi.mocked(getVerifiedAccessToken).mockReset();
});

describe("GET original knowledge file", () => {
  it("streams only safe file headers through the authenticated FastAPI boundary", async () => {
    vi.mocked(getVerifiedAccessToken).mockResolvedValue("access-token");
    vi.mocked(productApiResponse).mockResolvedValue(
      new Response("private content", {
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''guide.txt",
          "Content-Length": "15",
          "Content-Type": "text/plain",
          "Set-Cookie": "never-forward=true",
          "X-Content-Type-Options": "nosniff",
        },
      }),
    );

    const response = await GET(
      new Request("http://localhost:3000/app/org/knowledge/source/file"),
      context(),
    );

    expect(await response.text()).toBe("private content");
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(productApiResponse).toHaveBeenCalledWith(
      `/api/v1/organizations/${organizationId}/knowledge-sources/${sourceId}/file`,
      "access-token",
      { headers: { Accept: "application/octet-stream" } },
    );
  });

  it("rejects invalid identifiers before calling the product API", async () => {
    const response = await GET(new Request("http://localhost:3000/file"), context("invalid"));

    expect(response.status).toBe(404);
    expect(productApiResponse).not.toHaveBeenCalled();
  });

  it("redirects missing authentication to login", async () => {
    vi.mocked(getVerifiedAccessToken).mockResolvedValue(null);

    const response = await GET(new Request("http://localhost:3000/file"), context());

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("http://localhost:3000/login");
  });

  it("redirects denied or unavailable downloads to safe workspace feedback", async () => {
    vi.mocked(getVerifiedAccessToken).mockResolvedValue("access-token");
    vi.mocked(productApiResponse).mockRejectedValue(
      new ProductApiError(403, "insufficient_role", "request-id"),
    );

    const response = await GET(new Request("http://localhost:3000/file"), context());

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      `http://localhost:3000/app/${organizationId}/knowledge/${sourceId}?error=download_failed`,
    );
  });
});

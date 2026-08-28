import { getApiBaseUrl } from "./config";

interface PublicErrorBody {
  code: string;
  request_id: string | null;
}

export class ProductApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly requestId: string | null,
  ) {
    super(`Product API request failed: ${code}`);
    this.name = "ProductApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function publicError(payload: unknown): PublicErrorBody {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return { code: "api_error", request_id: null };
  }
  return {
    code: typeof payload.error.code === "string" ? payload.error.code : "api_error",
    request_id: typeof payload.error.request_id === "string" ? payload.error.request_id : null,
  };
}

async function responsePayload(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function productApiRequest(
  path: `/${string}`,
  accessToken: string,
  init: RequestInit = {},
): Promise<unknown> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers,
  });
  const payload = await responsePayload(response);
  if (!response.ok) {
    const error = publicError(payload);
    throw new ProductApiError(response.status, error.code, error.request_id);
  }
  return payload;
}

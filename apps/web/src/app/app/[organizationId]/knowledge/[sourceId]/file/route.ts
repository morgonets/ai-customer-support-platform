import { NextResponse } from "next/server";

import { ProductApiError, productApiResponse } from "@/lib/api/client";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";
import { validKnowledgeId } from "@/lib/knowledge/forms";

interface DownloadRouteContext {
  params: Promise<{ organizationId: string; sourceId: string }>;
}

export async function GET(request: Request, { params }: DownloadRouteContext): Promise<Response> {
  const { organizationId: rawOrganizationId, sourceId: rawSourceId } = await params;
  const organizationId = validKnowledgeId(rawOrganizationId);
  const sourceId = validKnowledgeId(rawSourceId);
  if (organizationId === null || sourceId === null) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  const accessToken = await getVerifiedAccessToken();
  if (accessToken === null) {
    return NextResponse.redirect(new URL("/login", request.url), 303);
  }
  try {
    const response = await productApiResponse(
      `/api/v1/organizations/${organizationId}/knowledge-sources/${sourceId}/file`,
      accessToken,
      { headers: { Accept: "application/octet-stream" } },
    );
    const headers = new Headers();
    for (const name of [
      "Content-Disposition",
      "Content-Length",
      "Content-Type",
      "X-Content-Type-Options",
    ]) {
      const value = response.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    headers.set("Cache-Control", "private, no-store");
    return new Response(response.body, { status: 200, headers });
  } catch (error) {
    if (!(error instanceof ProductApiError)) throw error;
    return NextResponse.redirect(
      new URL(`/app/${organizationId}/knowledge/${sourceId}?error=download_failed`, request.url),
      303,
    );
  }
}

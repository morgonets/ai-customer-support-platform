"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ProductApiError } from "@/lib/api/client";
import { createOrganization, getOrganization } from "@/lib/api/organizations";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";
import { getAppUrl } from "@/lib/supabase/config";
import { ACTIVE_ORGANIZATION_COOKIE, validOrganizationId } from "@/lib/organizations/active";
import { organizationName, selectedOrganizationId } from "@/lib/organizations/forms";

async function requiredAccessToken(): Promise<string> {
  const accessToken = await getVerifiedAccessToken();
  if (accessToken === null) {
    redirect("/login");
  }
  return accessToken;
}

async function rememberOrganization(organizationId: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(ACTIVE_ORGANIZATION_COOKIE, organizationId, {
    httpOnly: true,
    maxAge: 60 * 60 * 24 * 365,
    path: "/",
    sameSite: "lax",
    secure: getAppUrl().startsWith("https://"),
  });
}

export async function createOrganizationAction(formData: FormData): Promise<never> {
  const name = organizationName(formData);
  if (name === null) {
    redirect("/app?error=invalid_name");
  }
  const accessToken = await requiredAccessToken();
  try {
    const organization = await createOrganization(accessToken, name);
    await rememberOrganization(organization.id);
    redirect(`/app/${organization.id}`);
  } catch (error) {
    if (error instanceof ProductApiError) {
      redirect("/app?error=create_failed");
    }
    throw error;
  }
}

export async function switchOrganizationAction(formData: FormData): Promise<never> {
  const organizationId = validOrganizationId(selectedOrganizationId(formData) ?? undefined);
  if (organizationId === null) {
    redirect("/app");
  }
  const accessToken = await requiredAccessToken();
  try {
    await getOrganization(accessToken, organizationId);
  } catch (error) {
    if (error instanceof ProductApiError) {
      redirect("/app");
    }
    throw error;
  }
  await rememberOrganization(organizationId);
  redirect(`/app/${organizationId}`);
}

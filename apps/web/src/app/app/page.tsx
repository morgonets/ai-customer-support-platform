import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { listOrganizations } from "@/lib/api/organizations";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";
import { ACTIVE_ORGANIZATION_COOKIE, validOrganizationId } from "@/lib/organizations/active";
import { organizationErrorMessage } from "@/lib/organizations/messages";

import { CreateOrganizationForm } from "./create-organization-form";

interface ApplicationHomeProps {
  searchParams: Promise<{ error?: string }>;
}

export default async function ApplicationHome({ searchParams }: ApplicationHomeProps) {
  const accessToken = await getVerifiedAccessToken();
  if (accessToken === null) {
    redirect("/login");
  }
  const organizations = await listOrganizations(accessToken);
  if (organizations.length > 0) {
    const cookieStore = await cookies();
    const preferredId = validOrganizationId(cookieStore.get(ACTIVE_ORGANIZATION_COOKIE)?.value);
    const active = organizations.find((organization) => organization.id === preferredId);
    redirect(`/app/${active?.id ?? organizations[0]?.id}`);
  }
  const { error } = await searchParams;
  return (
    <main className="application-main">
      <CreateOrganizationForm error={organizationErrorMessage(error)} />
    </main>
  );
}

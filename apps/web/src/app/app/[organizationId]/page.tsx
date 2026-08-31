import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ProductApiError } from "@/lib/api/client";
import {
  getOrganization,
  listMemberships,
  listOrganizations,
  type Membership,
  type Organization,
} from "@/lib/api/organizations";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";
import { validOrganizationId } from "@/lib/organizations/active";

import { CreateOrganizationForm } from "../create-organization-form";
import { OrganizationSwitcher } from "../organization-switcher";

interface OrganizationPageProps {
  params: Promise<{ organizationId: string }>;
}

export default async function OrganizationPage({ params }: OrganizationPageProps) {
  const { organizationId: rawOrganizationId } = await params;
  const organizationId = validOrganizationId(rawOrganizationId);
  if (organizationId === null) {
    notFound();
  }
  const accessToken = await getVerifiedAccessToken();
  if (accessToken === null) {
    redirect("/login");
  }

  let workspace: [Organization, Organization[], Membership[]];
  try {
    workspace = await Promise.all([
      getOrganization(accessToken, organizationId),
      listOrganizations(accessToken),
      listMemberships(accessToken, organizationId),
    ]);
  } catch (error) {
    if (error instanceof ProductApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  const [organization, organizations, memberships] = workspace;
  return (
    <main className="application-main workspace-grid">
      <section className="workspace-heading">
        <OrganizationSwitcher
          activeOrganizationId={organization.id}
          organizations={organizations}
        />
        <p className="eyebrow">Active workspace</p>
        <h1>{organization.name}</h1>
        <p>
          Your current role is <strong>{organization.role}</strong>. Roles are resolved from live
          membership data on every request.
        </p>
      </section>

      <section className="panel knowledge-entry-panel" aria-labelledby="knowledge-entry-title">
        <p className="eyebrow">M2 workspace</p>
        <h2 id="knowledge-entry-title">Knowledge Base</h2>
        <p>
          Create versioned articles, process private documents, and inspect the normalized content
          that will support retrieval in M3.
        </p>
        <Link className="primary-link" href={`/app/${organization.id}/knowledge`}>
          Open Knowledge Base
        </Link>
      </section>

      <section className="panel membership-panel" aria-labelledby="members-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Access</p>
            <h2 id="members-title">Members</h2>
          </div>
          <span>{memberships.length}</span>
        </div>
        <ul className="membership-list">
          {memberships.map((membership) => (
            <li key={membership.id}>
              <div>
                <strong>{membership.display_name ?? membership.user_id}</strong>
                {membership.display_name === null ? null : <span>{membership.user_id}</span>}
              </div>
              <span className="role-badge">{membership.role}</span>
            </li>
          ))}
        </ul>
        <p className="field-hint">
          Email invitations and polished member administration remain outside the current scope.
        </p>
      </section>

      <CreateOrganizationForm error={null} title="Create another organization" />
    </main>
  );
}

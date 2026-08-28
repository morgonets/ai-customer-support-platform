import type { Organization } from "@/lib/api/organizations";

import { switchOrganizationAction } from "./actions";

interface OrganizationSwitcherProps {
  activeOrganizationId: string;
  organizations: Organization[];
}

export function OrganizationSwitcher({
  activeOrganizationId,
  organizations,
}: OrganizationSwitcherProps) {
  return (
    <form action={switchOrganizationAction} className="organization-switcher">
      <label htmlFor="organization-switcher">Active organization</label>
      <select id="organization-switcher" name="organization_id" defaultValue={activeOrganizationId}>
        {organizations.map((organization) => (
          <option key={organization.id} value={organization.id}>
            {organization.name} · {organization.role}
          </option>
        ))}
      </select>
      <button className="secondary-button" type="submit">
        Switch
      </button>
    </form>
  );
}

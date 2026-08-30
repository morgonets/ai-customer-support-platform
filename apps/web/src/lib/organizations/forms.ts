export function organizationName(formData: FormData): string | null {
  const value = formData.get("name");
  if (typeof value !== "string") {
    return null;
  }
  const name = value.trim();
  return name.length >= 1 && name.length <= 100 ? name : null;
}

export function selectedOrganizationId(formData: FormData): string | null {
  const value = formData.get("organization_id");
  return typeof value === "string" ? value : null;
}

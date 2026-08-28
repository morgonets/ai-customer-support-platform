import { createOrganizationAction } from "./actions";

interface CreateOrganizationFormProps {
  error: string | null;
  title?: string;
}

export function CreateOrganizationForm({
  error,
  title = "Create an organization",
}: CreateOrganizationFormProps) {
  return (
    <section className="panel compact-panel" aria-labelledby="create-organization-title">
      <p className="eyebrow">Workspace setup</p>
      <h2 id="create-organization-title">{title}</h2>
      <p>Organizations keep future support data and permissions isolated.</p>
      {error === null ? null : (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <form action={createOrganizationAction} className="stack-form">
        <label htmlFor="organization-name">Organization name</label>
        <input
          id="organization-name"
          name="name"
          type="text"
          autoComplete="organization"
          minLength={1}
          maxLength={100}
          required
        />
        <button type="submit">Create organization</button>
      </form>
    </section>
  );
}

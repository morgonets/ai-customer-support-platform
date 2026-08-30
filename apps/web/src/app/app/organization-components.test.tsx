import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CreateOrganizationForm } from "./create-organization-form";
import { OrganizationSwitcher } from "./organization-switcher";

vi.mock("./actions", () => ({
  createOrganizationAction: vi.fn(),
  switchOrganizationAction: vi.fn(),
}));

const organization = {
  id: "20000000-0000-4000-8000-000000000001",
  name: "Example Organization",
  role: "owner",
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
} as const;

describe("organization components", () => {
  it("renders organization creation validation feedback", () => {
    render(<CreateOrganizationForm error="Enter a valid name." />);

    expect(screen.getByRole("heading", { name: "Create an organization" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid name.");
  });

  it("supports a custom title without an error", () => {
    render(<CreateOrganizationForm error={null} title="Create another organization" />);

    expect(
      screen.getByRole("heading", { name: "Create another organization" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the active organization and role", () => {
    render(
      <OrganizationSwitcher
        activeOrganizationId={organization.id}
        organizations={[organization, { ...organization, id: "other-id", role: "member" }]}
      />,
    );

    expect(screen.getByLabelText("Active organization")).toHaveValue(organization.id);
    expect(
      screen.getByRole("option", { name: "Example Organization · owner" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Example Organization · member" }),
    ).toBeInTheDocument();
  });
});

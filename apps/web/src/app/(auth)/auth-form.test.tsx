import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AuthForm } from "./auth-form";

describe("AuthForm", () => {
  it("renders sign-in state and safe error feedback", () => {
    render(
      <AuthForm
        action={vi.fn()}
        alternateHref="/register"
        alternateLabel="Create an account"
        error="The email or password is incorrect."
        submitLabel="Sign in"
        title="Welcome back"
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("The email or password is incorrect.");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("renders registration state without an error or recovery link", () => {
    render(
      <AuthForm
        action={vi.fn()}
        alternateHref="/login"
        alternateLabel="Sign in instead"
        error={null}
        submitLabel="Create account"
        title="Create your account"
      />,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.queryByRole("link", { name: "Forgot password?" })).not.toBeInTheDocument();
  });
});

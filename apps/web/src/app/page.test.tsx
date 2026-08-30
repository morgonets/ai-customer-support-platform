import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("presents the M1 authentication entry points", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { level: 1, name: "AI Customer Support Platform" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByText("PostgreSQL-backed organization roles")).toBeInTheDocument();
  });
});

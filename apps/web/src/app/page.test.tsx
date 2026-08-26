import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("describes the foundation milestone without claiming product features", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { level: 1, name: "AI Customer Support Platform" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Product capabilities are intentionally not implemented yet.",
    );
    expect(screen.getByText("Independent frontend and backend CI")).toBeInTheDocument();
  });
});

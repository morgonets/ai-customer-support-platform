import { describe, expect, it } from "vitest";

import { knowledgeMessage } from "./messages";

describe("knowledgeMessage", () => {
  it("returns safe known feedback and rejects unknown query values", () => {
    expect(knowledgeMessage("file_too_large")).toContain("10 MiB");
    expect(knowledgeMessage("updated")).toBe("Knowledge source updated.");
    expect(knowledgeMessage("unknown")).toBeNull();
    expect(knowledgeMessage(undefined)).toBeNull();
  });
});

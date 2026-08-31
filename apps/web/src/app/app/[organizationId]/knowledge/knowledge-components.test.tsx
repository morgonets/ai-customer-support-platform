import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { KnowledgeContent, KnowledgeSource } from "@/lib/api/knowledge";

import {
  canManageKnowledge,
  formatFileSize,
  KnowledgeCreationTools,
  KnowledgeSourceList,
  KnowledgeSourceManagement,
} from "./knowledge-components";

vi.mock("./actions", () => ({
  createKnowledgeArticleAction: vi.fn(),
  deleteKnowledgeSourceAction: vi.fn(),
  replaceKnowledgeArticleAction: vi.fn(),
  retryKnowledgeDocumentAction: vi.fn(),
  updateKnowledgeMetadataAction: vi.fn(),
  uploadKnowledgeDocumentAction: vi.fn(),
}));

const organizationId = "20000000-0000-4000-8000-000000000001";
const source: KnowledgeSource = {
  id: "40000000-0000-4000-8000-000000000001",
  organization_id: organizationId,
  kind: "article",
  title: "Support guide",
  description: null,
  created_by_user_id: null,
  updated_by_user_id: null,
  created_at: "2026-08-31T12:00:00Z",
  updated_at: "2026-08-31T12:00:00Z",
  current_version: {
    id: "50000000-0000-4000-8000-000000000001",
    version_number: 1,
    status: "ready",
    original_filename: null,
    media_type: null,
    size_bytes: null,
    processing_attempts: 0,
    processing_started_at: null,
    processed_at: "2026-08-31T12:00:00Z",
    failure_code: null,
    failure_message: null,
    created_at: "2026-08-31T12:00:00Z",
    updated_at: "2026-08-31T12:00:00Z",
  },
};
const content: KnowledgeContent = {
  source_id: source.id,
  version_id: source.current_version.id,
  version_number: 1,
  kind: "article",
  raw_text: "Raw article",
  normalized_text: "Raw article",
  locator_map: { schema_version: 1 },
};

describe("knowledge components", () => {
  it("applies role and file-size presentation rules", () => {
    expect(canManageKnowledge("owner")).toBe(true);
    expect(canManageKnowledge("admin")).toBe(true);
    expect(canManageKnowledge("member")).toBe(false);
    expect(formatFileSize(null)).toBeNull();
    expect(formatFileSize(12)).toBe("12 B");
    expect(formatFileSize(2048)).toBe("2.0 KiB");
    expect(formatFileSize(1024 * 1024)).toBe("1.0 MiB");
  });

  it("renders accessible article and document creation forms", () => {
    render(<KnowledgeCreationTools organizationId={organizationId} />);

    expect(screen.getByRole("heading", { name: "New article" })).toBeInTheDocument();
    expect(screen.getByLabelText("Knowledge content")).toBeRequired();
    expect(screen.getByRole("heading", { name: "Add document" })).toBeInTheDocument();
    expect(screen.getByLabelText("Document")).toHaveAttribute(
      "accept",
      ".txt,.md,.pdf,text/plain,text/markdown,application/pdf",
    );
  });

  it("renders an empty state and linked source summaries", () => {
    const { rerender } = render(
      <KnowledgeSourceList organizationId={organizationId} sources={[]} />,
    );
    expect(screen.getByRole("heading", { name: "No knowledge sources yet" })).toBeInTheDocument();

    const document: KnowledgeSource = {
      ...source,
      id: "40000000-0000-4000-8000-000000000002",
      kind: "document",
      description: "Uploaded guide",
      current_version: {
        ...source.current_version,
        original_filename: "guide.txt",
        media_type: "text/plain",
        size_bytes: 2048,
      },
    };
    rerender(<KnowledgeSourceList organizationId={organizationId} sources={[source, document]} />);

    expect(screen.getAllByRole("link", { name: /Support guide/ })[0]).toHaveAttribute(
      "href",
      `/app/${organizationId}/knowledge/${source.id}`,
    );
    expect(screen.getByText("No description")).toBeInTheDocument();
    expect(screen.getByText("2.0 KiB")).toBeInTheDocument();
    expect(screen.getAllByText("ready")).toHaveLength(2);
  });

  it("renders article version and destructive management controls", () => {
    const { unmount } = render(
      <KnowledgeSourceManagement
        content={content}
        organizationId={organizationId}
        source={source}
      />,
    );

    expect(screen.getByLabelText("Title")).toHaveValue("Support guide");
    expect(screen.getByLabelText("Article content")).toHaveValue("Raw article");
    expect(screen.queryByRole("button", { name: "Retry document" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete knowledge source" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeRequired();

    unmount();
    render(
      <KnowledgeSourceManagement
        content={{ ...content, raw_text: null, normalized_text: "Normalized article" }}
        organizationId={organizationId}
        source={source}
      />,
    );
    expect(screen.getByLabelText("Article content")).toHaveValue("Normalized article");
  });

  it("renders document retry without article editing", () => {
    const failedDocument: KnowledgeSource = {
      ...source,
      kind: "document",
      current_version: { ...source.current_version, status: "failed" },
    };
    render(
      <KnowledgeSourceManagement
        content={null}
        organizationId={organizationId}
        source={failedDocument}
      />,
    );

    expect(screen.getByRole("button", { name: "Retry document" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Article content")).not.toBeInTheDocument();
  });
});

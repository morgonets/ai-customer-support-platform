import { beforeEach, describe, expect, it, vi } from "vitest";

import { productApiRequest } from "./client";
import {
  createKnowledgeArticle,
  deleteKnowledgeSource,
  getKnowledgeContent,
  getKnowledgeSource,
  listKnowledgeSources,
  parseKnowledgeContent,
  parseKnowledgePage,
  parseKnowledgeSource,
  parseKnowledgeVersion,
  replaceKnowledgeArticle,
  retryKnowledgeDocument,
  updateKnowledgeMetadata,
  uploadKnowledgeDocument,
} from "./knowledge";

vi.mock("./client", () => ({ productApiRequest: vi.fn() }));

const version = {
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
};

const source = {
  id: "40000000-0000-4000-8000-000000000001",
  organization_id: "20000000-0000-4000-8000-000000000001",
  kind: "article",
  title: "Support guide",
  description: null,
  created_by_user_id: null,
  updated_by_user_id: "10000000-0000-4000-8000-000000000001",
  created_at: "2026-08-31T12:00:00Z",
  updated_at: "2026-08-31T12:00:00Z",
  current_version: version,
};

const content = {
  source_id: source.id,
  version_id: version.id,
  version_number: 1,
  kind: "article",
  raw_text: "Raw knowledge",
  normalized_text: "Raw knowledge",
  locator_map: { schema_version: 1 },
};

beforeEach(() => {
  vi.mocked(productApiRequest).mockReset();
});

describe("knowledge product API", () => {
  it("requests collection filters and source lifecycle operations", async () => {
    vi.mocked(productApiRequest)
      .mockResolvedValueOnce({ items: [source], next_cursor: "next" })
      .mockResolvedValueOnce({ items: [], next_cursor: null })
      .mockResolvedValueOnce(source)
      .mockResolvedValueOnce(source)
      .mockResolvedValueOnce(content)
      .mockResolvedValueOnce(source)
      .mockResolvedValueOnce(source)
      .mockResolvedValueOnce(source)
      .mockResolvedValueOnce(null);

    await expect(
      listKnowledgeSources("token", source.organization_id, {
        cursor: "cursor value",
        kind: "article",
        processingStatus: "ready",
      }),
    ).resolves.toMatchObject({ next_cursor: "next" });
    await expect(listKnowledgeSources("token", source.organization_id)).resolves.toEqual({
      items: [],
      next_cursor: null,
    });
    await createKnowledgeArticle("token", source.organization_id, {
      title: "Support guide",
      description: null,
      text: "Raw knowledge",
    });
    await getKnowledgeSource("token", source.organization_id, source.id);
    await getKnowledgeContent("token", source.organization_id, source.id);
    await updateKnowledgeMetadata("token", source.organization_id, source.id, {
      title: "Updated",
      description: "Description",
    });
    await replaceKnowledgeArticle("token", source.organization_id, source.id, "Replacement");
    await retryKnowledgeDocument("token", source.organization_id, source.id);
    await deleteKnowledgeSource("token", source.organization_id, source.id);

    expect(productApiRequest).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("cursor=cursor+value&kind=article&processing_status=ready"),
      "token",
    );
    expect(productApiRequest).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("/articles"),
      "token",
      expect.objectContaining({ method: "POST" }),
    );
    expect(productApiRequest).toHaveBeenLastCalledWith(
      expect.stringContaining(source.id),
      "token",
      { method: "DELETE" },
    );
  });

  it("builds multipart document uploads with optional metadata", async () => {
    vi.mocked(productApiRequest).mockResolvedValue(source);
    const file = new File(["content"], "guide.md", { type: "text/markdown" });

    await uploadKnowledgeDocument("token", source.organization_id, {
      file,
      title: "Guide",
      description: "Description",
    });
    await uploadKnowledgeDocument("token", source.organization_id, {
      file,
      title: null,
      description: null,
    });

    const firstInit = vi.mocked(productApiRequest).mock.calls[0]?.[2] as RequestInit;
    const secondInit = vi.mocked(productApiRequest).mock.calls[1]?.[2] as RequestInit;
    expect(firstInit.body).toBeInstanceOf(FormData);
    expect((firstInit.body as FormData).get("title")).toBe("Guide");
    expect((firstInit.body as FormData).get("description")).toBe("Description");
    expect((secondInit.body as FormData).has("title")).toBe(false);
    expect((secondInit.body as FormData).has("description")).toBe(false);
  });
});

describe("knowledge response parsing", () => {
  it("parses all source kinds, states, nullable fields, and content", () => {
    expect(parseKnowledgeSource(source).kind).toBe("article");
    expect(
      parseKnowledgeSource({
        ...source,
        kind: "document",
        current_version: {
          ...version,
          status: "processing",
          original_filename: "guide.txt",
          media_type: "text/plain",
          size_bytes: 12,
          processing_attempts: 1,
          processing_started_at: "2026-08-31T12:00:00Z",
        },
      }).current_version,
    ).toMatchObject({ status: "processing", size_bytes: 12 });
    expect(parseKnowledgeVersion({ ...version, status: "failed" }).status).toBe("failed");
    expect(parseKnowledgePage({ items: [source], next_cursor: null }).items).toHaveLength(1);
    expect(parseKnowledgeContent(content).locator_map).toEqual({ schema_version: 1 });
  });

  it.each([
    [() => parseKnowledgeSource(null), "invalid knowledge source"],
    [() => parseKnowledgeSource({ ...source, id: 7 }), "invalid id"],
    [() => parseKnowledgeSource({ ...source, description: 7 }), "invalid description"],
    [() => parseKnowledgeSource({ ...source, kind: "web" }), "invalid knowledge source kind"],
    [() => parseKnowledgeVersion({ ...version, status: "queued" }), "processing status"],
    [() => parseKnowledgeVersion({ ...version, version_number: "1" }), "version_number"],
    [() => parseKnowledgeVersion({ ...version, version_number: 1.5 }), "version_number"],
    [() => parseKnowledgePage({ items: null, next_cursor: null }), "source items"],
    [() => parseKnowledgeContent({ ...content, locator_map: [] }), "locator map"],
  ])("rejects malformed payloads", (parse, message) => {
    expect(parse).toThrow(message);
  });
});

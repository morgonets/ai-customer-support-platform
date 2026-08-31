import { describe, expect, it } from "vitest";

import {
  knowledgeArticleInput,
  knowledgeDocumentInput,
  knowledgeMetadataInput,
  knowledgeReplacementText,
  validKnowledgeId,
} from "./forms";

const UUID = "20000000-0000-4000-8000-000000000001";

function articleData(): FormData {
  const data = new FormData();
  data.set("title", " Support guide ");
  data.set("description", " ");
  data.set("text", "  Knowledge content\n");
  return data;
}

function documentData(file = new File(["content"], "guide.txt", { type: "text/plain" })) {
  const data = new FormData();
  data.set("title", " ");
  data.set("description", " Document description ");
  data.set("file", file);
  return data;
}

describe("knowledge form parsing", () => {
  it("validates and normalizes identifiers", () => {
    expect(validKnowledgeId(UUID.toUpperCase())).toBe(UUID);
    expect(validKnowledgeId(undefined)).toBeNull();
    expect(validKnowledgeId("not-a-uuid")).toBeNull();
  });

  it("parses articles while preserving authored content", () => {
    expect(knowledgeArticleInput(articleData())).toEqual({
      title: "Support guide",
      description: null,
      text: "  Knowledge content\n",
    });
    expect(knowledgeReplacementText(articleData())).toBe("  Knowledge content\n");
  });

  it("rejects malformed article and metadata values", () => {
    const missing = new FormData();
    const whitespace = articleData();
    whitespace.set("text", " \n ");
    const longDescription = articleData();
    longDescription.set("description", "d".repeat(2001));
    const longText = articleData();
    longText.set("text", "x".repeat(500001));
    const blobTitle = articleData();
    blobTitle.set("title", new Blob(["title"]));

    expect(knowledgeArticleInput(missing)).toBeNull();
    expect(knowledgeArticleInput(whitespace)).toBeNull();
    expect(knowledgeArticleInput(longDescription)).toBeNull();
    expect(knowledgeArticleInput(longText)).toBeNull();
    expect(knowledgeArticleInput(blobTitle)).toBeNull();
    expect(knowledgeReplacementText(missing)).toBeNull();

    const metadata = new FormData();
    metadata.set("title", " Guide ");
    metadata.set("description", " Details ");
    expect(knowledgeMetadataInput(metadata)).toEqual({
      title: "Guide",
      description: "Details",
    });
    metadata.set("title", " ");
    expect(knowledgeMetadataInput(metadata)).toBeNull();
  });

  it.each([
    new File(["markdown"], "guide.md", { type: "text/markdown" }),
    new File(["markdown"], "guide.MD", { type: "text/plain" }),
    new File(["%PDF-content"], "guide.pdf", { type: "application/pdf" }),
  ])("accepts each supported document contract", (file) => {
    expect(knowledgeDocumentInput(documentData(file))).toMatchObject({
      title: null,
      description: "Document description",
      file,
    });
  });

  it("rejects missing, empty, oversized, mismatched, and invalid metadata documents", () => {
    const missing = new FormData();
    const oversized = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "large.txt", {
      type: "text/plain",
    });
    const invalidTitle = documentData();
    invalidTitle.set("title", "x".repeat(201));
    const invalidDescription = documentData();
    invalidDescription.set("description", "x".repeat(2001));

    expect(knowledgeDocumentInput(missing)).toBeNull();
    expect(
      knowledgeDocumentInput(documentData(new File([], "empty.txt", { type: "text/plain" }))),
    ).toBeNull();
    expect(knowledgeDocumentInput(documentData(oversized))).toBeNull();
    expect(
      knowledgeDocumentInput(documentData(new File(["content"], "guide", { type: "text/plain" }))),
    ).toBeNull();
    expect(
      knowledgeDocumentInput(
        documentData(new File(["content"], "guide.docx", { type: "text/plain" })),
      ),
    ).toBeNull();
    expect(
      knowledgeDocumentInput(
        documentData(new File(["content"], "guide.pdf", { type: "text/plain" })),
      ),
    ).toBeNull();
    expect(knowledgeDocumentInput(invalidTitle)).toBeNull();
    expect(knowledgeDocumentInput(invalidDescription)).toBeNull();
  });
});

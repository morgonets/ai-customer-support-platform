import { productApiRequest } from "./client";

export type KnowledgeSourceKind = "article" | "document";
export type KnowledgeProcessingStatus = "processing" | "ready" | "failed";

export interface KnowledgeSourceVersion {
  created_at: string;
  failure_code: string | null;
  failure_message: string | null;
  id: string;
  media_type: string | null;
  original_filename: string | null;
  processed_at: string | null;
  processing_attempts: number;
  processing_started_at: string | null;
  size_bytes: number | null;
  status: KnowledgeProcessingStatus;
  updated_at: string;
  version_number: number;
}

export interface KnowledgeSource {
  created_at: string;
  created_by_user_id: string | null;
  current_version: KnowledgeSourceVersion;
  description: string | null;
  id: string;
  kind: KnowledgeSourceKind;
  organization_id: string;
  title: string;
  updated_at: string;
  updated_by_user_id: string | null;
}

export interface KnowledgeSourcePage {
  items: KnowledgeSource[];
  next_cursor: string | null;
}

export interface KnowledgeContent {
  kind: KnowledgeSourceKind;
  locator_map: Record<string, unknown>;
  normalized_text: string;
  raw_text: string | null;
  source_id: string;
  version_id: string;
  version_number: number;
}

interface KnowledgeListOptions {
  cursor?: string;
  kind?: KnowledgeSourceKind;
  processingStatus?: KnowledgeProcessingStatus;
}

interface ArticleInput {
  description: string | null;
  text: string;
  title: string;
}

interface DocumentInput {
  description: string | null;
  file: File;
  title: string | null;
}

interface MetadataInput {
  description: string | null;
  title: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown, name: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`The product API returned invalid ${name}`);
  }
  return value;
}

function stringField(value: Record<string, unknown>, name: string): string {
  if (typeof value[name] !== "string") {
    throw new Error(`The product API returned an invalid ${name}`);
  }
  return value[name];
}

function nullableStringField(value: Record<string, unknown>, name: string): string | null {
  const field = value[name];
  if (field !== null && typeof field !== "string") {
    throw new Error(`The product API returned an invalid ${name}`);
  }
  return field;
}

function integerField(value: Record<string, unknown>, name: string): number {
  const field = value[name];
  if (typeof field !== "number" || !Number.isInteger(field)) {
    throw new Error(`The product API returned an invalid ${name}`);
  }
  return field;
}

function sourceKind(value: unknown): KnowledgeSourceKind {
  if (value !== "article" && value !== "document") {
    throw new Error("The product API returned an invalid knowledge source kind");
  }
  return value;
}

function processingStatus(value: unknown): KnowledgeProcessingStatus {
  if (value !== "processing" && value !== "ready" && value !== "failed") {
    throw new Error("The product API returned an invalid knowledge processing status");
  }
  return value;
}

export function parseKnowledgeVersion(value: unknown): KnowledgeSourceVersion {
  const payload = record(value, "knowledge source version");
  return {
    id: stringField(payload, "id"),
    version_number: integerField(payload, "version_number"),
    status: processingStatus(payload.status),
    original_filename: nullableStringField(payload, "original_filename"),
    media_type: nullableStringField(payload, "media_type"),
    size_bytes: payload.size_bytes === null ? null : integerField(payload, "size_bytes"),
    processing_attempts: integerField(payload, "processing_attempts"),
    processing_started_at: nullableStringField(payload, "processing_started_at"),
    processed_at: nullableStringField(payload, "processed_at"),
    failure_code: nullableStringField(payload, "failure_code"),
    failure_message: nullableStringField(payload, "failure_message"),
    created_at: stringField(payload, "created_at"),
    updated_at: stringField(payload, "updated_at"),
  };
}

export function parseKnowledgeSource(value: unknown): KnowledgeSource {
  const payload = record(value, "knowledge source");
  return {
    id: stringField(payload, "id"),
    organization_id: stringField(payload, "organization_id"),
    kind: sourceKind(payload.kind),
    title: stringField(payload, "title"),
    description: nullableStringField(payload, "description"),
    created_by_user_id: nullableStringField(payload, "created_by_user_id"),
    updated_by_user_id: nullableStringField(payload, "updated_by_user_id"),
    created_at: stringField(payload, "created_at"),
    updated_at: stringField(payload, "updated_at"),
    current_version: parseKnowledgeVersion(payload.current_version),
  };
}

export function parseKnowledgePage(value: unknown): KnowledgeSourcePage {
  const payload = record(value, "knowledge source page");
  if (!Array.isArray(payload.items)) {
    throw new Error("The product API returned invalid knowledge source items");
  }
  return {
    items: payload.items.map(parseKnowledgeSource),
    next_cursor: nullableStringField(payload, "next_cursor"),
  };
}

export function parseKnowledgeContent(value: unknown): KnowledgeContent {
  const payload = record(value, "knowledge content");
  return {
    source_id: stringField(payload, "source_id"),
    version_id: stringField(payload, "version_id"),
    version_number: integerField(payload, "version_number"),
    kind: sourceKind(payload.kind),
    raw_text: nullableStringField(payload, "raw_text"),
    normalized_text: stringField(payload, "normalized_text"),
    locator_map: record(payload.locator_map, "knowledge locator map"),
  };
}

function collectionPath(organizationId: string): `/api/v1/${string}` {
  return `/api/v1/organizations/${organizationId}/knowledge-sources`;
}

export async function listKnowledgeSources(
  accessToken: string,
  organizationId: string,
  options: KnowledgeListOptions = {},
): Promise<KnowledgeSourcePage> {
  const query = new URLSearchParams();
  if (options.cursor !== undefined) query.set("cursor", options.cursor);
  if (options.kind !== undefined) query.set("kind", options.kind);
  if (options.processingStatus !== undefined) {
    query.set("processing_status", options.processingStatus);
  }
  const suffix = query.size === 0 ? "" : `?${query.toString()}`;
  return parseKnowledgePage(
    await productApiRequest(`${collectionPath(organizationId)}${suffix}`, accessToken),
  );
}

export async function createKnowledgeArticle(
  accessToken: string,
  organizationId: string,
  input: ArticleInput,
): Promise<KnowledgeSource> {
  return parseKnowledgeSource(
    await productApiRequest(`${collectionPath(organizationId)}/articles`, accessToken, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  );
}

export async function uploadKnowledgeDocument(
  accessToken: string,
  organizationId: string,
  input: DocumentInput,
): Promise<KnowledgeSource> {
  const body = new FormData();
  body.set("file", input.file, input.file.name);
  if (input.title !== null) body.set("title", input.title);
  if (input.description !== null) body.set("description", input.description);
  return parseKnowledgeSource(
    await productApiRequest(`${collectionPath(organizationId)}/documents`, accessToken, {
      method: "POST",
      body,
    }),
  );
}

export async function getKnowledgeSource(
  accessToken: string,
  organizationId: string,
  sourceId: string,
): Promise<KnowledgeSource> {
  return parseKnowledgeSource(
    await productApiRequest(`${collectionPath(organizationId)}/${sourceId}`, accessToken),
  );
}

export async function getKnowledgeContent(
  accessToken: string,
  organizationId: string,
  sourceId: string,
): Promise<KnowledgeContent> {
  return parseKnowledgeContent(
    await productApiRequest(`${collectionPath(organizationId)}/${sourceId}/content`, accessToken),
  );
}

export async function updateKnowledgeMetadata(
  accessToken: string,
  organizationId: string,
  sourceId: string,
  input: MetadataInput,
): Promise<KnowledgeSource> {
  return parseKnowledgeSource(
    await productApiRequest(`${collectionPath(organizationId)}/${sourceId}`, accessToken, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  );
}

export async function replaceKnowledgeArticle(
  accessToken: string,
  organizationId: string,
  sourceId: string,
  text: string,
): Promise<KnowledgeSource> {
  return parseKnowledgeSource(
    await productApiRequest(`${collectionPath(organizationId)}/${sourceId}/content`, accessToken, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  );
}

export async function retryKnowledgeDocument(
  accessToken: string,
  organizationId: string,
  sourceId: string,
): Promise<KnowledgeSource> {
  return parseKnowledgeSource(
    await productApiRequest(`${collectionPath(organizationId)}/${sourceId}/retry`, accessToken, {
      method: "POST",
    }),
  );
}

export async function deleteKnowledgeSource(
  accessToken: string,
  organizationId: string,
  sourceId: string,
): Promise<void> {
  await productApiRequest(`${collectionPath(organizationId)}/${sourceId}`, accessToken, {
    method: "DELETE",
  });
}

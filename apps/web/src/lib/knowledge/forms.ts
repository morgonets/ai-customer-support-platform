const maximumTitleCharacters = 200;
const maximumDescriptionCharacters = 2_000;
const maximumArticleCharacters = 500_000;
const maximumUploadBytes = 10 * 1024 * 1024;
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const allowedDocumentTypes: Record<string, ReadonlySet<string>> = {
  ".md": new Set(["text/markdown", "text/plain"]),
  ".pdf": new Set(["application/pdf"]),
  ".txt": new Set(["text/plain"]),
};

export interface KnowledgeArticleFormInput {
  description: string | null;
  text: string;
  title: string;
}

export interface KnowledgeDocumentFormInput {
  description: string | null;
  file: File;
  title: string | null;
}

export interface KnowledgeMetadataFormInput {
  description: string | null;
  title: string;
}

function boundedRequiredText(
  formData: FormData,
  name: string,
  maximumLength: number,
): string | null {
  const value = formData.get(name);
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized.length >= 1 && normalized.length <= maximumLength ? normalized : null;
}

function boundedOptionalText(
  formData: FormData,
  name: string,
  maximumLength: number,
): string | null | undefined {
  const value = formData.get(name);
  if (typeof value !== "string") return undefined;
  const normalized = value.trim();
  if (normalized.length === 0) return null;
  return normalized.length <= maximumLength ? normalized : undefined;
}

function boundedKnowledgeText(formData: FormData, name: string): string | null {
  const value = formData.get(name);
  if (typeof value !== "string") return null;
  return value.length >= 1 && value.length <= maximumArticleCharacters && value.trim().length > 0
    ? value
    : null;
}

export function validKnowledgeId(value: string | undefined): string | null {
  return value !== undefined && uuidPattern.test(value) ? value.toLowerCase() : null;
}

export function knowledgeArticleInput(formData: FormData): KnowledgeArticleFormInput | null {
  const title = boundedRequiredText(formData, "title", maximumTitleCharacters);
  const description = boundedOptionalText(formData, "description", maximumDescriptionCharacters);
  const text = boundedKnowledgeText(formData, "text");
  return title === null || description === undefined || text === null
    ? null
    : { title, description, text };
}

export function knowledgeDocumentInput(formData: FormData): KnowledgeDocumentFormInput | null {
  const title = boundedOptionalText(formData, "title", maximumTitleCharacters);
  const description = boundedOptionalText(formData, "description", maximumDescriptionCharacters);
  const file = formData.get("file");
  if (
    title === undefined ||
    description === undefined ||
    !(file instanceof File) ||
    file.size < 1 ||
    file.size > maximumUploadBytes
  ) {
    return null;
  }
  const extensionIndex = file.name.lastIndexOf(".");
  const extension = extensionIndex < 0 ? "" : file.name.slice(extensionIndex).toLowerCase();
  if (!allowedDocumentTypes[extension]?.has(file.type.toLowerCase())) {
    return null;
  }
  return { title, description, file };
}

export function knowledgeMetadataInput(formData: FormData): KnowledgeMetadataFormInput | null {
  const title = boundedRequiredText(formData, "title", maximumTitleCharacters);
  const description = boundedOptionalText(formData, "description", maximumDescriptionCharacters);
  return title === null || description === undefined ? null : { title, description };
}

export function knowledgeReplacementText(formData: FormData): string | null {
  return boundedKnowledgeText(formData, "text");
}

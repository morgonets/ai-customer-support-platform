"use server";

import type { Route } from "next";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ProductApiError } from "@/lib/api/client";
import {
  createKnowledgeArticle,
  deleteKnowledgeSource,
  replaceKnowledgeArticle,
  retryKnowledgeDocument,
  updateKnowledgeMetadata,
  uploadKnowledgeDocument,
} from "@/lib/api/knowledge";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";
import {
  knowledgeArticleInput,
  knowledgeDocumentInput,
  knowledgeMetadataInput,
  knowledgeReplacementText,
  validKnowledgeId,
} from "@/lib/knowledge/forms";

const surfacedApiCodes = new Set([
  "file_too_large",
  "invalid_document",
  "processing_in_progress",
  "processing_not_retryable",
  "storage_unavailable",
  "unsupported_media_type",
]);

async function requiredAccessToken(): Promise<string> {
  const accessToken = await getVerifiedAccessToken();
  if (accessToken === null) redirect("/login");
  return accessToken;
}

function validContext(organizationId: string, sourceId?: string): [string, string | null] | null {
  const validOrganization = validKnowledgeId(organizationId);
  const validSource = sourceId === undefined ? null : validKnowledgeId(sourceId);
  if (validOrganization === null || (sourceId !== undefined && validSource === null)) return null;
  return [validOrganization, validSource];
}

function collectionPath(organizationId: string): Route {
  return `/app/${organizationId}/knowledge` as Route;
}

function sourcePath(organizationId: string, sourceId: string): Route {
  return `${collectionPath(organizationId)}/${sourceId}` as Route;
}

function withMessage(path: Route, kind: "error" | "notice", code: string): Route {
  const query = new URLSearchParams({ [kind]: code });
  return `${path}?${query.toString()}` as Route;
}

function apiErrorCode(error: unknown, fallback: string): string {
  return error instanceof ProductApiError && surfacedApiCodes.has(error.code)
    ? error.code
    : fallback;
}

export async function createKnowledgeArticleAction(
  organizationId: string,
  formData: FormData,
): Promise<never> {
  const context = validContext(organizationId);
  if (context === null) redirect("/app");
  const input = knowledgeArticleInput(formData);
  if (input === null) {
    redirect(withMessage(collectionPath(context[0]), "error", "invalid_article"));
  }
  const accessToken = await requiredAccessToken();
  try {
    const source = await createKnowledgeArticle(accessToken, context[0], input);
    revalidatePath(collectionPath(context[0]));
    redirect(sourcePath(context[0], source.id));
  } catch (error) {
    if (!(error instanceof ProductApiError)) throw error;
    redirect(
      withMessage(collectionPath(context[0]), "error", apiErrorCode(error, "create_failed")),
    );
  }
}

export async function uploadKnowledgeDocumentAction(
  organizationId: string,
  formData: FormData,
): Promise<never> {
  const context = validContext(organizationId);
  if (context === null) redirect("/app");
  const input = knowledgeDocumentInput(formData);
  if (input === null) {
    redirect(withMessage(collectionPath(context[0]), "error", "invalid_document"));
  }
  const accessToken = await requiredAccessToken();
  try {
    const source = await uploadKnowledgeDocument(accessToken, context[0], input);
    revalidatePath(collectionPath(context[0]));
    redirect(sourcePath(context[0], source.id));
  } catch (error) {
    if (!(error instanceof ProductApiError)) throw error;
    redirect(
      withMessage(collectionPath(context[0]), "error", apiErrorCode(error, "create_failed")),
    );
  }
}

export async function updateKnowledgeMetadataAction(
  organizationId: string,
  sourceId: string,
  formData: FormData,
): Promise<never> {
  const context = validContext(organizationId, sourceId);
  if (context === null || context[1] === null) redirect("/app");
  const input = knowledgeMetadataInput(formData);
  if (input === null) {
    redirect(withMessage(sourcePath(context[0], context[1]), "error", "invalid_metadata"));
  }
  const accessToken = await requiredAccessToken();
  try {
    await updateKnowledgeMetadata(accessToken, context[0], context[1], input);
    revalidatePath(sourcePath(context[0], context[1]));
    revalidatePath(collectionPath(context[0]));
    redirect(withMessage(sourcePath(context[0], context[1]), "notice", "updated"));
  } catch (error) {
    if (!(error instanceof ProductApiError)) throw error;
    redirect(withMessage(sourcePath(context[0], context[1]), "error", "update_failed"));
  }
}

export async function replaceKnowledgeArticleAction(
  organizationId: string,
  sourceId: string,
  formData: FormData,
): Promise<never> {
  const context = validContext(organizationId, sourceId);
  if (context === null || context[1] === null) redirect("/app");
  const text = knowledgeReplacementText(formData);
  if (text === null) {
    redirect(withMessage(sourcePath(context[0], context[1]), "error", "invalid_replacement"));
  }
  const accessToken = await requiredAccessToken();
  try {
    await replaceKnowledgeArticle(accessToken, context[0], context[1], text);
    revalidatePath(sourcePath(context[0], context[1]));
    redirect(withMessage(sourcePath(context[0], context[1]), "notice", "updated"));
  } catch (error) {
    if (!(error instanceof ProductApiError)) throw error;
    redirect(withMessage(sourcePath(context[0], context[1]), "error", "update_failed"));
  }
}

export async function retryKnowledgeDocumentAction(
  organizationId: string,
  sourceId: string,
  formData: FormData,
): Promise<never> {
  void formData;
  const context = validContext(organizationId, sourceId);
  if (context === null || context[1] === null) redirect("/app");
  const accessToken = await requiredAccessToken();
  try {
    await retryKnowledgeDocument(accessToken, context[0], context[1]);
    revalidatePath(sourcePath(context[0], context[1]));
    revalidatePath(collectionPath(context[0]));
    redirect(withMessage(sourcePath(context[0], context[1]), "notice", "updated"));
  } catch (error) {
    if (!(error instanceof ProductApiError)) throw error;
    redirect(
      withMessage(sourcePath(context[0], context[1]), "error", apiErrorCode(error, "retry_failed")),
    );
  }
}

export async function deleteKnowledgeSourceAction(
  organizationId: string,
  sourceId: string,
  formData: FormData,
): Promise<never> {
  const context = validContext(organizationId, sourceId);
  if (context === null || context[1] === null) redirect("/app");
  if (formData.get("confirm") !== "delete") {
    redirect(withMessage(sourcePath(context[0], context[1]), "error", "delete_failed"));
  }
  const accessToken = await requiredAccessToken();
  try {
    await deleteKnowledgeSource(accessToken, context[0], context[1]);
    revalidatePath(collectionPath(context[0]));
    redirect(withMessage(collectionPath(context[0]), "notice", "deleted"));
  } catch (error) {
    if (!(error instanceof ProductApiError)) throw error;
    redirect(
      withMessage(
        sourcePath(context[0], context[1]),
        "error",
        apiErrorCode(error, "delete_failed"),
      ),
    );
  }
}

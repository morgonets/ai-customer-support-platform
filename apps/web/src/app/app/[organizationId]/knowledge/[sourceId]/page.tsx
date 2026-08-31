import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ProductApiError } from "@/lib/api/client";
import {
  getKnowledgeContent,
  getKnowledgeSource,
  type KnowledgeContent,
} from "@/lib/api/knowledge";
import { getOrganization } from "@/lib/api/organizations";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";
import { validKnowledgeId } from "@/lib/knowledge/forms";
import { knowledgeMessage } from "@/lib/knowledge/messages";

import {
  canManageKnowledge,
  formatFileSize,
  KnowledgeSourceManagement,
} from "../knowledge-components";

interface KnowledgeSourcePageProps {
  params: Promise<{ organizationId: string; sourceId: string }>;
  searchParams: Promise<{ error?: string; notice?: string }>;
}

export default async function KnowledgeSourcePage({
  params,
  searchParams,
}: KnowledgeSourcePageProps) {
  const [{ organizationId: rawOrganizationId, sourceId: rawSourceId }, query] = await Promise.all([
    params,
    searchParams,
  ]);
  const organizationId = validKnowledgeId(rawOrganizationId);
  const sourceId = validKnowledgeId(rawSourceId);
  if (organizationId === null || sourceId === null) notFound();
  const accessToken = await getVerifiedAccessToken();
  if (accessToken === null) redirect("/login");

  let workspace;
  try {
    workspace = await Promise.all([
      getOrganization(accessToken, organizationId),
      getKnowledgeSource(accessToken, organizationId, sourceId),
    ]);
  } catch (error) {
    if (error instanceof ProductApiError && error.status === 404) notFound();
    throw error;
  }
  const [organization, source] = workspace;
  let content: KnowledgeContent | null = null;
  if (source.current_version.status === "ready") {
    content = await getKnowledgeContent(accessToken, organizationId, sourceId);
  }
  const canManage = canManageKnowledge(organization.role);
  const fileSize = formatFileSize(source.current_version.size_bytes);
  const errorMessage = knowledgeMessage(query.error);
  const noticeMessage = knowledgeMessage(query.notice);

  return (
    <main className="application-main knowledge-detail">
      <header className="knowledge-detail-header">
        <Link className="back-link" href={`/app/${organization.id}/knowledge`}>
          ← Knowledge Base
        </Link>
        <div className="knowledge-source-heading">
          <span className="source-kind">{source.kind}</span>
          <span className={`status-badge status-${source.current_version.status}`}>
            {source.current_version.status}
          </span>
        </div>
        <h1>{source.title}</h1>
        <p>{source.description ?? "No description"}</p>
        <div className="source-meta">
          <span>Version {source.current_version.version_number}</span>
          <span>{source.current_version.processing_attempts} processing attempts</span>
          {fileSize === null ? null : <span>{fileSize}</span>}
        </div>
      </header>

      {errorMessage === null ? null : (
        <p className="form-error" role="alert">
          {errorMessage}
        </p>
      )}
      {noticeMessage === null ? null : (
        <p className="form-notice" role="status">
          {noticeMessage}
        </p>
      )}

      {source.current_version.status === "failed" ? (
        <section className="processing-failure" aria-labelledby="processing-failure-title">
          <p className="eyebrow">Processing failed</p>
          <h2 id="processing-failure-title">
            {source.current_version.failure_code ?? "Document could not be processed"}
          </h2>
          <p>{source.current_version.failure_message ?? "Retry the document or delete it."}</p>
        </section>
      ) : null}

      {source.current_version.status === "processing" ? (
        <section className="processing-state" aria-live="polite">
          <strong>Processing in progress</strong>
          <p>This persisted attempt can be retried by a manager after its lease becomes stale.</p>
        </section>
      ) : null}

      {source.kind === "document" && canManage ? (
        <div className="document-actions">
          <Link
            className="primary-link"
            href={`/app/${organization.id}/knowledge/${source.id}/file`}
          >
            Download original file
          </Link>
          <p>Original file access is restricted to owners and admins.</p>
        </div>
      ) : null}

      {content === null ? null : (
        <section className="knowledge-content" aria-labelledby="normalized-content-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Readable by every member</p>
              <h2 id="normalized-content-title">Normalized content</h2>
            </div>
            <span>v{content.version_number}</span>
          </div>
          <pre>{content.normalized_text}</pre>
        </section>
      )}

      {canManage ? (
        <KnowledgeSourceManagement
          content={content}
          organizationId={organization.id}
          source={source}
        />
      ) : null}
    </main>
  );
}

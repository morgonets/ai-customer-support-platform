import Link from "next/link";

import type { KnowledgeContent, KnowledgeSource } from "@/lib/api/knowledge";
import type { OrganizationRole } from "@/lib/api/organizations";

import {
  createKnowledgeArticleAction,
  deleteKnowledgeSourceAction,
  replaceKnowledgeArticleAction,
  retryKnowledgeDocumentAction,
  updateKnowledgeMetadataAction,
  uploadKnowledgeDocumentAction,
} from "./actions";

export function canManageKnowledge(role: OrganizationRole): boolean {
  return role === "owner" || role === "admin";
}

export function formatFileSize(value: number | null): string | null {
  if (value === null) return null;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

function formattedDate(value: string): string {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeZone: "UTC" }).format(
    new Date(value),
  );
}

export function KnowledgeCreationTools({ organizationId }: { organizationId: string }) {
  const createArticle = createKnowledgeArticleAction.bind(null, organizationId);
  const uploadDocument = uploadKnowledgeDocumentAction.bind(null, organizationId);
  return (
    <div className="knowledge-creation-grid">
      <section className="panel knowledge-form-panel" aria-labelledby="new-article-title">
        <p className="eyebrow">Write</p>
        <h2 id="new-article-title">New article</h2>
        <p>Add durable guidance that support answers can cite in a later milestone.</p>
        <form action={createArticle} className="stack-form">
          <label htmlFor="article-title">Title</label>
          <input id="article-title" name="title" maxLength={200} required />
          <label htmlFor="article-description">Description</label>
          <input id="article-description" name="description" maxLength={2000} />
          <label htmlFor="article-text">Knowledge content</label>
          <textarea id="article-text" name="text" maxLength={500000} rows={10} required />
          <button type="submit">Create article</button>
        </form>
      </section>

      <section className="panel knowledge-form-panel" aria-labelledby="upload-document-title">
        <p className="eyebrow">Upload</p>
        <h2 id="upload-document-title">Add document</h2>
        <p>Text extraction completes in this request and records a safe failure state if needed.</p>
        <form action={uploadDocument} className="stack-form" encType="multipart/form-data">
          <label htmlFor="document-file">Document</label>
          <input
            id="document-file"
            name="file"
            type="file"
            accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
            required
          />
          <p className="field-hint">UTF-8 text, Markdown, or text-based PDF · 10 MiB maximum</p>
          <label htmlFor="document-title">Title (optional)</label>
          <input id="document-title" name="title" maxLength={200} />
          <label htmlFor="document-description">Description</label>
          <input id="document-description" name="description" maxLength={2000} />
          <button type="submit">Upload document</button>
        </form>
      </section>
    </div>
  );
}

export function KnowledgeSourceList({
  organizationId,
  sources,
}: {
  organizationId: string;
  sources: KnowledgeSource[];
}) {
  if (sources.length === 0) {
    return (
      <div className="knowledge-empty">
        <h2>No knowledge sources yet</h2>
        <p>Owners and admins can add the first article or document above.</p>
      </div>
    );
  }
  return (
    <ul className="knowledge-source-list">
      {sources.map((source) => {
        const fileSize = formatFileSize(source.current_version.size_bytes);
        return (
          <li key={source.id}>
            <Link href={`/app/${organizationId}/knowledge/${source.id}`}>
              <div className="knowledge-source-heading">
                <span className="source-kind">{source.kind}</span>
                <span className={`status-badge status-${source.current_version.status}`}>
                  {source.current_version.status}
                </span>
              </div>
              <h3>{source.title}</h3>
              <p>{source.description ?? "No description"}</p>
              <div className="source-meta">
                <span>Version {source.current_version.version_number}</span>
                {fileSize === null ? null : <span>{fileSize}</span>}
                <time dateTime={source.updated_at}>{formattedDate(source.updated_at)}</time>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function KnowledgeSourceManagement({
  content,
  organizationId,
  source,
}: {
  content: KnowledgeContent | null;
  organizationId: string;
  source: KnowledgeSource;
}) {
  const updateMetadata = updateKnowledgeMetadataAction.bind(null, organizationId, source.id);
  const replaceArticle = replaceKnowledgeArticleAction.bind(null, organizationId, source.id);
  const retryDocument = retryKnowledgeDocumentAction.bind(null, organizationId, source.id);
  const deleteSource = deleteKnowledgeSourceAction.bind(null, organizationId, source.id);
  return (
    <div className="knowledge-management-grid">
      <section className="panel knowledge-form-panel" aria-labelledby="metadata-title">
        <p className="eyebrow">Manage</p>
        <h2 id="metadata-title">Metadata</h2>
        <form action={updateMetadata} className="stack-form">
          <label htmlFor="source-title">Title</label>
          <input
            id="source-title"
            name="title"
            defaultValue={source.title}
            maxLength={200}
            required
          />
          <label htmlFor="source-description">Description</label>
          <input
            id="source-description"
            name="description"
            defaultValue={source.description ?? ""}
            maxLength={2000}
          />
          <button type="submit">Save metadata</button>
        </form>
      </section>

      {source.kind === "article" && content !== null ? (
        <section className="panel knowledge-form-panel" aria-labelledby="replace-title">
          <p className="eyebrow">Version</p>
          <h2 id="replace-title">Replace article</h2>
          <p>Saving creates a new immutable current version.</p>
          <form action={replaceArticle} className="stack-form">
            <label htmlFor="replacement-text">Article content</label>
            <textarea
              id="replacement-text"
              name="text"
              defaultValue={content.raw_text ?? content.normalized_text}
              maxLength={500000}
              rows={12}
              required
            />
            <button type="submit">Create new version</button>
          </form>
        </section>
      ) : null}

      {source.kind === "document" && source.current_version.status !== "ready" ? (
        <section className="panel knowledge-form-panel" aria-labelledby="retry-title">
          <p className="eyebrow">Recovery</p>
          <h2 id="retry-title">Retry processing</h2>
          <p>Retry a failed extraction or reclaim a stale processing attempt.</p>
          <form action={retryDocument}>
            <button type="submit">Retry document</button>
          </form>
        </section>
      ) : null}

      <section className="panel danger-panel" aria-labelledby="delete-source-title">
        <p className="eyebrow">Permanent action</p>
        <h2 id="delete-source-title">Delete source</h2>
        <p>Deletes every version, normalized content, and any stored original file.</p>
        <form action={deleteSource} className="stack-form">
          <label className="confirmation-field">
            <input name="confirm" type="checkbox" value="delete" required />I understand this
            knowledge source will be permanently deleted.
          </label>
          <button className="danger-button" type="submit">
            Delete knowledge source
          </button>
        </form>
      </section>
    </div>
  );
}

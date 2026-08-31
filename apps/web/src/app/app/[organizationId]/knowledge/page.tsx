import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ProductApiError } from "@/lib/api/client";
import {
  listKnowledgeSources,
  type KnowledgeProcessingStatus,
  type KnowledgeSourceKind,
} from "@/lib/api/knowledge";
import { getOrganization } from "@/lib/api/organizations";
import { getVerifiedAccessToken } from "@/lib/auth/access-token";
import { validKnowledgeId } from "@/lib/knowledge/forms";
import { knowledgeMessage } from "@/lib/knowledge/messages";

import {
  canManageKnowledge,
  KnowledgeCreationTools,
  KnowledgeSourceList,
} from "./knowledge-components";

interface KnowledgePageProps {
  params: Promise<{ organizationId: string }>;
  searchParams: Promise<{
    cursor?: string;
    error?: string;
    kind?: string;
    notice?: string;
    status?: string;
  }>;
}

function selectedKind(value: string | undefined): KnowledgeSourceKind | undefined {
  return value === "article" || value === "document" ? value : undefined;
}

function selectedStatus(value: string | undefined): KnowledgeProcessingStatus | undefined {
  return value === "processing" || value === "ready" || value === "failed" ? value : undefined;
}

export default async function KnowledgePage({ params, searchParams }: KnowledgePageProps) {
  const [{ organizationId: rawOrganizationId }, query] = await Promise.all([params, searchParams]);
  const organizationId = validKnowledgeId(rawOrganizationId);
  if (organizationId === null) notFound();
  const accessToken = await getVerifiedAccessToken();
  if (accessToken === null) redirect("/login");
  const kind = selectedKind(query.kind);
  const processingStatus = selectedStatus(query.status);

  let workspace;
  try {
    workspace = await Promise.all([
      getOrganization(accessToken, organizationId),
      listKnowledgeSources(accessToken, organizationId, {
        ...(query.cursor === undefined ? {} : { cursor: query.cursor }),
        ...(kind === undefined ? {} : { kind }),
        ...(processingStatus === undefined ? {} : { processingStatus }),
      }),
    ]);
  } catch (error) {
    if (error instanceof ProductApiError && error.status === 404) notFound();
    throw error;
  }
  const [organization, sources] = workspace;
  const errorMessage = knowledgeMessage(query.error);
  const noticeMessage = knowledgeMessage(query.notice);
  const nextQuery = new URLSearchParams();
  if (sources.next_cursor !== null) nextQuery.set("cursor", sources.next_cursor);
  if (kind !== undefined) nextQuery.set("kind", kind);
  if (processingStatus !== undefined) nextQuery.set("status", processingStatus);

  return (
    <main className="application-main knowledge-workspace">
      <header className="knowledge-hero">
        <Link className="back-link" href={`/app/${organization.id}`}>
          ← {organization.name}
        </Link>
        <p className="eyebrow">Organization knowledge</p>
        <h1>Knowledge Base</h1>
        <p>
          Manage normalized, versioned support knowledge now; chunking and retrieval remain an M3
          concern.
        </p>
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

      {canManageKnowledge(organization.role) ? (
        <KnowledgeCreationTools organizationId={organization.id} />
      ) : (
        <section className="panel readonly-panel">
          <p className="eyebrow">Read-only access</p>
          <h2>Organization knowledge</h2>
          <p>
            Members can read source metadata and normalized content. An owner or admin manages
            sources and original document files.
          </p>
        </section>
      )}

      <section className="knowledge-library" aria-labelledby="knowledge-library-title">
        <div className="section-heading knowledge-library-heading">
          <div>
            <p className="eyebrow">Library</p>
            <h2 id="knowledge-library-title">Sources</h2>
          </div>
          <span>{sources.items.length}</span>
        </div>
        <form className="knowledge-filters" method="get">
          <label htmlFor="kind-filter">Type</label>
          <select id="kind-filter" name="kind" defaultValue={kind ?? ""}>
            <option value="">All types</option>
            <option value="article">Articles</option>
            <option value="document">Documents</option>
          </select>
          <label htmlFor="status-filter">Status</label>
          <select id="status-filter" name="status" defaultValue={processingStatus ?? ""}>
            <option value="">All states</option>
            <option value="ready">Ready</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
          </select>
          <button className="secondary-button" type="submit">
            Apply filters
          </button>
          <Link className="secondary-link" href={`/app/${organization.id}/knowledge`}>
            Clear
          </Link>
        </form>
        <KnowledgeSourceList organizationId={organization.id} sources={sources.items} />
        {sources.next_cursor === null ? null : (
          <Link
            className="secondary-link pagination-link"
            href={`/app/${organization.id}/knowledge?${nextQuery.toString()}`}
          >
            Next page
          </Link>
        )}
      </section>
    </main>
  );
}

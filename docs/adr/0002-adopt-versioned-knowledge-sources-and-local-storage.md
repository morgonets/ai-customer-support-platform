# ADR 0002: Adopt versioned knowledge sources and local storage

- **Status:** Accepted
- **Date:** 2026-08-31
- **Milestone:** M2 — Knowledge-base lifecycle

## Context

M2 introduces organization-scoped articles and uploaded documents that a later grounded-answer
pipeline can chunk, embed, retrieve, and cite. The design must preserve FastAPI as the exclusive
product-data and file-access API, enforce tenant isolation in both application code and PostgreSQL
row-level security, and avoid requiring production infrastructure before a hosting target exists.

The source model must retain normalized text and stable content identities without prematurely
implementing M3 retrieval concerns. Upload processing must also survive an interrupted request
without introducing a queue, broker, or separately deployed worker.

## Decision

Use one `knowledge_sources` abstraction for both manually authored articles and uploaded documents.
Store immutable content revisions in `knowledge_source_versions`; metadata changes do not create a
new version, while article content replacement does. A source has at most one current version.

Every knowledge row contains a non-null `organization_id`, every relationship is tenant-aware, and
all knowledge tables enable and force RLS. Owners and admins may create, update, retry, and delete
knowledge. All organization members may read source metadata and normalized content. Original
uploaded file access is a distinct owner/admin-only capability enforced by FastAPI and by a
restricted PostgreSQL function; ordinary table reads do not grant access to storage keys.

Uploaded files use a narrow `ObjectStorage` interface. M2 implements a persistent local-filesystem
adapter with server-generated organization/source/version keys. Supabase Storage and hosted object
storage adapters remain deferred until a production hosting and least-privilege credential model is
approved. Browser code never receives storage paths and never accesses storage directly.

M2 accepts UTF-8 text, Markdown, and text-based PDF files. It performs bounded synchronous
extraction outside the event loop, while persisting `processing`, `ready`, or `failed` state in
PostgreSQL. An interrupted or failed attempt can be retried without a queue or background worker.
Ready versions are immutable.

Chunking, embeddings, vector search, retrieval, answer generation, and citations belong to M3.
Future chunks will reference the organization, source, and immutable source-version identifiers and
use the version's normalized-text offsets and locator map.

## Consequences

### Benefits

- Articles and documents share authorization, lifecycle, API, and future retrieval contracts.
- Immutable versions give future citations and indexing runs a stable content target.
- Tenant-aware foreign keys and FORCE RLS protect against missed application filters.
- Original-file access can remain stricter than normalized-content access.
- Local development is durable without choosing or simulating a production storage provider.
- Persisted processing state makes synchronous ingestion observable and recoverable.

### Costs and constraints

- Filesystem storage is suitable only for local or explicitly single-instance durable-volume use.
- Database and object storage cannot be mutated atomically; deletion and interrupted processing use
  idempotent recovery rules.
- PDF extraction is limited to text-based files; OCR and hostile-file sandboxing remain deferred.
- A future hosted deployment must add an object-storage adapter before enabling production uploads.

## Rejected alternatives

- **Separate article and document source tables:** rejected because authorization, metadata,
  lifecycle, and future retrieval behavior are shared.
- **Mutable text on the source row:** rejected because edits would invalidate future chunks and
  citations without a stable content identity.
- **Supabase Storage in M2:** rejected because the available access patterns would duplicate tenant
  authorization or require an overly broad runtime credential.
- **Database `bytea` file storage:** rejected because it couples large immutable blobs to the
  transactional database and creates an avoidable future migration.
- **In-memory background tasks:** rejected because process exit can silently lose work.
- **A queue, broker, or worker deployment:** rejected because bounded M2 extraction does not justify
  the additional operational and cross-tenant worker identity surface.

## Follow-up constraints

- Do not expose storage keys, filesystem paths, or direct object URLs through public contracts.
- Do not let members invoke the original-file lookup function or download endpoint.
- Do not overwrite a ready version; create a new version or future indexing generation.
- Do not add a production storage adapter without least-privilege credentials and documented
  backup, deletion, and recovery behavior.
- Keep M3 chunk and embedding records tenant-scoped and version-addressed.

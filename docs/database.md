# Database Design

## Status

M0 provides a local PostgreSQL service with pgvector available. It does not create application tables or migrations. The model below is a design direction for later milestones, not an implemented schema.

## Database role

PostgreSQL is the intended transactional system of record. pgvector will keep embeddings close to tenant-scoped source metadata and enable a simple initial retrieval path. Uploaded file bytes should live in object storage; PostgreSQL stores their metadata, lifecycle state, extracted structure, and citations.

## Conventions

- PostgreSQL-supported UUID primary keys for externally visible entities
- `created_at` and `updated_at` as timezone-aware UTC timestamps
- Lowercase `snake_case` names for tables, columns, constraints, and indexes
- Explicit foreign keys and deletion behavior
- Database constraints for invariants that must survive every code path
- Money, token counts, dimensions, and status values represented with deliberate types rather than generic text
- No secrets, raw access tokens, or provider credentials in ordinary application tables

## Planned ownership model

Tenant-owned tables carry a non-null `tenant_id` (or organization identifier) and use tenant-aware unique constraints and indexes. Repository methods require tenant context explicitly. Authorization is resolved before querying; caller-supplied tenant identifiers are not trusted as proof of access.

PostgreSQL row-level security is expected to provide defense in depth if the selected Supabase/authentication pattern can supply a trustworthy database session context. RLS is not a substitute for authorization in application services, and service credentials that bypass RLS must be tightly scoped and tested.

Cross-tenant administrative operations must use separate, auditable code paths and database roles.

## Planned logical areas

### Identity and tenancy

- organizations/tenants
- users or external identity mappings
- memberships and roles
- invitations and audit events

### Knowledge

- knowledge bases or collections
- documents and immutable versions
- ingestion jobs and processing attempts
- chunks with stable source locations
- embeddings with provider/model/dimension metadata

### Support conversations

- channels and channel identities
- conversations, participants, and assignments
- messages and normalized content
- generated-answer metadata and citations
- feedback, handoff events, and internal notes

### Operations and analytics

- durable product events where necessary
- provider usage/cost attribution
- delivery attempts and idempotency keys
- retention/deletion audit records

This grouping does not require separate schemas or services. Begin with one application schema unless access or operational constraints justify more.

## Vector search direction

- Store the embedding model identifier and vector dimension alongside a versioned embedding configuration.
- Do not mix incompatible embeddings in one search path.
- Filter by tenant and eligible document state before ranking.
- Select HNSW or IVFFlat only after representative data and recall/latency measurements; exact search may be sufficient initially.
- Keep chunk text and citation metadata accessible without depending on provider responses.
- Re-embedding must be resumable and support overlapping versions without corrupting active retrieval.

The embedding provider, model, dimension, distance metric, chunking strategy, and index parameters remain open decisions for M2/M3.

## Migration policy

The migration tool will be selected with the M1 persistence layer; Alembic is the default candidate for SQLAlchemy-based access.

- Every schema change is delivered through a committed migration.
- Applied migrations are immutable.
- CI should apply all migrations to an empty database and, once releases exist, test supported upgrade paths.
- Destructive or long-running changes require rollout and recovery notes.
- Application changes that depend on a migration should support safe deployment ordering.
- Seed data must be synthetic, deterministic, and free of credentials or customer information.

## Backup, retention, and deletion

Production retention periods and recovery objectives are not selected. Before launch, document and test:

- automated database backups and point-in-time recovery
- object/database consistency during document deletion
- tenant offboarding and data export/deletion
- conversation and analytics retention
- embedding and derived-data cleanup
- a restore drill with measured recovery time and recovery point

## Decisions required before M1–M2

- Identity provider and trustworthy tenant context
- SQLAlchemy versus direct SQL/query tooling
- RLS policy and privileged-operation model
- Production PostgreSQL/Supabase ownership and region
- Object storage and data residency requirements
- Retention, deletion, backup, and recovery objectives

# Architecture

## Status

This document describes the implemented M2 authentication, tenancy, and knowledge-base
architecture plus the intended direction for later milestones. Sections marked **planned** are not
implemented yet.

## Architectural drivers

- Strong tenant isolation and auditable access
- Grounded AI answers with stable source citations
- Replaceable external providers without lowest-common-denominator domain design
- Reproducible local development and deployment
- Operational visibility into latency, quality, cost, and failure
- A small system that can evolve without premature distributed-systems overhead

## System context

```mermaid
flowchart LR
    customer[Customer] --> webchat[Web chat - planned]
    customer --> telegram[Telegram - planned]
    agent[Support agent] --> web[Next.js web app]
    web --> auth[Supabase Auth]
    webchat --> api[FastAPI modular monolith]
    telegram --> api
    web --> api
    api --> db[(Supabase PostgreSQL + pgvector)]
    auth --> db
    api --> storage[Private local object storage]
    api --> llm[LLM and embedding providers - planned]
```

M2 includes Supabase Auth sessions, authenticated application routes, FastAPI JWT verification,
organizations, memberships, role authorization, PostgreSQL RLS, versioned knowledge sources, and
private local file storage. Chat, Telegram, managed storage, and model providers remain planned.

## Repository and deployment units

The repository contains two application boundaries:

- **Web (`apps/web`)** — Next.js App Router application. It owns browser rendering, Supabase Auth
  session integration, user interaction, and calls to the public API. It accesses Supabase directly
  only for authentication and does not query product data through Supabase Data APIs.
- **API (`apps/api`)** — FastAPI modular monolith. It owns authorization, tenant-aware domain
  workflows, product persistence, and later retrieval, provider orchestration, and channel adapters.

Supabase PostgreSQL with pgvector is the system of record. Supabase Auth owns credentials and
sessions; current application roles, memberships, and knowledge metadata/content remain PostgreSQL
data. M2 original document bytes use a persistent local-filesystem adapter behind `ObjectStorage`.
A managed adapter and external AI providers will be added only when their deployment milestones
have approved credential and tenancy models.

M2 extraction is bounded and synchronous, with blocking parsing moved off the event loop and
processing state persisted before file work. A background worker may later run from the same
backend codebase when durable indexing work justifies it. That would be a process boundary for
operational work, not permission to duplicate domain logic or introduce a separate service.

## Backend module direction

Product modules are organized by capability rather than technical layer alone. M2 implements the
`tenants` and `knowledge` capabilities; later directories remain planned:

```text
app/
├── api/             # HTTP composition, dependencies, and versioned routers
├── core/            # Configuration, observability, security primitives
├── tenants/         # Organizations, memberships, tenant context (M1)
├── knowledge/       # Sources, versions, local storage, extraction (M2)
├── conversations/   # Conversations, messages, feedback, handoff (planned)
├── answering/       # Retrieval, prompting, citations, provider ports (planned)
└── integrations/    # Telegram and other external adapters (planned)
```

Each capability may contain its domain models, application services, persistence adapters, and tests. HTTP handlers should validate/translate requests and delegate behavior; provider SDKs and SQL must not become the domain interface.

## Frontend module direction

Keep route-specific UI close to App Router routes. Promote code into `src/components`, `src/features`, or `src/lib` only when reuse or an explicit boundary appears. API client modules should expose typed application-oriented operations, centralize error handling, and avoid leaking transport details through components.

Prefer server components for data loading and static rendering. Client components are appropriate for interactive chat, streaming state, and browser-only integrations.

M1 uses `@supabase/ssr` cookie-backed clients. The root Next.js proxy refreshes expiring sessions;
server actions own registration, login, logout, and password recovery; and the protected `/app`
layout establishes identity from locally verified asymmetric JWT claims. Confirmation links terminate
at `/auth/confirm`, exchange either a PKCE authorization code or an allowlisted email OTP with
Supabase Auth, and allow only an explicit recovery redirect. Passwords and refresh tokens never pass
through FastAPI.

M2 adds `/app/{organization_id}/knowledge` and source-detail routes as server-rendered workspaces.
Typed client modules call FastAPI for every metadata, content, and file operation. Server actions
perform manager mutations; the download route proxies only safe response headers from FastAPI and
never exposes a storage key or filesystem path. Members see normalized content, while original-file
controls are shown only to owners and admins; FastAPI and PostgreSQL remain the authoritative
enforcement boundaries.

## Authenticated request flow

1. Supabase Auth creates an access/refresh-token session through the Next.js SSR integration. The
   access token is short-lived and the proxy persists provider refresh rotation in secure cookies.
2. Next.js validates identity for protected rendering and forwards the access token as a bearer
   token when calling FastAPI.
3. FastAPI validates the configured JWT algorithm, JWKS signature, issuer, audience, expiry, and
   subject, then constructs an authenticated actor.
4. A path organization UUID selects a workspace but never grants access. FastAPI resolves a current
   membership and enforces the role required by the application service.
5. The database dependency begins a transaction, installs verified claims transaction-locally, and
   assumes the restricted `app_api` role before the first product query.
6. Repositories require organization context and use explicit tenant filters; RLS independently
   evaluates the same user against membership data.
7. Expected failures use the stable API error contract and do not reveal foreign-tenant existence.

Protected rendering and API authorization are separate checks. Next.js redirects unauthenticated
application rendering to `/login`; FastAPI still verifies every bearer token independently and never
trusts a Next.js-only header or session assertion.

The protected application reads organization data only through typed FastAPI client modules. The
active organization is a URL path segment; an HTTP-only preference cookie selects a default on the
next `/app` visit but never grants access. The workspace switch action verifies membership through
FastAPI before redirecting, and a direct foreign organization URL still receives FastAPI/RLS denial.

Organization roles are deliberately absent from JWT claims so a role change takes effect on the
next database authorization check rather than waiting for token refresh.

The authorization matrix is deliberately small: owners administer organization settings and all
roles; admins update organization settings and add/remove members; and every user may leave an
organization. For knowledge, all members read source metadata and normalized text, while only
owners and admins create, update, retry, delete, or download original files. The last-owner database
invariant applies regardless of the calling role. Permissions remain role-based only until a
concrete later requirement justifies a more granular model.

## Core request rules

1. The edge/API authenticates the caller or, in a later milestone, validates a public channel session.
2. A trusted tenant context is resolved from authorization data, never accepted blindly from a request body.
3. Application services receive tenant context explicitly.
4. Persistence queries require tenant scope; PostgreSQL policies add defense in depth.
5. External provider calls receive only the minimum required tenant data.
6. Responses use stable public identifiers and avoid exposing provider or storage internals.

## Provider boundaries

M2 defines a narrow `ObjectStorage` port with a local persistent adapter. Storage keys are generated
server-side from tenant/source/version identities, and the adapter validates that shape before file
access. Text generation, embeddings, managed object storage, and messaging delivery remain planned;
their provider adapters must translate SDK requests and failures without making vendor SDKs domain
interfaces.

Provider abstraction does not mean every vendor feature must be flattened. Vendor-specific capabilities may be exposed through typed capability checks or configuration where they create product value.

## Reliability and observability direction

- The API accepts a valid UUID `X-Request-ID` or generates one, returns it in every HTTP response, and
  includes it in structured request-completion and failure logs.
- The API emits JSON application logs to stderr with method, path, status, and duration, excluding query
  strings, request/response bodies, authorization headers, tokens, and unnecessary customer content.
- Propagate the request/correlation ID through jobs and provider calls when those boundaries arrive.
- Track latency, failure, token/cost, retrieval, citation, and handoff outcomes.
- Make asynchronous work idempotent and persist job state before adding retries.
- Use transactional outbox or equivalent only when a real cross-boundary delivery workflow requires it.
- Provide liveness/readiness semantics appropriate to each deployment target.

## Security boundaries

Authentication, tenant resolution, database access, uploaded files, retrieved content, prompt construction, model output, web rendering, and incoming webhooks are distinct trust boundaries. The design assumes uploaded content and model output are untrusted.

See `SECURITY.md` and `docs/database.md` for repository and data-specific controls.

## Decisions intentionally left open

These choices should be approved when their milestone has concrete requirements:

- Object storage provider and document malware-scanning approach
- Background job implementation and queue infrastructure
- Initial LLM and embedding providers and fallback policy
- Hosting platform, regions, recovery objectives, and production topology
- Licensing and commercial distribution terms

Record hard-to-reverse choices as ADRs in `docs/adr/`.

## Public and future commercial boundaries

The public portfolio keeps the reusable security and product foundation: tenant-aware schema and
RLS, authorization services, source/version lifecycle, storage and extraction ports, HTTP
contracts, frontend workspace, tests, and operational documentation. A future private commercial
core may add proprietary ranking, evaluation data, provider routing, billing policy, enterprise
integrations, or support operations. Those capabilities should consume the public versioned source
and normalized-content contracts rather than fork tenant identity, storage authorization, or the
knowledge lifecycle.

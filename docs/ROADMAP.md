# Product Roadmap

This roadmap sequences outcomes rather than promising dates. A milestone is complete only when its acceptance criteria are implemented, tested, documented, and operable. Scope may change through explicit architectural decisions and user feedback.

## M0 — Repository and development foundation

**Goal:** establish a professional, reproducible base without product functionality.

- Monorepo with Next.js and FastAPI foundations
- Strict formatting, linting, type checking, tests, and production builds
- Reproducible JavaScript and Python dependency locks
- Local PostgreSQL/pgvector service and application containers
- CI, contribution workflow, environment template, and living documentation

**Exit criteria:** all local quality gates pass; CI represents the same gates; the complete foundation is documented; no secrets or product features are included.

## M1 — Tenant-aware SaaS core

**Goal:** introduce the minimum secure application and persistence model.

- PostgreSQL migrations and repository/session infrastructure
- Organizations, users, memberships, and roles
- Authentication provider selection and integration
- Tenant context propagated through API and persistence boundaries
- Defense-in-depth tenant isolation tests
- Structured logging, request IDs, and baseline error contracts

**Exit criteria:** an authenticated user can access only an authorized workspace, with automated tests proving isolation and documented recovery/migration procedures.

## M2 — Knowledge-base lifecycle

**Goal:** let a workspace safely manage source material.

- Document upload and storage abstraction
- File validation, limits, status, and deletion lifecycle
- Text extraction and normalized document representation
- Background job mechanism chosen from measured requirements
- Chunking, embedding abstraction, and pgvector persistence
- Reprocessing, idempotency, failure visibility, and retention rules

**Exit criteria:** supported documents move through an observable, retryable ingestion pipeline and can be deleted completely within their tenant boundary.

## M3 — Grounded answer engine

**Goal:** answer questions from tenant knowledge with verifiable evidence.

- Versioned retrieval and ranking pipeline
- LLM and embedding provider interfaces
- Prompt construction with untrusted-content defenses
- Source citations mapped to stable document locations
- No-answer and low-confidence behavior
- Evaluation dataset and retrieval/answer quality harness
- Token, latency, and provider error telemetry

**Exit criteria:** evaluated questions produce traceable answers or an explicit no-answer outcome, with tenant isolation and provider failures covered by tests.

## M4 — Web support experience

**Goal:** deliver the first end-to-end customer support channel.

- Configurable, embeddable web chat
- Conversation and message persistence
- Streaming answer experience and citation UI
- Anonymous visitor/session model with abuse controls
- Agent-facing conversation view
- Feedback capture and accessible responsive UX

**Exit criteria:** a customer can complete a durable, cited support conversation through the web channel and an authorized workspace member can review it.

## M5 — Telegram channel

**Goal:** reuse the same conversation and answer core through Telegram.

- Secure bot configuration and webhook verification
- Tenant/channel mapping and Telegram identity handling
- Message normalization into the shared conversation model
- Formatting, retries, deduplication, and rate-limit behavior
- Channel-specific operational documentation

**Exit criteria:** Telegram conversations are idempotent, tenant-safe, observable, and visible alongside web conversations.

## M6 — Human handoff and support operations

**Goal:** let automation transfer ownership without losing context.

- Handoff triggers and explicit customer requests
- Queue, assignment, ownership, and conversation state model
- Agent replies and internal notes
- Notifications and service-level timestamps
- Audit history for operational actions

**Exit criteria:** a conversation can move reliably between AI and a human agent with clear ownership, context, auditability, and failure recovery.

## M7 — Analytics and quality operations

**Goal:** help businesses measure support outcomes and improve content.

- Tenant dashboards for volume, resolution, handoff, latency, and feedback
- Unanswered-question and weak-source reporting
- Cost and token attribution
- Privacy-aware event model and retention controls
- Export and evaluation workflows

**Exit criteria:** metrics are defined, tested against source events, tenant-safe, and useful for concrete content or support improvements.

## M8 — Production hardening and release

**Goal:** make the service ready for a controlled production launch.

- Deployment platform and managed service decisions
- Infrastructure-as-code where it reduces operational risk
- Backup/restore drill, disaster recovery objectives, and runbooks
- Rate limiting, quotas, abuse controls, and security review
- Load, resilience, accessibility, and browser testing
- Observability, alerts, dependency scanning, and release process
- Billing only if the product model and launch scope require it

**Exit criteria:** staging and production are reproducible; security and recovery controls are verified; service objectives and ownership are documented; a release can be rolled forward or recovered safely.

## Explicitly deferred

Native mobile clients, voice support, broad CRM integrations, multiple independently deployed microservices, custom model training, and enterprise billing are not assumed. They require validated product demand and separate decisions.

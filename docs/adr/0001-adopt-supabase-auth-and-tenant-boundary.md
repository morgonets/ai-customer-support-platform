# ADR 0001: Adopt Supabase authentication and tenant boundary

- **Status:** Accepted
- **Date:** 2026-08-26
- **Milestone:** M1 — Tenant-aware SaaS core

## Context

M1 introduces authentication, organizations, memberships, roles, persistence, and tenant
isolation. The existing system is a modular monolith with a Next.js web application, a FastAPI
backend, and PostgreSQL as the intended system of record. Authentication provider, database
access, migration tooling, and the exact RLS boundary were intentionally left open in M0.

The selected design must keep product rules in FastAPI, support server-rendered authentication,
make local development reproducible, and prevent a missed application filter from becoming a
cross-organization data leak.

## Decision

Use one Supabase project per environment for Supabase Auth and PostgreSQL. Use the Supabase CLI
stack for local Auth and PostgreSQL development.

The boundaries are:

- Next.js communicates with Supabase directly only for authentication and session operations.
- FastAPI is the exclusive product-data API. Browser code does not query Supabase Data APIs or
  PostgREST for application tables.
- FastAPI verifies Supabase access tokens using configured asymmetric signing keys and the
  project's JWKS endpoint. Organization memberships and application roles remain database state;
  they are not copied into JWT claims.
- FastAPI accesses PostgreSQL through SQLAlchemy using a dedicated, non-owner, non-bypass runtime
  role. Each authenticated transaction installs verified JWT claims transaction-locally before
  querying and assumes a restricted application role.
- Authorization is enforced in both FastAPI application services and PostgreSQL row-level
  security. Request-supplied organization identifiers select among authorized organizations but
  never grant access.
- Supabase SQL migrations are the single schema history. Alembic is not introduced alongside
  them. SQLAlchemy models are runtime mappings, not a second migration authority.
- Product tables live in a non-exposed `app` schema. Security-definer helpers live in a separate
  non-exposed `app_private` schema.
- Initial authorization is role-based with `owner`, `admin`, and `member` roles.
- The active organization is route context, with a server-controlled cookie used only as a
  last-selection preference.

Production-specific choices such as project region, SMTP provider, session timeouts, backup
objectives, and connection topology remain configurable deployment decisions. M1 does not create,
link, or modify a remote Supabase project.

## Consequences

### Benefits

- Authentication and application identities share one PostgreSQL trust domain.
- FastAPI remains the single place for product workflows and public product contracts.
- RLS limits the impact of an accidentally unscoped repository query.
- The runtime application cannot use migration ownership or Supabase service credentials.
- SQL migrations can express roles, grants, policies, triggers, and recovery notes directly.
- Local Auth, email capture, migrations, and policy tests are reproducible in Docker through the
  Supabase CLI.

### Costs and constraints

- Local development requires Docker and the pinned Supabase CLI stack rather than only one
  PostgreSQL container.
- The runtime login password must be provisioned separately from committed migrations.
- Every pooled database transaction must install claims with transaction-local settings and must
  reliably commit or roll back.
- JWT verification is subject to access-token expiry and JWKS cache behavior; signing-key rotation
  and emergency revocation require documented operations.
- The `@supabase/ssr` integration is isolated behind local wrappers because its API may evolve.

## Rejected alternatives

- **Frontend product queries through PostgREST:** rejected because it would split product behavior
  between browser database calls and FastAPI.
- **Runtime Supabase service credentials:** rejected because service credentials bypass RLS and
  would turn application checks into the only tenant boundary.
- **Roles embedded in JWT claims:** rejected because membership changes would remain stale until
  token refresh.
- **Alembic plus Supabase migrations:** rejected because two migration histories would create
  ordering and drift risks, while M1 schema changes are primarily SQL-native security objects.
- **Separate hosted Auth and local/independent PostgreSQL:** rejected because it would complicate
  trustworthy database identity propagation and local parity.
- **Microservices or a separate identity service:** rejected because the modular monolith already
  provides appropriate boundaries for M1.

## Follow-up constraints

- Do not expose `app` or `app_private` through Supabase Data APIs.
- Do not grant application-table privileges to `anon`, `authenticated`, or `service_role` unless a
  later reviewed contract explicitly requires it.
- Every future tenant-owned table must contain a non-null `organization_id`, tenant-aware indexes
  and constraints, explicit FastAPI authorization, and RLS in the same migration.
- Administrative or cross-tenant operations require separate credentials and auditable code paths.

# Deployment and Operations

## Status

M3 uses Supabase CLI for reproducible local Auth/PostgreSQL development, local persistent knowledge
storage, and a PostgreSQL-backed indexing worker from the FastAPI codebase. No remote project,
production hosting platform, region, domain, object-storage provider, or service-level objective has
been selected.

## Local modes

### Host applications with local Supabase

This is the fastest development loop:

```bash
cp .env.example .env
# Replace all placeholder values in .env.
pnpm install --frozen-lockfile
(cd apps/api && uv sync --frozen)
pnpm dev:supabase
# Copy the printed local publishable key into .env.
pnpm db:reset
pnpm db:provision
pnpm dev:web
pnpm dev:api
# In another terminal:
(cd apps/api && uv run --env-file ../../.env python -m app.rag.worker)
```

The web and API commands run in separate terminals. Supabase Studio, local email capture, Auth,
and PostgreSQL endpoints are printed after startup. PostgreSQL is available on port `54322` by
default. The local stack uses generated ES256 signing keys under the ignored `supabase/.temp`
directory.

### Complete container stack

```bash
pnpm dev:supabase
docker compose up --build
```

Compose runs the web and API containers against the host's local Supabase stack. It waits for API
health before starting the web application. `pnpm supabase:stop` stops Supabase; `pnpm db:reset`
recreates local application data from committed migrations and seed files and is destructive.

## Configuration

`.env.example` is the inventory of local configuration. Copy it to `.env` and replace placeholders. The committed template contains no usable production secret.

- `ENVIRONMENT`: `local`, `test`, `staging`, or `production`
- `LOG_LEVEL`: backend log level
- `API_PORT`: published backend port for the local Compose stack
- `API_CORS_ORIGINS`: JSON array of allowed browser origins
- `APP_URL`: canonical web origin used to build allowlisted Auth confirmation/recovery redirects
- `API_INTERNAL_URL`: server-to-server FastAPI origin; defaults to `NEXT_PUBLIC_API_URL` for host development
- `NEXT_PUBLIC_API_URL`: public browser-visible API base URL
- `NEXT_PUBLIC_SUPABASE_URL`: browser-visible Supabase project URL
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: browser-visible Supabase publishable key; not a secret
- `SUPABASE_JWT_ISSUER`, `SUPABASE_JWKS_URL`, `SUPABASE_JWT_AUDIENCE`: backend token-verification contract
- `SUPABASE_JWT_LEEWAY_SECONDS`: optional clock-skew allowance from `0` to `300` seconds; defaults to `0`
- `DATABASE_URL`: least-privilege FastAPI runtime database URL
- `KNOWLEDGE_LOCAL_STORAGE_PATH`: private local document root; defaults to `apps/api/.data/knowledge` through `pnpm dev:api`
- `KNOWLEDGE_MAX_UPLOAD_BYTES`: upload ceiling, capped by the application at 10 MiB
- `KNOWLEDGE_MAX_PDF_PAGES`: PDF page ceiling, capped by the application at 100
- `KNOWLEDGE_PROCESSING_STALE_SECONDS`: processing lease after which a manager may retry
- `API_DATABASE_PASSWORD`: local runtime-role provisioning input
- `RAG_WORKER_DATABASE_URL`, `RAG_WORKER_DATABASE_PASSWORD`: separate least-privilege indexing
  worker connection and local provisioning input
- `RAG_EMBEDDING_PROFILE_KEY`: immutable profile used when an organization is first indexed
- `RAG_GENERATION_PROVIDER`: `deterministic` locally/CI or opt-in `openai`
- `RAG_EXACT_VECTOR_SEARCH`: exact cosine search is the default; disable only after measuring the
  available HNSW path
- `RAG_MINIMUM_VECTOR_SIMILARITY`, `RAG_CANDIDATE_LIMIT`, `RAG_EVIDENCE_LIMIT`,
  `RAG_MAXIMUM_CHUNKS_PER_SOURCE`: public reference retrieval bounds, externally configurable
- `RAG_WORKER_LEASE_SECONDS`, `RAG_WORKER_MAXIMUM_ATTEMPTS`,
  `RAG_WORKER_RETRY_DELAY_SECONDS`, `RAG_WORKER_POLL_SECONDS`: durable worker controls
- `OPENAI_API_KEY`, `OPENAI_API_BASE_URL`, `OPENAI_GENERATION_MODEL`: server-only opt-in OpenAI
  adapter settings; the key must never use a `NEXT_PUBLIC_*` name
- `API_DATABASE_URL_DOCKER`, `SUPABASE_JWKS_URL_DOCKER`: container-to-host local endpoints

The local `api_login` and `rag_worker_login` passwords are deliberately absent from migrations.
`pnpm db:provision` reads both password values from the environment or ignored root `.env` and
sets only those local roles' passwords. Production roles and passwords must be provisioned by an approved
secret-management/release process; do not place them in migrations.

Production configuration must come from the hosting platform's secret/configuration service. Do not bake secrets into images, source files, build arguments, `NEXT_PUBLIC_*`, or CI logs.
Production startup rejects local/placeholder database and Auth endpoints and requires HTTPS for the
Supabase issuer and JWKS URL. It also rejects local file storage unless
`KNOWLEDGE_ALLOW_LOCAL_STORAGE_IN_PRODUCTION=true` is an explicit deployment decision and
`KNOWLEDGE_LOCAL_STORAGE_PATH` is absolute. This is a guardrail, not a production storage
recommendation. Hosting-specific URLs, credentials, storage durability, clock-skew policy, and
secret delivery remain deployment configuration; this repository does not invent production
values.

Production also rejects placeholder/local RAG worker URLs and deterministic answer generation. The
OpenAI adapter is enabled only when selected and configured with a server-side key and HTTPS base
URL. It explicitly uses non-persistent responses. Provider routing, fallback, calibrated
thresholds, and production prompt policy remain private deployment concerns.

`APP_URL` must be an origin without a path, query, or fragment. The same production origin and
`/auth/confirm` callback must be allowlisted in the Supabase Auth project configuration. Cookie
security, Auth email delivery, SMTP reputation, redirect allowlists, CAPTCHA/rate limits, and custom
email templates remain environment-specific operational choices; local development uses Mailpit.

## Container contracts

- The web image is a Next.js standalone production server listening on port `3000`.
- The web runtime needs `APP_URL`; the three `NEXT_PUBLIC_*` values are browser-visible build inputs.
- Compose sets `API_INTERNAL_URL=http://api:8000`; production should use its private service origin.
- The API image runs a non-root user and Uvicorn on port `8000`.
- The indexing worker uses the same API image/codebase with `python -m app.rag.worker`; schedule one
  or more instances as a separate process using `rag_worker_login`, never service-role credentials.
- Compose mounts the private `knowledge_data` volume at `/var/lib/ai-support/knowledge`; original
  files are never served by the web server or mounted into its container.
- `/health` is a process liveness check; `/ready` verifies PostgreSQL connectivity for traffic readiness.
- Images install dependencies from committed lockfiles.
- The Supabase CLI stack is for local development only and is not a production database recommendation.
- The API writes structured JSON application logs to stderr. HTTP entries contain request ID, method,
  path, status, and duration; they deliberately omit query strings, bodies, credentials, and tokens.
- Containers keep writable state outside the image filesystem. Back up or remove the
  `knowledge_data` volume according to the same lifecycle as its local database; resetting only
  PostgreSQL does not clean the file volume.

For production, pin base images by digest through an explicit dependency-update process. M0 uses readable version tags so the initial stack remains maintainable while the hosting target is undecided.

## CI gates

GitHub Actions runs independent frontend, backend, and database jobs for pull requests and pushes to
`main`:

- Frontend: locked install, formatting, ESLint, TypeScript, auth/organization/knowledge Vitest coverage, Next.js production build
- Backend: locked uv sync, Ruff formatting/linting, strict mypy, knowledge API/storage/extraction pytest coverage
- Database: local Supabase startup, migration reset, SQL lint, pgTAP RLS tests, and
  FastAPI/PostgreSQL knowledge and tenant integration tests

Branch protection should require all three jobs after the workflow has run successfully on GitHub.

## Production direction

A first production topology should stay small:

- one managed Next.js/web deployment
- one containerized FastAPI deployment, with horizontal replicas only when needed
- managed Supabase PostgreSQL with pgvector; project ownership, region, and plan remain open
- managed private object storage before multi-host or public production deployment; the M2
  `ObjectStorage` interface is the replacement boundary
- one or more indexing worker processes from the API codebase using PostgreSQL leases
- managed secrets, TLS, centralized logs, metrics, traces, and alerting

Avoid adding Kubernetes, a service mesh, or multiple separately owned services without requirements that outweigh their operational cost.

## Release and migration direction

- Build immutable artifacts from reviewed commits.
- Promote the same artifact through staging and production where the platform permits.
- Apply database migrations as a controlled release step, not concurrently from every web process.
- Design schema/application changes for safe ordering and roll-forward recovery.
- Record release health checks and rollback/roll-forward instructions.

## Pre-production checklist

Before a public launch, decide and verify:

- hosting provider, region, domains, TLS, and environment separation
- secret rotation and least-privilege service identities
- database connection pooling and migration execution
- backups, point-in-time recovery, restore drills, RPO, and RTO
- structured logs, metrics, traces, error reporting, and actionable alerts
- rate limits, quotas, abuse protection, and upload scanning
- dependency/container scanning and patch process
- privacy, retention, deletion, and data residency requirements
- load, resilience, accessibility, and browser test results
- incident response and support ownership

These are launch requirements, not claims about the M0 scaffold.

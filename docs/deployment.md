# Deployment and Operations

## Status

M0 supports local development and production-style container builds. No production hosting platform, cloud account, region, domain, or service-level objective has been selected.

## Local modes

### Host applications with containerized database

This is the fastest development loop:

```bash
cp .env.example .env
# Replace all placeholder values in .env.
pnpm install --frozen-lockfile
(cd apps/api && uv sync --frozen)
docker compose up -d db
pnpm dev:web
pnpm dev:api
```

The web and API commands run in separate terminals. PostgreSQL is available on port `5432` by default.

### Complete container stack

```bash
docker compose up --build
```

Compose waits for PostgreSQL health before starting the API and for API health before starting the web application. The named database volume survives container recreation. `docker compose down` stops the stack; adding `--volumes` deletes local database data and must be used deliberately.

## Configuration

`.env.example` is the inventory of local configuration. Copy it to `.env` and replace placeholders. The committed template contains no usable production secret.

- `ENVIRONMENT`: `local`, `test`, `staging`, or `production`
- `LOG_LEVEL`: backend log level
- `API_PORT`: published backend port for the local Compose stack
- `API_CORS_ORIGINS`: JSON array of allowed browser origins
- `NEXT_PUBLIC_API_URL`: public browser-visible API base URL
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: local database bootstrap
- `DATABASE_URL`: host-development database connection URL; Compose overrides the hostname for containers

Production configuration must come from the hosting platform's secret/configuration service. Do not bake secrets into images, source files, build arguments, `NEXT_PUBLIC_*`, or CI logs.

## Container contracts

- The web image is a Next.js standalone production server listening on port `3000`.
- The API image runs a non-root user and Uvicorn on port `8000`.
- Images install dependencies from committed lockfiles.
- The local database image includes pgvector and is not a production database recommendation.
- Containers should write logs to stdout/stderr and keep writable state outside the image filesystem.

For production, pin base images by digest through an explicit dependency-update process. M0 uses readable version tags so the initial stack remains maintainable while the hosting target is undecided.

## CI gates

GitHub Actions runs independent frontend and backend jobs for pull requests and pushes to `main`:

- Frontend: locked install, formatting, ESLint, TypeScript, Vitest coverage, Next.js production build
- Backend: locked uv sync, Ruff formatting/linting, strict mypy, pytest coverage

Branch protection should require both jobs after the initial workflow has run successfully on GitHub.

## Production direction

A first production topology should stay small:

- one managed Next.js/web deployment
- one containerized FastAPI deployment, with horizontal replicas only when needed
- managed PostgreSQL with pgvector (Supabase is a candidate)
- managed object storage when document ingestion is introduced
- a worker process from the API codebase only when durable background work exists
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

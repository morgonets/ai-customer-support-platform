# Deployment and Operations

## Status

M1 uses Supabase CLI for reproducible local Auth and PostgreSQL development and retains
production-style application container builds. No remote project, production hosting platform,
region, domain, or service-level objective has been selected.

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
- `NEXT_PUBLIC_API_URL`: public browser-visible API base URL
- `NEXT_PUBLIC_SUPABASE_URL`: browser-visible Supabase project URL
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: browser-visible Supabase publishable key; not a secret
- `SUPABASE_JWT_ISSUER`, `SUPABASE_JWKS_URL`, `SUPABASE_JWT_AUDIENCE`: backend token-verification contract
- `SUPABASE_JWT_LEEWAY_SECONDS`: optional clock-skew allowance from `0` to `300` seconds; defaults to `0`
- `DATABASE_URL`: least-privilege FastAPI runtime database URL
- `API_DATABASE_PASSWORD`: local runtime-role provisioning input
- `API_DATABASE_URL_DOCKER`, `SUPABASE_JWKS_URL_DOCKER`: container-to-host local endpoints

The local `api_login` password is deliberately absent from migrations. `pnpm db:provision` reads
`API_DATABASE_PASSWORD` from the environment or the ignored root `.env` and sets only that local
role's password. Production roles and passwords must be provisioned by an approved
secret-management/release process; do not place them in migrations.

Production configuration must come from the hosting platform's secret/configuration service. Do not bake secrets into images, source files, build arguments, `NEXT_PUBLIC_*`, or CI logs.
Production startup rejects local/placeholder database and Auth endpoints and requires HTTPS for the
Supabase issuer and JWKS URL. Hosting-specific URLs, credentials, clock-skew policy, and secret
delivery remain deployment configuration; this repository does not invent production values.

`APP_URL` must be an origin without a path, query, or fragment. The same production origin and
`/auth/confirm` callback must be allowlisted in the Supabase Auth project configuration. Cookie
security, Auth email delivery, SMTP reputation, redirect allowlists, CAPTCHA/rate limits, and custom
email templates remain environment-specific operational choices; local development uses Mailpit.

## Container contracts

- The web image is a Next.js standalone production server listening on port `3000`.
- The web runtime needs `APP_URL`; the three `NEXT_PUBLIC_*` values are browser-visible build inputs.
- The API image runs a non-root user and Uvicorn on port `8000`.
- `/health` is a process liveness check; `/ready` verifies PostgreSQL connectivity for traffic readiness.
- Images install dependencies from committed lockfiles.
- The Supabase CLI stack is for local development only and is not a production database recommendation.
- Containers should write logs to stdout/stderr and keep writable state outside the image filesystem.

For production, pin base images by digest through an explicit dependency-update process. M0 uses readable version tags so the initial stack remains maintainable while the hosting target is undecided.

## CI gates

GitHub Actions runs independent frontend and backend jobs for pull requests and pushes to `main`:

- Frontend: locked install, formatting, ESLint, TypeScript, auth-state Vitest coverage, Next.js production build
- Backend: locked uv sync, Ruff formatting/linting, strict mypy, pytest coverage

Branch protection should require both jobs after the initial workflow has run successfully on GitHub.

## Production direction

A first production topology should stay small:

- one managed Next.js/web deployment
- one containerized FastAPI deployment, with horizontal replicas only when needed
- managed Supabase PostgreSQL with pgvector; project ownership, region, and plan remain open
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

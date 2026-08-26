# AGENTS.md

## Purpose

This file contains permanent working agreements for coding agents contributing to the AI Customer Support Platform. Follow these instructions for every task unless a user explicitly gives stricter task-specific direction.

## Product and architecture

- Build a multi-tenant customer-support SaaS, not a collection of demos.
- Keep the system a modular monolith unless measured operational needs justify another deployable service.
- Keep deployable applications in `apps/web` and `apps/api`. Add shared packages only after two real consumers exist.
- Keep transport, persistence, provider, and domain concerns separated. Business rules must not depend directly on framework request objects or vendor SDKs.
- Put external systems such as LLMs, messaging channels, storage, and email behind small typed interfaces.
- Treat tenant isolation as a security invariant. Every tenant-owned record and query must have an explicit tenant boundary, with defense-in-depth controls documented in `docs/database.md`.
- Prefer backward-compatible, versioned HTTP contracts under `/api/v1`. Operational endpoints such as `/health` may remain unversioned.
- Use UTC internally. Use UUIDs for externally visible identifiers unless a documented decision says otherwise.
- Do not implement work from a later roadmap milestone unless the current task explicitly requests it.

## Repository map

- `apps/web`: Next.js App Router application and frontend tests.
- `apps/api`: FastAPI application, Python package, and backend tests.
- `docs`: living architecture, API, database, deployment, and roadmap documentation.
- `.github`: continuous integration and collaboration templates.
- Root configuration: repository-wide developer experience, formatting, containers, and workspace metadata.

If a directory contains a more specific `AGENTS.md`, follow both files; the closest file wins where instructions conflict.

## Required workflow

1. Read the relevant code, tests, documentation, and Git status before editing.
2. Clarify only when a decision cannot be inferred safely. Otherwise state the assumption and proceed.
3. Make the smallest cohesive change that solves the requested problem.
4. Add or update tests for important behavior and regressions.
5. Update documentation in the same change when contracts, architecture, configuration, data, or operations change.
6. Run the relevant format, lint, type-check, test, and build commands.
7. Review the complete diff for accidental changes, generated artifacts, secrets, and scope creep.

Never claim a check passed unless it was run successfully in the current worktree.

## Standard commands

Run commands from the repository root unless noted otherwise.

```bash
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Backend-only commands use uv:

```bash
cd apps/api
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy app tests
uv run pytest
```

Use `pnpm format` to apply repository formatting and `pnpm --dir apps/api api:format` is not a supported command; run `uv run ruff format .` inside `apps/api` for Python.

## TypeScript and frontend rules

- Keep TypeScript strict. Do not weaken compiler or linter settings to make an error disappear.
- Avoid `any`. Narrow `unknown` at system boundaries.
- Prefer server components. Add `"use client"` only where browser state, effects, or browser APIs are necessary.
- Keep components small and accessible. Use semantic HTML and keyboard-compatible interactions.
- Keep API access behind typed modules rather than scattering `fetch` calls through UI components.
- Do not expose server-only values through `NEXT_PUBLIC_*` variables.
- Test behavior and user-visible outcomes. Avoid tests coupled to implementation details.

## Python and backend rules

- Require type annotations for public functions, methods, and meaningful local structures.
- Keep mypy strict and Ruff clean. Do not add blanket ignores; make any narrow suppression explain why it is safe.
- Use Pydantic models at HTTP and configuration boundaries.
- Keep route handlers thin. Domain behavior belongs in framework-independent services or domain modules.
- Use dependency injection for database sessions, tenant context, clocks, IDs, and external providers when those concerns are introduced.
- Use async only for genuinely asynchronous I/O. Never block the event loop with synchronous network or database work.
- Convert expected domain failures to a consistent API error model; do not leak stack traces or provider payloads.

## Data and migrations

- All schema changes require a reviewed migration. Never edit an applied migration.
- Migrations must be safe for existing data and include rollback or recovery notes when rollback is unsafe.
- Prevent cross-tenant reads and writes in repository/query interfaces and test that boundary explicitly.
- Do not store raw secrets, provider credentials, or unnecessary customer content in logs.
- Document new tables, indexes, retention rules, vector dimensions, and deletion behavior in `docs/database.md`.

## Testing and quality

- Important business rules require focused unit tests.
- HTTP, persistence, tenancy, and provider boundaries require integration tests when implemented.
- Every bug fix should include a regression test when practical.
- Tests must be deterministic: freeze or inject time, randomness, IDs, and external services.
- Mock only boundaries owned by another system. Prefer real domain objects for internal collaboration.
- Do not delete or dilute a test merely to make CI pass.

## Security and configuration

- Never commit secrets, tokens, private keys, customer data, or populated `.env` files.
- Add placeholders to `.env.example` and document every new variable.
- Validate configuration at startup and fail clearly when required production values are missing.
- Apply least privilege to CI, database roles, storage, and integrations.
- Treat uploaded documents and model output as untrusted input. Validate size/type and escape rendered content when those features arrive.
- Do not place sensitive data in client bundles, URLs, analytics events, exceptions, or logs.

## Documentation and decisions

- Documentation is part of the implementation, not cleanup work.
- Keep `README.md` focused on evaluating and running the project.
- Keep `docs/architecture.md`, `docs/api.md`, `docs/database.md`, and `docs/deployment.md` synchronized with reality.
- Record significant, hard-to-reverse architectural decisions as ADRs under `docs/adr/` using sequential names such as `0001-decision-title.md`. Do not create an ADR for routine implementation detail.
- Mark planned behavior as planned; never document unimplemented features as available.

## Git practices

- Use Conventional Commits, for example `feat(api): add conversation endpoint` or `docs: clarify tenant isolation`.
- Keep commits small and logically scoped. Do not create artificial commits to make history look busy.
- Do not mix unrelated refactors with behavior changes.
- Never commit broken code. Review the staged diff and validation results before committing.
- Do not push, force-push, rewrite shared history, or delete branches unless explicitly authorized.
- Preserve user changes in a dirty worktree and avoid destructive Git commands.

## Definition of done

A task is done only when the requested behavior is complete, relevant automated checks pass, documentation is current, no secrets or unrelated artifacts are present, and the final diff has been reviewed. Report any check that could not run and why.

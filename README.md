# AI Customer Support Platform

[![CI](https://github.com/morgonets/ai-customer-support-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/morgonets/ai-customer-support-platform/actions/workflows/ci.yml)

A production-oriented, multi-tenant customer-support SaaS in development. The platform is intended to let businesses connect a knowledge base and provide grounded AI answers with citations through web chat and Telegram, while retaining conversation history, analytics, and a path to human support.

> **Project status:** Milestone M1 authentication and tenant foundations are implemented on this
> feature branch and awaiting review. Knowledge ingestion, RAG, customer chat, Telegram, analytics,
> billing, and human handoff remain deferred to later milestones.

## Why this project exists

This public portfolio project demonstrates how to design and deliver an AI-enabled SaaS beyond a prototype: explicit tenant boundaries, provider abstractions, traceable answers, observable operations, tested business logic, reproducible environments, and documentation that evolves with the code.

## Planned capabilities

- Multi-tenant workspaces and role-based access
- Knowledge-base upload, processing, and lifecycle management
- Retrieval-augmented answers with source citations
- Embeddable web chat and Telegram support
- Durable conversation history and feedback
- Human handoff and support workflows
- Quality, usage, and support analytics
- Swappable LLM and embedding providers

See the [roadmap](docs/ROADMAP.md) for sequencing and acceptance goals.

## Architecture at a glance

The repository starts as a modular monolith with two deployable applications:

- `apps/web`: Next.js and TypeScript user interface
- `apps/api`: FastAPI and Python backend
- Supabase PostgreSQL with pgvector: transactional and vector data store

This keeps deployment and local development straightforward while preserving clear internal boundaries for domain logic and external providers. See [architecture](docs/architecture.md), [database](docs/database.md), [API](docs/api.md), and [deployment](docs/deployment.md) for the current design.

## Repository structure

```text
.
├── apps/
│   ├── api/                 # FastAPI application and backend tests
│   └── web/                 # Next.js application and frontend tests
├── docs/                    # Living technical documentation and roadmap
├── .github/                 # CI and pull request workflow
├── compose.yaml             # Local container stack
├── AGENTS.md                # Permanent guidance for coding agents
└── package.json             # Repository-level developer commands
```

## Prerequisites

- Node.js 24
- pnpm 11.19.0
- Python 3.12
- [uv](https://docs.astral.sh/uv/) for Python dependency management
- Docker with Compose for the local Supabase stack and container validation

## Local setup

```bash
git clone https://github.com/morgonets/ai-customer-support-platform.git
cd ai-customer-support-platform
cp .env.example .env
```

Install dependencies:

```bash
pnpm install --frozen-lockfile
cd apps/api && uv sync --frozen && cd ../..
```

Start the local Supabase Auth and PostgreSQL stack:

```bash
pnpm dev:supabase
```

Copy the local publishable key shown by the command into `.env`, then provision the runtime
database login as described in [deployment documentation](docs/deployment.md). Replace every
remaining `replace-with-...` value before starting an application.

Run the applications in separate terminals:

```bash
pnpm dev:web
pnpm dev:api
```

- Web: <http://localhost:3000>
- Local Auth email inbox: <http://127.0.0.1:54324>
- API health: <http://localhost:8000/health>
- API readiness: <http://localhost:8000/ready>
- OpenAPI UI: <http://localhost:8000/docs>

To run the applications in containers, start Supabase first and then use
`docker compose up --build`.

## Quality commands

```bash
pnpm format:check   # Prettier and Ruff formatting
pnpm lint           # ESLint and Ruff linting
pnpm typecheck      # TypeScript and mypy
pnpm test           # Vitest and pytest with coverage
pnpm build          # Production frontend build
pnpm check          # All non-build quality gates
```

CI runs independent frontend, backend, and local database-isolation gates on every pull request and
on pushes to `main`.

## Documentation

- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/architecture.md)
- [Database design](docs/database.md)
- [API conventions](docs/api.md)
- [Deployment and operations](docs/deployment.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Contributing

Use Conventional Commits, keep changes focused, update relevant documentation, and run the applicable quality gates before opening a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

## License

No open-source license has been selected yet. Until one is added, all rights are reserved by the repository owner.

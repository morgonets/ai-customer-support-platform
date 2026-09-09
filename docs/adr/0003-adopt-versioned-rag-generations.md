# ADR 0003: Adopt versioned RAG generations and PostgreSQL-backed indexing

- **Status:** Accepted
- **Date:** 2026-09-09
- **Milestone:** M3 — Grounded answer engine

## Context

M3 must index immutable M2 knowledge versions, retrieve tenant evidence, and produce grounded
answers with citations. Indexing may require many external embedding requests for a single source,
so an HTTP-bound synchronous workflow is not durable enough. The public repository must provide a
complete reference implementation without committing commercial ranking, prompt, or evaluation IP.

## Decision

Keep retrieval and indexing in the FastAPI modular monolith. Run durable indexing as a separate
process from the same API codebase, using PostgreSQL rows, leases, and a restricted non-service-role
worker identity rather than an external broker.

Chunks are immutable exact slices of an immutable `knowledge_source_version`. Chunker and embedding
profiles are versioned. Re-indexing creates a new generation. A replacement is built and validated
while the prior successful generation remains active; activation swaps the two atomically. Source
deletion cascades through all RAG artifacts immediately.

Store variable-dimension pgvector values with explicit dimension checks and an initial
1536-dimensional HNSW expression index. Exact tenant-filtered cosine retrieval is the default.
Reference ranking combines vector and PostgreSQL lexical candidates with equal-weight reciprocal
rank fusion. Model reranking and query rewriting are deferred.

Knowledge evidence is untrusted data. The reference prompt receives a serialized evidence envelope,
has no tools, and requires structured answer parts that cite known evidence identifiers. Questions,
answers, and citation records are not persisted in M3.

## Public and private boundary

The public implementation includes schema/RLS, reference chunking, fixed RRF, provider ports,
deterministic adapters, an opt-in OpenAI adapter, citations, safe telemetry hooks, and synthetic
tests. Production prompts, real evaluation data, calibrated thresholds, advanced chunking,
rewriting, reranking, learned weights, citation scoring, routing/fallback, and automatic tuning must
never enter this repository.

## Consequences

- Indexing survives process loss and can be retried idempotently without Redis or a broker.
- A failed replacement does not make previously validated knowledge unavailable.
- Historical source versions may remain retrievable until a replacement activates; M2 `is_current`
  and M3 `is_active` intentionally have different meanings.
- Model migrations can build inactive generations before switching retrieval.
- A shared HNSW graph can reduce filtered recall, so exact search remains the default until measured.
- The worker adds a least-privilege database credential and an operational process, but not a new
  service or authorization bypass.

## Follow-up constraints

- Retrieval must select only active ready generations belonging to the authorized organization.
- No incomplete generation, provider payload, vector, prompt, question, or answer is public API data.
- Every tenant-owned RAG table must retain FORCE RLS and composite tenant lineage.
- Private strategies must implement the public ports rather than fork tenancy or source lifecycle.

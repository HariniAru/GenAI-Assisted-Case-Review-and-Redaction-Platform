# Milestone: LangChain retrieval for case review

Work in the existing `postgres-migration` branch. Read `AGENTS.md`, `README.md`, `docs/POSTGRES_MIGRATION.md`, and `docs/rag_reference_corpus.md` before editing. If it is missing or older, stop and ask me for that file; do not invent replacement rules.

## Goal

For an existing activity, retrieve relevant fictional redaction rules and illustrative examples using LangChain, local embeddings, and pgvector in the existing PostgreSQL database. Deliver retrieval and inspection only. Do **not** change AI prompts, recommendations, summary generation, reviewer actions, frontend behavior, or add LangGraph yet.

## Implement

1. Enable pgvector on the current PostgreSQL 17 setup. Use a compatible image and an Alembic migration for the extension and vector storage. Preserve the existing Docker volume and case tables; never reset development data. Document any image or migration compatibility decision.
2. Add minimal, version-compatible LangChain dependencies and a small local open-source embedding model (`sentence-transformers`); no paid embedding API. Pin the model identity and vector dimensions in configuration/documentation.
3. Write a repeatable ingestion command for `docs/rag_reference_corpus.md`. Index Sections 1–4 only. Split by policy heading and individual example block so each target stays with its label and reason. Attach `source`, `kind`, `section`, `activity_uid` where applicable, and `status` (`seed` or `proposed`). Do not index Section 5, database activity descriptions, or any evaluation answer keys. Re-running ingestion should update changed chunks without accumulating duplicates or deleting case data.
4. Add a read-only endpoint, `GET /activities/{activity_id}/references`, that embeds the activity description, returns a small number of relevant example/policy chunks with their metadata, and includes the applicable policy rules reliably. Use exact term matching for the small abbreviation glossary when useful; do not depend on vector similarity to retrieve mandatory rules. Return a clear error for an unknown activity or an uninitialized index.

## Verify and report

- Run the existing backend checks against PostgreSQL and the frontend checks if touched. Add focused integration checks for migration, repeat ingestion, retrieval, metadata, and 404 behavior. Use the isolated test database; do not modify local review records.
- Inspect retrieval for ACT-1001-01, ACT-1002-02, ACT-1004-01, and ACT-1005-01, including a negative example. These are **sanity checks**, not a held-out accuracy score, because their labeled examples are in the corpus.
- Update setup commands and document how to ingest, re-ingest, and inspect results. Report the files changed, exact commands and results, sample retrieved sections, and any remaining limitations. Keep this as one reviewable commit/PR; do not merge into `main`.

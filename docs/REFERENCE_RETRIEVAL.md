# Local reference retrieval

[Grounded recommendations](GROUNDED_AI_SETUP.md) and case analysis reuse this index;
the inspection endpoint is also available. The corpus is still draft synthetic policy; retrieval does
not turn proposed labels into approved decisions.

## Setup and data preservation

The Compose image is `pgvector/pgvector:0.8.6-pg17-trixie`. The prior database ran
PostgreSQL 17.11 on Debian Trixie with glibc collation version 2.41. The selected
image also runs PostgreSQL 17.11 on Trixie. Keeping both the PostgreSQL major
version and OS family avoids an unnecessary major upgrade or Bookworm collation
downgrade. The existing `postgres_data` volume and mount path are unchanged.

From the repository root:

```bash
docker compose --env-file backend/.env.postgres pull
docker compose --env-file backend/.env.postgres up -d --wait
cd backend
uv sync --locked --extra dev
uv run --env-file .env.postgres alembic upgrade head
uv run --env-file .env.postgres python -m app.ingest_references
```

Do not run `down -v`, reset the volume, or reseed existing review records for this
milestone. Migration `0002_reference_chunks` enables the database-wide `vector`
extension in `public` and adds only `reference_chunks`. Installing an extension
requires a database role with sufficient privileges (the local Compose owner
has these). Downgrading to `0001_initial_schema` drops reference chunks but
preserves all case tables and leaves the shared extension installed.

The first ingestion downloads a public embedding model from Hugging Face. All
embedding computation then runs locally on CPU; no paid API or external
embedding service receives activity text. Allow disk space for PyTorch and the
model cache. Later runs reuse the Hugging Face cache. After the first successful
download, `HF_HUB_OFFLINE=1` can enforce offline model loading. Model download or
local inference failures return a controlled error, not a switch to another model.

## Model and dependencies

The configuration pins:

- Model: `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0).
- Revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.
- Dimension: 384, matching the Alembic `vector(384)` column.
- Embedding algorithm: split tokenized input into 200-token windows, encode each,
  average the window vectors, and normalize. Whole corpus chunks stay intact in
  storage and responses. This avoids MiniLM's default 256-token truncation on
  larger examples; averaging is a simple compromise that can dilute specific
  facts in long text.

`langchain-core` supplies Documents, Embeddings, and the BaseRetriever interface;
`sentence-transformers` runs the local model; `pgvector` supplies SQLAlchemy's
vector column and cosine-distance expression. Retrieval needs no hosted embedding integration or extra vector-store table manager.
LangGraph coordinates the separate case-analysis workflow. `uv.lock` pins the resolved dependency tree. LangChain's transitive
LangSmith tracing is explicitly disabled in this endpoint.

Model identity, revision, dimensions, and the averaging algorithm form the index
compatibility contract. Settings reject alternative model names or dimensions;
a deliberate future model change must update configuration, storage if needed,
and re-ingest. Each row stores its model/algorithm key; incompatible stored keys
produce 503 until re-ingestion. `REFERENCE_EXAMPLES` defaults to 3 (allowed 1–5).

## Ingestion and re-ingestion

Run the same command after editing the corpus:

```bash
cd backend
uv run --env-file .env.postgres python -m app.ingest_references
```

The source path resolves relative to this repository, not the current directory.
Only `docs/rag_reference_corpus.md`, Sections 1–4, is parsed:

- Six policy chunks: general rules, four labels, ambiguity/scope.
- Seventeen glossary rows, each retaining its term, meaning, and note.
- Eight whole activity example blocks, including target/label/reason tables and
  negative examples. Each carries the section's explanation of draft examples.
- One summary style guide.

Section 5 is never indexed. Do not put evaluation answer keys into Sections 1–4;
the parser intentionally treats their contents as corpus reference material.
Database activity descriptions are embedded transiently for the query, never
inserted into the reference table.

Stable chunk IDs hash source plus section heading. Unchanged content/metadata
and model keys reuse vectors. Changed chunks update in place; removed headings
remove only this corpus's stale reference rows. The update is one transaction
protected by a PostgreSQL advisory lock, so concurrent ingestions serialize and
readers see committed versions. Failures roll back the index changes. No case,
activity, user, redaction, or redaction-type row is modified.

Metadata includes `source`, `kind`, `section`, `status`, and `activity_uid` for
examples (`term` for glossary rows). Only the existing ACT-1001-01 annotation
block has `status=seed`; remaining chunks are `proposed`, including the draft
policy and glossary. IDs and metadata remain stable across unchanged ingestion.

## Inspection endpoint

```bash
uv run --env-file .env.postgres uvicorn app.main:app --reload
curl http://127.0.0.1:8000/activities/1/references
```

Use an actual activity ID from `GET /cases/{case_id}/activities`. The endpoint
returns a JSON array of LangChain Documents with `id`, `page_content`, `metadata`,
and `type`. It always returns **all six policy chunks** so no semantic search
miss can omit a rule; includes glossary entries matched case-insensitively with
word boundaries (including `c/b`); then returns the three closest example blocks
by pgvector cosine distance. Summary guidance is stored but not included in this
activity-redaction inspection response.

`metadata.retrieval` is `mandatory_policy`, `exact_term`, or `semantic`. Semantic
results include `cosine_distance` (smaller is closer, not a confidence score).
The tiny corpus uses exact nearest-neighbor ordering without an approximate
HNSW/IVFFlat index. An activity UID is metadata, not a shortcut for ranking.

Unknown activity: 404. Missing migration, empty/incomplete mandatory policy,
incompatible embedding model, or unavailable index: 503 with guidance. No new
frontend route is added; inspect through curl, FastAPI `/docs`, or DBeaver.

## Verification and limitations

See [README verification](../README.md#verification) for both database modes.
Tests use deterministic fake vectors in isolated PostgreSQL schemas and exercise
migration preservation, repeat/update/remove ingestion, rollback, required policy,
metadata, missing records, and incompatible model errors. SQLite uses a JSON
storage variant for portable schema/tests; live retrieval requires PostgreSQL.

`python -m app.inspect_references` is a read-only real-embedding diagnostic for
seeded activities. Use `uv run --env-file .env.postgres python -m app.inspect_references`
from `backend/`. These are corpus sanity checks, not a held-out accuracy score:
the synthetic activity examples are already in the corpus. Relevance is limited
by the small English model, window averaging, and tiny synthetic corpus.

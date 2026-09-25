# Local reference retrieval

This milestone retrieves and displays fictional reference material only. It does
not change AI prompts, recommendations, summary generation, reviewer actions,
or the frontend. The corpus is still draft synthetic policy; retrieval does
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
vector column and cosine-distance expression. No full LangChain framework,
LangGraph, hosted embedding integration, or extra vector-store table manager is
needed. `uv.lock` pins the resolved dependency tree. LangChain's transitive
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

## Checks

From `backend/`:

```bash
uv run ruff format --check .
uv run ruff check .
uv run --env-file .env.postgres pytest
uv run --env-file .env.postgres alembic check
uv run pytest
```

PostgreSQL tests use the existing dedicated `_test` database and per-test schemas;
`public` is in their search path solely to resolve the shared vector extension.
Tests never seed or mutate the development review records. SQLite regression
tests use a JSON storage variant to exercise old application behavior; semantic
retrieval itself requires PostgreSQL. The `sqlite-baseline` tag remains unchanged.
Tests use deterministic fake vectors for fast, offline integration checks;
actual-model sanity checks are documented below and are not an accuracy score.

## Actual verification results

Commands run from `backend/` (with `UV_CACHE_DIR=/tmp/case-review-uv-cache` as a
sandbox cache-location override):

```bash
uv sync --extra dev
uv run ruff format .
uv run ruff check .
uv run --env-file .env.postgres alembic upgrade head
uv run --env-file .env.postgres pytest -q
uv run pytest -q
uv run --env-file .env.postgres python -m app.ingest_references
HF_HUB_OFFLINE=1 uv run --env-file .env.postgres python -m app.ingest_references
HF_HUB_OFFLINE=1 uv run --env-file .env.postgres python -m app.inspect_references
uv run --env-file .env.postgres alembic check
```

The container was pulled and started using the root Compose commands above.
Initial ingestion: `chunks=32 updated=32 removed=0`. Offline repeat:
`chunks=32 updated=0 removed=0`. Real-model HTTP endpoint checks used FastAPI's
TestClient against the existing development activities and confirmed 200s and
an unknown-activity 404, without writes. All five original case tables had
identical row counts and ordered-row hashes before and after the milestone.

| Activity queried | Ranked example activity UIDs (closest first) |
| --- | --- |
| ACT-1001-01 | ACT-1001-01, ACT-1004-01, ACT-1004-02 |
| ACT-1002-02 | ACT-1002-02, ACT-1004-02, ACT-1004-01 |
| ACT-1004-01 | ACT-1004-01, ACT-1002-02, ACT-1004-02 |
| ACT-1005-01 | ACT-1005-01, ACT-1002-01, ACT-1001-01 |
| ACT-1001-02 (negative) | ACT-1001-02, ACT-1004-02, ACT-1004-01 |

Each response included all six `1.*` policy sections, plus exact glossary
matches. For ACT-1005-01, the first example contains the explicit `No legal
advice discussed` negative for PRIVILEGED; the always-included PRIVILEGED policy
also states that exception. ACT-1001-02's first example explicitly suggests no
redactions. Lower-ranked neighbors can contain unrelated positive examples:
retrieval alone must never be treated as a redaction decision.

Results: PostgreSQL **12 passed**; SQLite **9 passed, 3 intentionally skipped**
(pgvector-only integration tests). Ruff format/lint passed; Alembic detected no
model/schema drift. The real embedding library emits a non-blocking rename
warning for `get_sentence_embedding_dimension`; dimensions are verified as 384.
Frontend checks were not run because no frontend files or behavior changed.
No held-out evaluation, generation changes, or browser UI were part of this
milestone. Retrieval relevance remains limited by this small English model,
window averaging, and the deliberately tiny synthetic corpus.

References: [pgvector supported images](https://github.com/pgvector/pgvector#docker),
[MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
[LangChain embedding interface](https://docs.langchain.com/oss/python/integrations/embeddings).

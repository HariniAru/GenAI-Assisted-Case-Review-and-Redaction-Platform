# GenAI Case Review

A learning-focused case review and text-redaction platform using synthetic
records, FastAPI, SQLAlchemy, React, and a reviewer-controlled AI workflow.
**`main` is the complete application and the branch to study.** Choose SQLite
or PostgreSQL through `DATABASE_URL`; switching databases does not require a
branch switch. `postgres-migration` and the `sqlite-baseline` tag are preserved
as historical checkpoints.

AI output is advisory. Generation returns unsaved drafts; each redaction and
the summary require separate approval. Reading cases never generates or saves
summaries. Activity text remains unchanged, and redactions refer to exact
Unicode character spans in that text.

## Database modes

| Feature | SQLite | PostgreSQL + pgvector |
| --- | --- | --- |
| Case list/detail, saved summaries and redactions | Yes | Yes |
| Close/reopen cases; manual redaction create/update/delete API | Yes | Yes |
| React selection, manual create/delete, exact-span rendering | Yes | Yes |
| Explicit summary approval API (reviewed text only) | Yes | Yes |
| Corpus ingestion and semantic reference retrieval | No | Yes |
| Live grounded AI recommendations and case-analysis drafts | No | Yes, with model credentials and an ingested corpus |
| Acceptance of newly grounded redaction drafts | Requires indexed policy unavailable in normal SQLite setup | Yes |
| Studio and case-analysis LangSmith traces | No supported live analysis | Optional |

SQLite uses JSON storage for the reference model only to keep migrations and
isolated tests portable; it has no pgvector search. AI controls remain in the
shared UI, but live retrieval/analysis returns an unavailable error in SQLite.
There is no ungrounded fallback. Displaying or deleting an already saved AI
redaction works in either mode. The summary approval API is database-independent,
but the UI obtains its summary drafts through PostgreSQL-backed **Analyze case**.

## Install

Use Python 3.12+ with `uv`, and Node.js/npm (Node 22.22.2 was used for verification).
The locked test dependencies require Node `^22.22.2`, `^24.15.0`, or `>=26`.
Docker Desktop is needed only for
local PostgreSQL. Run the API and frontend on the host.

```bash
# repository root
cd backend
uv sync --locked --extra dev --extra studio
cd ../frontend
npm ci
```

The optional `studio` extra installs the local graph server; omit it if unused.
When running API and Studio together, keep `--extra studio` in uv commands to
avoid removing its optional packages from the shared environment.

## SQLite setup and switching

Stop the running API (and Studio) before changing modes. From `backend/`, use
an explicit URL so it overrides any different URL in `.env` or your shell:

```bash
DATABASE_URL=sqlite:///./case_review.db uv run --extra studio alembic upgrade head
DATABASE_URL=sqlite:///./case_review.db uv run --extra studio uvicorn app.main:app --reload
```

The path is relative to `backend/`. These commands reuse the existing SQLite
file; migrations add missing schema without deleting review records. For a
**new, empty database only**, seed it after migration and before starting the API:

```bash
DATABASE_URL=sqlite:///./case_review.db uv run --extra studio python -m app.seed
```

Do not reseed an existing database just to switch modes: the synthetic seed
has status adjustments as well as duplicate prevention. No model credentials,
Docker, or reference ingestion are needed for SQLite's core review features.

## PostgreSQL setup and switching

From the repository root, create a local environment file only if absent:

```bash
cp -n backend/.env.example backend/.env.postgres
```

Set its `POSTGRES_PASSWORD` and replace `<password>` in both database URLs with
the same password. URL-encode special characters in URLs, or use a hexadecimal
password. Local `.env` files are ignored; do not commit them. Keep provider and
optional LangSmith credentials in `backend/.env`. Avoid duplicating those values
in `.env.postgres`, since uv supplies that file as environment overrides.

```bash
# repository root
unset DATABASE_URL TEST_DATABASE_URL
docker compose --env-file backend/.env.postgres up -d --wait
cd backend
uv run --extra studio --env-file .env.postgres alembic upgrade head
# New, empty database only:
uv run --extra studio --env-file .env.postgres python -m app.seed
# Initial reference setup, or after editing the corpus:
uv run --extra studio --env-file .env.postgres python -m app.ingest_references
uv run --extra studio --env-file .env.postgres uvicorn app.main:app --reload
```

For subsequent switches to PostgreSQL, stop the SQLite API, start Compose if
needed, and run only the PostgreSQL API command. Existing exported variables
have precedence over uv's environment files; unset stale database variables first.
The API's settings read `.env` for remaining values. Restart after changing either
file; do not rely on `--reload` to reload environment variables.

PostgreSQL listens on `127.0.0.1:5432`; update `POSTGRES_PORT` and both URL ports
if necessary. Docker's `postgres_data` volume stores its data independently of
SQLite. `docker compose --env-file backend/.env.postgres down` stops it without
deleting data. **Do not use `down -v` or reset either database to switch modes.**
Initialization credentials apply only when the volume is first created. Switching
URLs selects separate data stores; it does not copy or synchronize their records.

The fresh synthetic seed contains 1 reviewer, 4 redaction types, 5 cases,
8 activities, and 6 saved redactions. The demo reviewer is
`jordan.lee@example.com`; authentication is not implemented.

## Frontend and AI

Edit `frontend/index.html` and files under `frontend/src/`. `frontend/dist/` is
generated by `npm run build`, ignored by Git, and overwritten by the next build;
it is not a second frontend implementation. `node_modules/`, `.venv/`, and
`.langgraph_api/` are also generated/local directories, not application source.
TypeScript settings live in `frontend/tsconfig*.json`; dependency manifests and
lockfiles remain tracked so installations are reproducible.

In another terminal, from `frontend/`:

```bash
npm run dev
```

Open the printed Vite URL, normally `http://localhost:5173`. Its proxy forwards
requests to the API at `127.0.0.1:8000` in either database mode. API documentation
is available at `http://127.0.0.1:8000/docs`.

For PostgreSQL AI generation, set `HF_TOKEN`, `HF_MODEL`, and `HF_PROVIDER` in
`backend/.env` using the example settings. The existing provider is Hugging Face
with Qwen; model calls can incur charges. Reference embeddings run locally on
CPU after the initial public-model download. All data must remain synthetic.

- [Architecture and core API](docs/API.md): component boundaries and review rules.
- [Reference retrieval](docs/REFERENCE_RETRIEVAL.md): corpus ingestion and pgvector search.
- [Grounded recommendations](docs/GROUNDED_AI_SETUP.md): evidence and exact-span acceptance.
- [Case analysis](docs/CASE_ANALYSIS.md): parallel LangGraph branches and independent approval.
- [Studio and LangSmith](docs/LANGGRAPH_STUDIO.md): optional graph visualization and tracing.
- [Synthetic reference corpus](docs/rag_reference_corpus.md): indexed policy, glossary, examples, and summary guide.

For a guided reading order and the implementation's learning scope, start with
[studying the code](docs/API.md#studying-the-code).

## Verification

From `backend/`:

```bash
uv run --extra dev --extra studio ruff format --check .
uv run --extra dev --extra studio ruff check .
env -u TEST_DATABASE_URL uv run --extra dev --extra studio pytest -q
uv run --extra dev --extra studio --env-file .env.postgres pytest -q
uv run --extra studio --env-file .env.postgres alembic check
```

SQLite tests use temporary files, regardless of the developer's `DATABASE_URL`.
PostgreSQL tests require `TEST_DATABASE_URL` pointing to a separate database
whose name ends in `_test`; each test creates and removes its own random schema.
Create the test database once if absent (from the repository root):

```bash
docker compose --env-file backend/.env.postgres exec -T postgres createdb -U case_review case_review_test
```

Tests exercise migrations, constraints, seed behavior, core API, exact spans,
grounding, graph concurrency, and approvals. SQLite runs fake-retriever/model
tests, which do not imply SQLite supports live vector retrieval. PostgreSQL-only
integration tests skip in SQLite mode. Tests disable hosted tracing and model
calls and never reset the development databases.

From `frontend/`:

```bash
npm run lint
npm test -- --run
npm run build
```

## Study the historical SQLite version

Configuration switching on `main` is the normal workflow. To inspect the exact
pre-migration implementation, stop servers and commit or stash tracked edits:

```bash
# repository root
git switch --detach sqlite-baseline
cd backend
DATABASE_URL=sqlite:///./case_review.db uv run --no-sync uvicorn app.main:app --reload
```

The installed environment can run this snapshot; `--no-sync` avoids changing
packages or creating a historical lockfile. For study edits, create a branch with
`git switch -c sqlite-study sqlite-baseline` instead. To return to the current
code, run `git switch main` from the root, synchronize dependencies, and select
either database using the commands above. Git switches neither ignored local
databases nor `.env` files nor Docker volumes. Historical milestone documents
and experiments remain available in Git history and `postgres-migration`.

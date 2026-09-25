# PostgreSQL migration

## Scope and preserved baseline

`sqlite-baseline` tags commit `dbc2fe5` on `main`. This baseline removes previously
tracked frontend build outputs and expands ignore rules, without changing the
SQLite application. The original generated files were retained locally; Git
history before the baseline still contains the previously committed outputs.
`docs/rag_reference_corpus.md` remains untracked by request.

All PostgreSQL work is on `postgres-migration` in the same repository. The old
SQLite database and `.env` are untouched. This is a fresh PostgreSQL schema and
synthetic seed, not a transfer of local SQLite review history. No pgvector or RAG
was added. Earlier milestone documents describe historical requirements; this
note and README supersede their SQLite setup commands for this branch.

## Implementation choices

- `compose.yaml`: official PostgreSQL 17 image, localhost-only port, readiness
  check, persistent named volume, password supplied through an ignored file.
- `backend/.env.example`, `app/config.py`: explicit `DATABASE_URL`; no implicit
  fallback to a SQLite file. Separate `.env.postgres` lets branch switching reuse
  the old `.env` unchanged. Existing AI credentials remain in that old file.
- `pyproject.toml`, `uv.lock`: Psycopg 3 binary driver avoids a local compiler and
  libpq installation. The new lockfile resolves all previously unlocked
  dependencies, so several existing packages also received newer compatible
  versions. No application changes were made for those updates.
- `app/database.py`: retain synchronous sessions and SQLite compatibility;
  connection pre-ping detects stale connections after a PostgreSQL restart.
- `alembic.ini`, `migrations/env.py`: resolve the configured URL and accept an
  existing test connection. The initial migration itself already works on
  PostgreSQL and remains unchanged; no second schema revision is needed.
- `app/models.py`: explicitly use timezone-aware SQLAlchemy datetime columns to
  match the existing migration. PostgreSQL can distinguish timestamp types;
  leaving the old inferred types would cause schema drift and timezone issues.
- `tests/conftest.py` and database tests: apply actual Alembic migrations on
  isolated PostgreSQL schemas or temporary SQLite files. A rolled-back insert
  consumes a PostgreSQL sequence value, so the constraint test now uses the
  returned case ID instead of assuming it is 1.
- The seed script and application routers/frontend are unchanged. Current seed
  counts are 5 cases and 8 activities, beyond the original seeding milestone.
  Its pre-existing second-run status adjustments remain intact.

References: [SQLAlchemy Psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg),
[official PostgreSQL container](https://hub.docker.com/_/postgres).

## Verification on the migration branch

- Docker Desktop 4.92.0, Engine 29.8.0, Compose 5.5.1 accessible.
- `docker compose --env-file backend/.env.postgres up -d --wait`: healthy.
- `uv sync --extra dev`: installed driver and generated dependency lock.
- `uv run --env-file .env.postgres alembic upgrade head`: fresh database upgraded.
- `uv run --env-file .env.postgres python -m app.seed`, twice: both returned
  users=1, redaction_types=4, cases=5, activities=8, redactions=6.
- `uv run --env-file .env.postgres alembic check`: no schema differences.
- Ruff format and lint: passed.
- `uv run pytest`: 8 passed on SQLite.
- `uv run --env-file .env.postgres pytest`: 8 passed on PostgreSQL, including
  destructive migration round-trip only inside disposable test schemas.
- Both runs have one upstream Starlette/httpx deprecation warning.
- Frontend `npm run lint`, `npm test -- --run` (1 test), `npm run build`: passed.
- Live PostgreSQL API `/health`: HTTP 200, `{"status":"ok"}`.
- Live requests through a temporary Vite proxy returned the two CASE-1001
  activities and six saved redactions from PostgreSQL.
- Existing user servers occupied ports 8000/5173, so temporary verification used
  8001/5174 without stopping them. No frontend source/config changes were needed.

Full visual browser verification remains outstanding: browser connections were
unavailable and native computer-use permissions were not granted. Backend tests
exercise the endpoints used for create/edit/delete, close/reopen, AI acceptance,
and summary persistence; they do not establish that every visual interaction
works. External AI inference was not called. With the PostgreSQL backend running
on 8000, manually check case navigation, selection/create/edit/delete, refresh
persistence, and close/reopen in the normal frontend before treating browser
verification as complete.

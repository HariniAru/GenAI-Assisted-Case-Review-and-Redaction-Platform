# GenAI Case Review

Learning-focused case review and text-redaction platform using synthetic records,
FastAPI, SQLAlchemy, and React. The `postgres-migration` branch uses PostgreSQL;
`main` and the `sqlite-baseline` tag preserve the SQLite implementation.
No RAG or pgvector is included in this migration.

## Local PostgreSQL setup

Prerequisites: Docker Desktop running, Python 3.12+ with `uv`, and Node.js/npm.
The API and frontend run on the host; only PostgreSQL runs in Docker.

From the repository root, create a separate local environment file **only if it
does not already exist**:

```bash
cp -n backend/.env.example backend/.env.postgres
```

In `backend/.env.postgres`, set `POSTGRES_PASSWORD` to a local password and replace
`<password>` in both URLs with the same value. Use a hexadecimal password (for
example, generated with `python3 -c 'import secrets; print(secrets.token_hex(24))'`)
or URL-encode special characters in URLs. Never commit this file. A configured
`.env.postgres` was already created during this migration on the original machine.
Keep the existing SQLite `backend/.env` unchanged.

```bash
docker compose --env-file backend/.env.postgres up -d --wait
cd backend
uv sync --locked --extra dev
uv run --env-file .env.postgres alembic upgrade head
uv run --env-file .env.postgres python -m app.seed
uv run --env-file .env.postgres uvicorn app.main:app --reload
```

`uv run --env-file .env.postgres` supplies `DATABASE_URL` to the API, Alembic, and
seed command. Settings still read `backend/.env` for other values, including AI
provider configuration, unless overridden by environment variables. Remove any
old exported `DATABASE_URL`/`TEST_DATABASE_URL` from your shell before using these
commands: existing shell variables take precedence over uv's environment file.

The database listens only on `127.0.0.1:5432`. If that port is occupied, change
`POSTGRES_PORT` and both URL ports together. Docker stores PostgreSQL data in the
`postgres_data` named volume. `docker compose --env-file backend/.env.postgres down`
stops it without deleting data; do not add `-v` unless you intend to erase that
volume. Initialization credentials apply only when the volume is first created.

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). The existing Vite proxy
forwards API requests to `http://127.0.0.1:8000`.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/cases
curl http://127.0.0.1:8000/cases/1/activities
```

The synthetic seed contains 1 user, 4 redaction types, 5 cases, 8 activities, and
6 saved redactions. Repeated runs do not add duplicates. The existing seed's
status adjustments for CASE-1001 and CASE-1002 are preserved. It does not import
or modify your old SQLite records. The demo reviewer remains
`jordan.lee@example.com`; authentication is not implemented.

## Verification

Create the separate test database once, from the repository root:

```bash
docker compose --env-file backend/.env.postgres exec -T postgres createdb -U case_review case_review_test
```

Then, from `backend/`:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run --env-file .env.postgres pytest
uv run --env-file .env.postgres alembic check
```

Without `TEST_DATABASE_URL`, tests use temporary SQLite files. With it, tests
require a `postgresql+psycopg` URL whose database name ends in `_test`. Each test
creates and removes its own random schema using Alembic; development data is not
used. Tests cover upgrade/downgrade/upgrade, model/schema agreement, constraints,
seed counts and offsets, timestamps, case status changes, manual redactions,
accepted AI redactions, and summaries. AI tests use a fake provider without
external model calls.

From `frontend/`:

```bash
npm run lint
npm test -- --run
npm run build
```

See [migration notes and verification results](docs/POSTGRES_MIGRATION.md).

## Switch between SQLite and PostgreSQL

Run Git commands from the repository root. Stop API/frontend servers first,
especially reload servers, so they do not reload midway through a branch switch.
Commit or stash any new tracked edits before switching. The untracked
`docs/rag_reference_corpus.md` remains local and accessible on either version.

Study the exact SQLite snapshot:

```bash
git switch --detach sqlite-baseline
cd backend
DATABASE_URL=sqlite:///./case_review.db uv run --no-sync uvicorn app.main:app --reload
```

The already-installed environment can run this snapshot; `--no-sync` avoids
changing dependencies or creating a lockfile in the historical checkout. On a
new machine, install baseline dependencies with `uv sync --extra dev` first;
the baseline predates a committed lockfile. The existing SQLite file is reused;
do not rerun the seed if you want to preserve its current contents exactly.

To make study edits on a branch rather than detached HEAD, use
`git switch -c sqlite-study sqlite-baseline`. Or use `git switch main` to return
to the preserved SQLite branch.

Return to PostgreSQL, from the repository root:

```bash
git switch postgres-migration
docker compose --env-file backend/.env.postgres up -d --wait
cd backend
uv sync --locked --extra dev
uv run --env-file .env.postgres uvicorn app.main:app --reload
```

Start the frontend with `npm run dev` from `frontend/` on either version. Git
switches code, not ignored `.env` files, the SQLite database, or Docker volumes.
Neither branch nor tag has been pushed or merged by this migration.

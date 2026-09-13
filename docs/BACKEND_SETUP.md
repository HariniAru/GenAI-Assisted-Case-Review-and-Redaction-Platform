# Backend Setup: Steps 1–3

## Goal

Create the project structure, configure a working Python/FastAPI backend, and implement the initial database migration.

Complete only the work described here. If anything else is necessary, explain why and ask before proceeding.

## Step 1: Create the project structure

```text
genai-case-review/
├── AGENTS.md
├── README.md
├── .gitignore
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .env.example
│   ├── alembic.ini
│   ├── migrations/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   └── schemas.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_health.py
│       └── test_models.py
├── frontend/
│   └── .gitkeep
├── knowledge/
│   └── .gitkeep
└── docs/
    └── BACKEND_SETUP.md
```

- Preserve `AGENTS.md` and this setup file.
- Add a root `README.md` with the project purpose and backend setup, migration, testing, and server commands.
- Add a root `.gitignore` for Python environments and caches, local databases, `.env`, OS files, and IDE files.

## Step 2: Set up the Python backend

### Dependencies

- Use Python 3.12 and `uv`.
- Runtime: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, and `pydantic-settings`.
- Development: `pytest`, `httpx`, and `ruff`.
- Commit `pyproject.toml` and the generated `uv.lock`.
- If `uv` is unavailable, ask before using another approach.

### Configuration and database

- In `app/config.py`, load settings with `pydantic-settings`.
- Add this local default to `.env.example`:

```text
DATABASE_URL=sqlite:///./case_review.db
```

- In `app/database.py`, create a synchronous SQLAlchemy engine, typed declarative base, session factory, and FastAPI session dependency.
- For SQLite, set `check_same_thread=False` and enable foreign-key enforcement on every connection.
- Use Alembic—not `Base.metadata.create_all()`—to create the application schema.

### FastAPI

Create the application in `app/main.py` and add:

```http
GET /health
```

It must return HTTP 200:

```json
{"status": "ok"}
```

## Step 3: Implement the database schema

Use singular Python model names and plural SQL table names.

### `User` / `users`

```text
id                  INTEGER PRIMARY KEY
first_name          VARCHAR NOT NULL
last_name           VARCHAR NOT NULL
email               VARCHAR NOT NULL UNIQUE
created_at          TIMESTAMP NOT NULL
updated_at          TIMESTAMP NOT NULL
```

One user can commit many redactions.

### `Case` / `cases`

```text
id                  INTEGER PRIMARY KEY
case_number         VARCHAR NOT NULL UNIQUE
status              VARCHAR NOT NULL
ai_summary          TEXT NULL
created_at          TIMESTAMP NOT NULL
updated_at          TIMESTAMP NOT NULL
```

`status` must allow only `OPEN`, `IN_PROGRESS`, or `CLOSED`. One case contains many activities.

### `Activity` / `activities`

```text
id                  INTEGER PRIMARY KEY
case_id             INTEGER NOT NULL FK → cases.id
activity_uid        VARCHAR NOT NULL UNIQUE
activity_type       VARCHAR NOT NULL
description         TEXT NOT NULL
created_at          TIMESTAMP NOT NULL
```

Each activity belongs to one case and can contain many redactions. Treat `description` as immutable.

### `RedactionType` / `redaction_types`

```text
id                  INTEGER PRIMARY KEY
name                VARCHAR NOT NULL UNIQUE
created_at          TIMESTAMP NOT NULL
updated_at          TIMESTAMP NOT NULL
deleted_at          TIMESTAMP NULL
```

One redaction type can classify many redactions.

### `Redaction` / `redactions`

```text
id                  INTEGER PRIMARY KEY
activity_id         INTEGER NOT NULL FK → activities.id
redaction_type_id   INTEGER NOT NULL FK → redaction_types.id
user_id             INTEGER NOT NULL FK → users.id
source              VARCHAR NOT NULL
redaction_text      VARCHAR NOT NULL
starting_position   INTEGER NOT NULL
created_at          TIMESTAMP NOT NULL
updated_at          TIMESTAMP NOT NULL
```

- `source` must allow only `AI` or `MANUAL`.
- `starting_position` must be greater than or equal to zero.
- Each redaction belongs to one activity, has one redaction type, and is committed by one user.
- Calculate the end position when needed with `starting_position + len(redaction_text)`.

### Model and migration requirements

- Use `back_populates` for:
  - `Case.activities ↔ Activity.case`
  - `Activity.redactions ↔ Redaction.activity`
  - `RedactionType.redactions ↔ Redaction.redaction_type`
  - `User.redactions ↔ Redaction.user`
- Index `activities.case_id`, `redactions.activity_id`, `redactions.redaction_type_id`, and `redactions.user_id`.
- Use timezone-aware UTC timestamps with one consistent strategy.
- Configure Alembic with the application's database URL and model metadata.
- Create and review one initial migration containing all five tables, foreign keys, indexes, and constraints.
- Verify upgrade from an empty database, downgrade to `base`, and upgrade again.

## Tests and completion

Add tests that verify:

1. The health endpoint returns HTTP 200 and `{"status": "ok"}`.
2. Alembic migrates an empty temporary SQLite database.
3. All five tables exist.
4. Invalid case status, redaction source, and negative starting positions are rejected.
5. SQLite foreign-key enforcement rejects invalid related IDs.

Run from `backend/`:

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run pytest
uv run alembic downgrade base
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Confirm `GET http://127.0.0.1:8000/health`, then stop the server. Report the files changed, dependencies installed, migration created, checks run, and any deviations. Recommend—but do not implement—the next milestone.

# GenAI Case Review

Learning-focused case review and text-redaction platform.

## Backend

From `backend/`, install dependencies and run checks:

```bash
python3 -m pip install -e '.[dev]'
python3 -m alembic upgrade head
python3 -m pytest
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The health endpoint is available at `GET /health`.

Seed deterministic synthetic data after applying migrations:

```bash
.venv/bin/python -m app.seed
```

Read-only case endpoints:

```bash
curl http://127.0.0.1:8000/cases
curl http://127.0.0.1:8000/cases/1
curl http://127.0.0.1:8000/cases/1/activities
```

This environment did not provide `uv`, so dependencies were installed in `backend/.venv` with pip. The documented `uv.lock` could not be generated; `pyproject.toml` remains the dependency source of truth until uv is available.


to run backend:

cd backend
.venv/bin/alembic upgrade head       
.venv/bin/python -m app.seed
.venv/bin/python -m uvicorn app.main:app --reload

to run frontend:
cd frontend
npm run dev

to lint and test frontend:
npm run lint
npm test -- --run
npm run build

to run openai_test.py:
.venv/bin/python openai_test.py            
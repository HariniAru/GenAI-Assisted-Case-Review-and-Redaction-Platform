# Read-Only Case API

## Goal

Expose the seeded case-review data through read-only FastAPI endpoints. This API will later supply the React case list and review pages.

Complete only the work described here. If anything else is necessary, explain why and ask before proceeding.

## Request flow

For each endpoint:

1. FastAPI matches the request to a case router.
2. The router receives a SQLAlchemy session through the existing dependency.
3. SQLAlchemy reads the requested database records and relationships.
4. Pydantic validates and serializes the result.
5. FastAPI returns JSON or a clear HTTP error.

Use the existing models, database configuration, seed function, and project conventions. Do not add dependencies or database migrations for this milestone.

## API response schemas

Create typed Pydantic v2 response schemas. Use `ConfigDict(from_attributes=True)` where ORM objects are serialized directly.

### Case response

```json
{
  "id": 1,
  "case_number": "CASE-1001",
  "status": "OPEN",
  "ai_summary": null,
  "created_at": "2026-09-09T12:00:00Z",
  "updated_at": "2026-09-09T12:00:00Z"
}
```

### Redaction type response

```json
{
  "id": 1,
  "name": "PERSONAL_INFO"
}
```

### User response

```json
{
  "id": 1,
  "first_name": "Jordan",
  "last_name": "Lee"
}
```

### Redaction response

```json
{
  "id": 1,
  "source": "MANUAL",
  "redaction_text": "Maria Lopez",
  "starting_position": 16,
  "ending_position": 27,
  "created_at": "2026-09-09T12:00:00Z",
  "updated_at": "2026-09-09T12:00:00Z",
  "redaction_type": {
    "id": 1,
    "name": "PERSONAL_INFO"
  },
  "user": {
    "id": 1,
    "first_name": "Jordan",
    "last_name": "Lee"
  }
}
```

`ending_position` is a response-only value calculated as:

```python
starting_position + len(redaction_text)
```

Do not add it to the database.

### Activity response

```json
{
  "id": 1,
  "case_id": 1,
  "activity_uid": "ACT-1001-01",
  "activity_type": "Call - Inbound",
  "description": "Spoke with cust Maria Lopez re cust concerns...",
  "created_at": "2026-09-09T12:00:00Z",
  "redactions": []
}
```

The `redactions` array must contain the complete redaction responses described above. Return an empty array when an activity has no saved redactions.

## Endpoints

Place the routes in a dedicated router module consistent with the existing project structure and register the router with the FastAPI application.

### `GET /cases`

Return all cases as a JSON array of case responses.

- Order cases by `case_number` ascending so results are deterministic.
- Return HTTP 200 and an empty array when no cases exist.
- Do not include activities in this list response.

### `GET /cases/{case_id}`

Return one case response for the integer primary key.

- Return HTTP 200 when the case exists.
- Return HTTP 404 with a clear message when it does not exist.
- Return case metadata only; activities are retrieved through the activities endpoint.

### `GET /cases/{case_id}/activities`

Return all activities belonging to the requested case, including each activity's saved redactions, redaction type, and user.

- Return HTTP 404 when the case does not exist.
- Return HTTP 200 and an empty array when the case exists but has no activities.
- Order activities by `created_at` ascending and then `id` ascending.
- Order each activity's redactions by `starting_position` ascending and then `id` ascending.
- Preserve the original abbreviated activity description exactly as stored.

Load the required relationships eagerly to avoid issuing separate queries for every redaction's type or user. Follow SQLAlchemy 2.x query patterns and keep database access synchronous.

## Tests

Use a temporary test database and the existing callable seed function. Automated tests must not read from or modify the normal development database.

Add tests confirming:

1. `GET /cases` returns the seeded cases in the specified order.
2. `GET /cases` returns an empty array when the database contains no cases.
3. `GET /cases/{case_id}` returns the expected case.
4. A nonexistent case returns HTTP 404.
5. `GET /cases/{case_id}/activities` returns only activities belonging to that case.
6. Activities and redactions use the specified deterministic ordering.
7. Activities without redactions return `"redactions": []`.
8. Saved redactions include their type, user, source, text, and positions.
9. Every returned `ending_position` equals `starting_position + len(redaction_text)`.
10. Every returned redaction matches the corresponding slice of the unchanged activity description.

Keep tests focused on observable API behavior rather than private implementation details.

## Documentation and verification

Update the root `README.md` with the three endpoints and example commands.

Run from `backend/`:

```bash
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m uvicorn app.main:app --reload
```

Verify these requests through FastAPI's `/docs` page or another HTTP client:

```text
GET /cases
GET /cases/1
GET /cases/1/activities
GET /cases/999999
```

Use a real case ID returned by `GET /cases` in place of `1` if the seeded database assigned a different ID.

Confirm that all requests are read-only and that the database record counts remain unchanged. When finished, report the files changed, endpoint behavior, tests and commands run, and any deviations. Recommend—but do not implement—the next milestone.

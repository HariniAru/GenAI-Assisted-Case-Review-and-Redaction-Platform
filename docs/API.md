# Architecture and core API

The current application lives on `main`. [README](../README.md) is the source
for setup, database switching, and verification commands.

## Components to study

| Component | Responsibility |
| --- | --- |
| `backend/app/config.py`, `database.py` | Environment settings, engine, request sessions; `DATABASE_URL` chooses the database |
| `models.py`, `schemas.py`, `migrations/` | SQLAlchemy storage, Pydantic request/response contracts, Alembic schema changes |
| `case_router.py`, `redaction_router.py` | Core review reads, case status, reviewer-authored redactions |
| `redaction_validation.py` | Shared exact-span rule for manual redactions and AI proposals |
| `reference_corpus.py`, `reference_embeddings.py`, `reference_service.py` | Parse reference material, embed locally, ingest/retrieve using pgvector |
| `ai_service.py`, `ai_grounding.py`, `recommendation_service.py` | Provider calls, policy evidence, shared grounded proposal validation |
| `ai_router.py`, `analysis_router.py`, `case_analysis.py` | Per-activity recommendations, parallel case analysis, independent explicit approval |
| `observability.py`, `studio.py`, `langgraph.json` | Opt-in tracing and optional local Studio entry point |
| `frontend/src/App.tsx`, `ActivityCard.tsx` | Case navigation, unsaved drafts, independent reviewer actions |
| `api.ts`, `types.ts`, `selection.ts`, `redactions.ts` | Typed HTTP client, response types, Unicode selection and overlap rendering |

Routers handle HTTP, services implement model/retrieval logic, and LangGraph
coordinates independent branches. The graph calls services rather than the
application's own HTTP endpoints. Keep these boundaries when studying the code.

## Core endpoints (both databases)

| Method and path | Behavior |
| --- | --- |
| `GET /health` | Process health |
| `GET /cases`, `GET /cases/{id}` | Cases with saved summaries; does not generate AI output |
| `GET /cases/{id}/activities` | Original notes with saved redactions and reviewer metadata |
| `POST /cases/{id}/close`, `POST /cases/{id}/reopen` | Reviewer-controlled case status |
| `GET /redaction-types` | Active types |
| `POST /activities/{id}/redactions` | Create a validated manual redaction |
| `PATCH /redactions/{id}` | Update a manual redaction's type, text, or position |
| `DELETE /redactions/{id}` | Delete either a manual or previously accepted AI redaction |
| `POST /cases/{id}/summary/approve` | Save only the reviewed summary, checking the expected saved value |

The React UI exposes manual selection/create/delete; manual updates are available
through the API. Closed cases reject mutations. Open cases display `IN_PROGRESS`
when they have saved redactions and `OPEN` otherwise; closed status is preserved.
Reading case status does not commit changes. Records use the configured demo
reviewer, not authentication.

A manual create body contains `redaction_type_id`, `redaction_text`, and
`starting_position`. Positions count Unicode code points from zero; the stored
substring must match the original activity exactly. End position is computed as
`start + len(text)` and is not stored. Invalid spans/types return 422, missing
records 404, and duplicate creates or closed-case mutations 409. Overlapping
spans remain distinct; rendering splits boundaries without changing source text.
AI redactions cannot be edited via PATCH but can be deleted.

## PostgreSQL-dependent AI flow

See [grounded recommendations](GROUNDED_AI_SETUP.md) for generation/acceptance and
[case analysis](CASE_ANALYSIS.md) for the graph and summary approval payloads.
Reference ingestion/search and normal live analysis require PostgreSQL/pgvector.
Missing retrieval produces an error, never an ungrounded model fallback.
The legacy automatic summary endpoint returns 410; clients use Analyze case
followed by explicit approval instead.

## Data and limits

`seed.py` contains synthetic notes and initial reviewed spans. It preserves exact
source text, checks offsets, and prevents duplicate records; use it only for an
initial database setup because it also adjusts seeded case statuses. No cleanup
or normal database-mode switch requires reseeding or dropping tables.

There is no production authentication, persistent approval queue, or held-out
model-quality evaluation. Model instructions and structural validation do not
prove a recommendation or summary is correct; the reviewer remains responsible.

# Grounded AI recommendation setup and API

`Generate AI recommendations` now retrieves rules before calling the existing
Hugging Face/Qwen provider. It reuses `ReferenceRetriever` and the existing
`reference_chunks` table; there is no second index, new migration, new dependency,
or change to case summary generation. Manual redactions are unchanged.

## Run

From the repository root, ensure PostgreSQL is running:

```bash
docker compose --env-file backend/.env.postgres up -d --wait
cd backend
uv sync --locked --extra dev
uv run --env-file .env.postgres alembic upgrade head
uv run --env-file .env.postgres python -m app.ingest_references
uv run --env-file .env.postgres uvicorn app.main:app --reload
```

Keep the existing `HF_TOKEN`, `HF_MODEL`, and `HF_PROVIDER` configuration in your
ignored local environment files. Recommendation generation requires both an
initialized local index/model and the existing Hugging Face provider. Do not
reseed existing review records. Re-ingest after corpus changes. Then start the
frontend with `npm run dev` from `frontend/` and open a case.

## Generation and evidence

`POST /activities/{activity_id}/ai-recommendations`:

1. Reject an unknown activity (404) or closed case (409).
2. Query the existing retriever with the current database description. Disable
   LangSmith tracing as with the inspection endpoint.
3. Include all six mandatory policy sections, matched glossary entries, and up
   to three returned examples. Remove any example whose `activity_uid` equals
   the current activity. The inspection endpoint itself remains unchanged.
4. Build bounded context: at most 16,000 characters for reference JSON records;
   current description at most 12,000 characters; model output at most 2,048
   tokens. Never truncate the source description or mandatory rules. Reject an
   oversized description (422) or mandatory rules (503); omit optional whole
   glossary/example blocks that do not fit. There may be fewer examples after
   same-activity filtering. No token-budget precision or exhaustive retrieval
   is claimed by these character limits.
5. Send the current description as the user message, clearly identifying it as
   the only source of output text and offsets. The system prompt makes policy
   override examples and permits no suggestions when nothing is supported.
6. Keep structured model output limited to label, text, position, and reason.
   Reject invented extra fields, including model-authored evidence. Validate
   known/active labels, exact substrings, positions, and duplicates. Preserve
   the pre-existing unique-match position correction: a wrong model offset can
   be corrected only when its exact text occurs once; ambiguous mismatches are
   discarded. Do not write any redaction during generation.
7. Attach server-selected `supporting_policy` from the mandatory policy chunk
   corresponding to the accepted label. Verify its ID, source, kind, and section.
   Examples never serve as the sole authority.

Each item in `recommendations` now has:

```text
redaction_type
redaction_text
starting_position
reason
supporting_policy:
  chunk_id        stable corpus/section ID
  content_sha256  fingerprint of the full current policy chunk
  section         e.g. "1. PERSONAL_INFO"
  excerpt         up to 360 characters copied from the policy body
```

For example, a synthetic proposal for `Omar Reed` displays:

> Supporting rule: 1. PERSONAL_INFO
>
> Protect a customer's full name, telephone number, account number, and street mailing address.

The UI displays the returned excerpt (which may include additional sentences),
its section, and a reminder that this is draft synthetic policy. It keeps Accept
and Reject explicit. Reject removes only client state; it makes no mutation
request. Generation errors clear stale pending suggestions and show the safe
server message. React renders rule/reason strings as text, not HTML.

Retrieval/index/model failures produce a clear **503** and never call the model
with an ungrounded prompt. Provider or invalid structured-response failures
produce **502**. Internal exceptions and credentials are not exposed.

## Acceptance

`POST /activities/{activity_id}/ai-recommendations/accept` receives the full
returned suggestion including `supporting_policy`. Old clients without evidence
must regenerate using the updated frontend. Acceptance:

- Reloads and locks the activity row, checks the case is open, and verifies the
  current substring and supplied offset exactly. Unlike generation, it does
  not repair client offsets.
- Resolves the active label and configured reviewer on the server.
- Reloads the current indexed policy for that label, recomputes its excerpt and
  full-content hash, and compares every supplied evidence field. Invented,
  mismatched, or stale evidence returns 422 and asks for regeneration; an
  unavailable policy returns 503. The fingerprint catches changes beyond the
  short excerpt, even when the stable section ID is unchanged.
- Rejects an already-saved identical text/position for the activity with 409.
  The activity lock serializes concurrent AI accept requests.
- Saves the validated span with `source=AI`. The reason is advisory, never used
  as authority or saved. Neither reason nor evidence is persisted in the existing
  redaction schema. The frontend refreshes saved redactions on success.

This does not prove that a model's chosen label is semantically correct or that
an arbitrary client submitted a suggestion actually generated earlier. A valid
policy citation establishes which label rule is being shown, not proof that the
rule applies. Reviewer verification remains necessary. Authentication and
persisted evidence provenance are outside this milestone.

## Verification

Commands from `backend/` (the implementation environment used
`UV_CACHE_DIR=/tmp/case-review-uv-cache` to place uv's cache in an allowed directory):

```bash
uv run ruff format .
uv run ruff check .
uv run --env-file .env.postgres pytest -q
uv run pytest -q
```

Commands from `frontend/`:

```bash
npm run lint
npm test -- --run
npm run build
```

Tests use isolated migrated databases and fake retrieval/model responses, plus
one integration through the actual `ReferenceRetriever` and pgvector index with
fake local vectors. They cover policy context, exclusion of same-activity
examples, real policy IDs, limits, invalid output fields/types/spans, duplicate
filtering/acceptance, closed cases, no writes before acceptance, and revalidation
against edited activity/policy content. The existing summary and manual-redaction
tests remain in place. Frontend interaction tests cover rule display, explicit
acceptance, local rejection, retrieval/acceptance errors, and manual selection/save.

No paid model calls or development review-record changes are required by these
tests. Live Qwen output quality is not verified by fake-model tests. Manual
browser inspection could not be completed: native computer-use permission was
not granted and no browser connection was available. To finish it locally, open
an unclosed case, generate suggestions, inspect the rule, reject one, accept one,
and refresh to confirm only the accepted span persists.

Completed checks for this milestone:

- PostgreSQL: **27 passed**.
- SQLite regression run: **23 passed, 4 skipped** (PostgreSQL-only checks).
- Backend Ruff formatting/lint: passed.
- Frontend ESLint: passed; Vitest: **5 passed**; TypeScript/Vite build: passed.
- The initial frontend build exposed missing Vitest matcher types; switching
  the existing setup import to `@testing-library/jest-dom/vitest` fixed it.
- No live Hugging Face/Qwen call was made. Manual browser inspection remained
  blocked by computer-use permissions, as described above.

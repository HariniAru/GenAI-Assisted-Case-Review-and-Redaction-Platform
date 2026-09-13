# Manual Redaction Workflow

## Goal

Allow a reviewer to select text within an activity, choose a redaction type, and create, update, or delete saved manual redactions. Keep the workflow cohesive with the existing FastAPI API and React case-detail page.

Complete only the work described here. If anything else is necessary, explain why and ask before proceeding.

## Workflow

### Create

1. The reviewer selects text inside one activity description.
2. The frontend calculates the selection's code-point start position.
3. The reviewer chooses an active redaction type.
4. The frontend sends the activity ID, selected text, start position, and type.
5. The backend validates the selection against the immutable activity description.
6. The backend saves the redaction with `source = MANUAL` and the configured demo reviewer.
7. The frontend refreshes the activity data and displays the saved mark.

### Update

The reviewer can change a manual redaction's type or replace its selected text with a new selection from the same activity. The activity, source, and reviewer cannot be changed.

### Delete

The reviewer confirms deletion, the backend deletes the manual redaction, and the frontend refreshes the activity data.

AI-sourced redactions remain visible but read-only in this milestone. They represent accepted AI-originated recommendations and should not silently become manual redactions.

## Demo reviewer

Authentication has not been added yet, but every redaction requires a user. Add this setting to the backend configuration and `.env.example`:

```text
DEMO_REVIEWER_EMAIL=jordan.lee@example.com
```

Resolve the user by this email on the backend when creating a manual redaction. Do not accept `user_id` from the frontend. Return a clear server-configuration error if the configured user does not exist.

This is a temporary development identity boundary, not an authentication system.

## Backend API

Follow the existing router, schema, session, error, and response conventions.

Use Pydantic request schemas with `ConfigDict(extra="forbid")` so fields such as `source`, `user_id`, `activity_id`, and `ending_position` cannot be silently accepted. Require at least one editable field in the PATCH schema.

### List active redaction types

```http
GET /redaction-types
```

Return HTTP 200 with all redaction types whose `deleted_at` is null, ordered by `name` ascending:

```json
[
  {
    "id": 1,
    "name": "CONFIDENTIAL"
  }
]
```

### Create a manual redaction

```http
POST /activities/{activity_id}/redactions
```

Request:

```json
{
  "redaction_type_id": 1,
  "redaction_text": "Maria Lopez",
  "starting_position": 16
}
```

Return HTTP 201 with the existing complete redaction response, including its type, user, `source`, and calculated `ending_position`.

The backend—not the request—sets:

```text
source = MANUAL
user = configured demo reviewer
activity = activity identified by the URL
```

### Update a manual redaction

```http
PATCH /redactions/{redaction_id}
```

Allow these optional fields:

```json
{
  "redaction_type_id": 2,
  "redaction_text": "(555) 014-7821",
  "starting_position": 63
}
```

At least one field must be present. Validate the complete resulting redaction even when only one field changes. Return HTTP 200 with the updated complete redaction response.

Do not allow this endpoint to change `activity_id`, `source`, or `user_id`. Return HTTP 409 if the existing redaction's source is not `MANUAL`.

### Delete a manual redaction

```http
DELETE /redactions/{redaction_id}
```

Return HTTP 204 with no response body. Return HTTP 409 if the redaction's source is not `MANUAL`.

The current `redactions` table has no soft-delete field, so this endpoint permanently deletes the selected manual redaction row.

## Backend validation

Use a shared service or helper so create and update apply the same rules.

For the final proposed values:

1. Confirm that the activity exists.
2. Confirm that the redaction type exists and `deleted_at` is null.
3. Reject empty or whitespace-only `redaction_text`.
4. Require `starting_position >= 0`.
5. Calculate `ending_position = starting_position + len(redaction_text)`.
6. Require `ending_position <= len(activity.description)`.
7. Require:

```python
activity.description[starting_position:ending_position] == redaction_text
```

Return HTTP 422 with a clear, non-sensitive message when the supplied text and positions do not match.

Permit adjacent, nested, and overlapping redactions. Reject an exact duplicate for the same activity, type, text, and position with HTTP 409. Do not change the database schema solely to detect duplicates in this milestone.

Use one transaction per mutation. Roll back on failure. Do not change the immutable activity description.

## Frontend API client

Extend the existing typed API module with functions for:

```text
GET    /redaction-types
POST   /activities/{activity_id}/redactions
PATCH  /redactions/{redaction_id}
DELETE /redactions/{redaction_id}
```

Add TypeScript request types containing only the client-editable fields. Reuse the existing response types and error handling.

After a successful create, update, or delete, retrieve the case's activities again so the screen reflects the server's authoritative state. Disable relevant controls while a request is pending and show a useful inline error if it fails.

## Text selection

Add a `Redact selected text` action to every activity card.

The description container must contain only the rendered source text segments so its DOM text content exactly matches `activity.description`. Do not use `contentEditable` or `dangerouslySetInnerHTML`.

When the action is used:

1. Read the browser selection with `window.getSelection()`.
2. Confirm that the selection starts and ends inside one activity description container.
3. Reject an empty or whitespace-only selection.
4. Calculate the selected text and start position relative to that activity's full description.
5. Count positions as Unicode code points with `Array.from(...)` so they match the Python API offsets.
6. Verify locally that the calculated slice equals the selected text.
7. Preserve the selection exactly; do not trim, normalize, expand abbreviations, or alter whitespace.

The selection logic must work when a selection begins or ends inside an existing `<mark>` and when it spans multiple rendered segments.

Keep DOM-range calculations in focused helper functions so they can be tested separately from the page.

## Create and edit interface

Use a compact form displayed within the relevant activity card rather than adding a modal or context menu.

### Create form

Display:

- The selected text as read-only content
- A dropdown populated by `GET /redaction-types`
- Save and Cancel buttons

Disable Save until the selection and type are valid.

### Edit form

Show an Edit button only for `MANUAL` redactions in the existing redaction list. The form should:

- Start with the current type and text selection.
- Allow the type to be changed.
- Provide a `Use current text selection` action to replace the text and position from a new selection within the same activity.
- Provide Save and Cancel buttons.

Only one create or edit form needs to be active at a time.

### Delete action

Show a Delete button only for `MANUAL` redactions. Require confirmation before sending the request. Keep AI-sourced redactions visible without edit or delete controls.

Use clear success or error feedback. Avoid optimistic updates; refresh from the API after successful mutations.

## Accessibility and presentation

- Use native labels, selects, buttons, and keyboard-focus styles.
- Associate error messages with their forms.
- Ensure selection and mutation actions are usable by keyboard where browser text selection permits.
- Do not rely on redaction color alone; retain the visible metadata list and accessible mark labels.
- Preserve the original abbreviated call-center text exactly.
- Reuse the existing minimal visual system and redaction-type configuration.

## Backend tests

Use the temporary test database and existing seed utilities. Test at least:

1. Active redaction types are returned in deterministic order.
2. A valid request creates a redaction with `source = MANUAL` and the configured reviewer.
3. The client cannot supply or override the source or reviewer.
4. Empty text, negative positions, out-of-bounds positions, and mismatched text are rejected.
5. A missing activity or redaction returns HTTP 404.
6. A missing or retired redaction type is rejected.
7. An exact duplicate returns HTTP 409.
8. Overlapping redactions are allowed.
9. A manual redaction's type and selected span can be updated.
10. Activity, source, and reviewer cannot be changed through update.
11. AI-sourced redactions cannot be updated or deleted through this workflow.
12. Deleting a manual redaction returns HTTP 204 and removes it.
13. A failed mutation leaves the database unchanged.

## Frontend tests

Mock the API and test at least:

1. Selecting valid text opens the create form with the exact text.
2. A selection outside the activity or across activities is rejected.
3. Code-point offsets remain correct when non-ASCII characters occur before the selection.
4. Selection works across normal and marked text segments.
5. Active redaction types populate the dropdown.
6. Saving sends only type, text, and starting position.
7. A successful create refreshes and displays the saved redaction.
8. Manual redactions expose Edit and Delete controls; AI redactions do not.
9. Editing the type or replacing the selection sends the correct patch.
10. Deletion requires confirmation and refreshes the activity list.
11. Pending controls are disabled and API errors are displayed.
12. Canceling leaves the saved data unchanged.

## Documentation and verification

Update the root `README.md` with the new endpoints and a short explanation of the temporary demo reviewer.

Run backend checks from `backend/`:

```bash
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m uvicorn app.main:app --reload
```

Run frontend checks from `frontend/`:

```bash
npm run lint
npm test -- --run
npm run build
npm run dev
```

Manually verify:

1. Select text in one activity and save it with each redaction type.
2. Refresh the page and confirm the redactions remain.
3. Change a manual redaction's type.
4. Replace a manual redaction's selected text within the same activity.
5. Create an overlapping manual redaction and confirm both render correctly.
6. Delete a manual redaction and confirm it stays deleted after refresh.
7. Confirm AI-sourced redactions remain visible and read-only.
8. Confirm invalid selections never create or change a database row.

When finished, report the files and dependencies changed, endpoint behavior, validation decisions, tests and commands run, and any deviations. Recommend—but do not implement—the next milestone.

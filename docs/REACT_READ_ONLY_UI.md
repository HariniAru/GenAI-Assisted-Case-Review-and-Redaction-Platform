# Initial React Case Review Interface

## Goal

Build a minimal read-only React interface that lets a reviewer browse cases, open a case, read its automotive call-center activities, and see existing redactions marked in the original text.

Complete only the work described here. If anything else is necessary, explain why and ask before proceeding.

## Frontend setup

- Initialize the existing `frontend/` directory as a Vite application using React and TypeScript.
- Use the current Node.js LTS release and npm.
- Remove the placeholder `.gitkeep` when the application files are created.
- Use React Router for client-side routing.
- Use the browser `fetch` API for HTTP requests; do not add a server-state library yet.
- Use plain CSS or CSS modules; do not add a component library.
- Add Vitest, React Testing Library, `jest-dom`, and jsdom for tests.
- Keep TypeScript strict and do not use `any`.

Configure the Vite development server to proxy relative `/cases` requests to `http://127.0.0.1:8000`. The frontend should call relative API paths so local development does not require backend CORS changes.

Add `frontend/.env.example` with an optional deployment-time API base URL:

```text
VITE_API_BASE_URL=
```

The local default should remain empty and use the Vite proxy.

## Routes and pages

### `/`

Redirect to `/cases`.

### `/cases`

Create a case-list page that calls:

```http
GET /cases
```

Display a simple table with:

- Case number
- Status
- AI summary, or `Not generated` when it is null
- A link or button to open the case

Show clear loading, error, and empty states. Keep the table readable on a narrow screen.

### `/cases/:caseId`

Create a case-detail page that calls:

```http
GET /cases/{case_id}
GET /cases/{case_id}/activities
```

Display:

- A link back to the case list
- Case number
- Status
- AI summary, or `Not generated`
- The case's activities in chronological order

For each activity, display:

- Activity type
- Activity UID
- Created date and time
- Original activity description
- Existing redactions visually marked in the description

Handle loading, API errors, a missing case, and a case with no activities. A backend HTTP 404 should produce a useful not-found message rather than a generic failure.

## API client and TypeScript types

Create a small API module that:

- Reads `VITE_API_BASE_URL`, defaulting to an empty string.
- Calls the three existing endpoints.
- Checks `response.ok` before parsing successful data.
- Distinguishes a 404 response from other request failures.
- Returns typed values.

Define TypeScript types matching the API contract:

```typescript
type CaseStatus = "OPEN" | "IN_PROGRESS" | "CLOSED";
type RedactionSource = "AI" | "MANUAL";

interface Case {
  id: number;
  case_number: string;
  status: CaseStatus;
  ai_summary: string | null;
  created_at: string;
  updated_at: string;
}

interface RedactionType {
  id: number;
  name: string;
}

interface UserSummary {
  id: number;
  first_name: string;
  last_name: string;
}

interface Redaction {
  id: number;
  source: RedactionSource;
  redaction_text: string;
  starting_position: number;
  ending_position: number;
  created_at: string;
  updated_at: string;
  redaction_type: RedactionType;
  user: UserSummary;
}

interface Activity {
  id: number;
  case_id: number;
  activity_uid: string;
  activity_type: string;
  description: string;
  created_at: string;
  redactions: Redaction[];
}
```

Keep these API types separate from presentation components.

## Redaction presentation configuration

Create a frontend configuration file for redaction labels and colors rather than storing UI colors in the database. Configure:

| Type | Display label | Suggested background | Suggested border |
| --- | --- | --- | --- |
| `PERSONAL_INFO` | Personal information | `#dbeafe` | `#2563eb` |
| `CONFIDENTIAL` | Confidential | `#fef3c7` | `#d97706` |
| `PRIVILEGED` | Privileged | `#fce7f3` | `#db2777` |
| `HIGHLIGHT` | Highlight | `#dcfce7` | `#16a34a` |

Provide a neutral fallback style and the raw type name for an unknown redaction type so future database configuration does not break the UI.

Display a small legend on the case-detail page. Do not rely on color alone: marked text must also expose its redaction type through visible supporting details and an accessible label or tooltip.

## Rendering redacted text

Create a reusable, pure text-segmentation helper and a presentation component. Do not modify the activity description and do not render it with `dangerouslySetInnerHTML`.

The helper must:

1. Validate each redaction range against the description.
2. Confirm that the specified slice equals `redaction_text`.
3. Split the original description into ordered, nonduplicated text segments.
4. Identify which redactions apply to every segment.
5. Preserve all original characters and whitespace.
6. Handle adjacent, nested, and overlapping redactions without losing or repeating text.
7. Ignore an invalid range for highlighting while keeping the full description visible and reporting a non-sensitive diagnostic to the console.

Python offsets count Unicode code points, while JavaScript strings normally use UTF-16 code units. Use a code-point-safe representation such as `Array.from(description)` when applying API positions so non-ASCII text does not shift redaction boundaries.

Render unredacted segments as normal text and redacted segments with semantic `<mark>` elements. For a segment covered by multiple redactions, show a distinct overlap treatment and list all applicable types in its tooltip or accessible label.

Under each activity, show a compact list of saved redactions with:

- Type
- Source
- Reviewer name
- Redacted text

This supporting list makes the meaning available without relying only on highlight colors.

## Minimal visual design

- Use a centered content area with a readable maximum width.
- Use semantic headings, a semantic table, buttons or links, and visible keyboard focus styles.
- Use simple cards for activities.
- Use status badges for `OPEN`, `IN_PROGRESS`, and `CLOSED`.
- Preserve activity whitespace with CSS such as `white-space: pre-wrap`.
- Format timestamps with `Intl.DateTimeFormat` rather than displaying raw values.
- Keep colors, spacing, and typography restrained and consistent.
- Make the case list and detail page usable on desktop and mobile widths.

## Tests

Mock API requests; frontend tests must not depend on a running backend or development database.

Add tests confirming:

1. The case-list page renders returned cases and links to their detail pages.
2. Loading, empty, and error states render correctly.
3. The case-detail page renders case metadata and activities.
4. A 404 produces the not-found state.
5. A null AI summary displays `Not generated`.
6. Activities without redactions display the original description unchanged.
7. Redaction marks use the API positions and preserve the complete original description.
8. Redaction metadata includes type, source, and reviewer.
9. Adjacent, nested, and overlapping redactions render without lost or duplicated text.
10. An invalid range leaves the original text visible.
11. A non-ASCII character before a redaction does not shift the highlighted text.
12. An unknown redaction type uses the fallback presentation.

Keep segmentation logic in a pure function so its boundary cases can be unit tested directly.

## Documentation and verification

Update the root `README.md` with frontend installation and startup instructions.

Expected local workflow:

Terminal 1, from `backend/`:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m uvicorn app.main:app --reload
```

Terminal 2, from `frontend/`:

```bash
npm install
npm run dev
```

Run frontend verification from `frontend/`:

```bash
npm run lint
npm test -- --run
npm run build
```

Manually verify:

1. `/cases` displays the seeded cases.
2. Opening a case displays its metadata and activities.
3. The abbreviated notes remain unchanged.
4. Existing redactions are marked at the correct positions.
5. Refreshing either page works.
6. Browser developer tools show no unexpected errors.

When finished, report the files and dependencies added, page behavior, tests and commands run, and any deviations. Recommend—but do not implement—the next milestone.

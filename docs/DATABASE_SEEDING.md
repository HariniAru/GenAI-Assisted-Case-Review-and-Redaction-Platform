# Database Seeding

> Historical SQLite milestone. For the PostgreSQL branch, use [the current setup](../README.md) and [migration notes](POSTGRES_MIGRATION.md). Existing application behavior is preserved.

## Goal

Add deterministic synthetic data to the existing SQLite database so the models, relationships, constraints, and future review interface can be tested.

The activity descriptions represent notes written by automotive customer-service representatives during or shortly after conversations with customers. These are operational case notes rather than polished transcripts, so they should realistically include shorthand, abbreviations, sentence fragments, and concise phrasing.

Preserve each description exactly as written. The later RAG workflow can retrieve an abbreviation glossary to help the model interpret the notes, but seeding must not expand or rewrite the stored text because redaction positions refer to the original characters.

Complete only the work described here. If anything else is necessary, explain why and ask before proceeding.

## Implementation

Create `backend/app/seed.py` with an idempotent seed function and command-line entry point.

Run it from `backend/` with:

```bash
.venv/bin/python -m app.seed
```

The command must:

- Use the existing settings, SQLAlchemy engine, session factory, and models.
- Assume Alembic migrations have already been applied.
- Insert the records below in one transaction.
- Roll back and return a clear error if seeding fails.
- Print a short summary of the resulting record counts.
- Produce the same database state when run repeatedly without creating duplicates.

Do not add dependencies or create a new migration for this milestone.

## Required seed data

All people, companies, accounts, and events below are fictional. Do not copy real customer records or use real automotive-company names. Keep the notes valid UTF-8; emulate call-center shorthand without intentionally adding corrupted characters.

### Abbreviations used in the notes

These definitions document the intended meaning of the synthetic data. They will later be included in the RAG knowledge document; do not implement retrieval or text normalization in this milestone.

| Abbreviation | Meaning |
| --- | --- |
| `cust` | customer |
| `adv` | advised |
| `veh` | vehicle |
| `sts` | states |
| `sks` | asks or requests |
| `re` | regarding |
| `acct` | account |
| `recs` | records |
| `req` | request |
| `docs` | documents |
| `c/b` | callback |
| `mgr` | manager |
| `dept` | department |
| `asst` | assistance |
| `clld` | called |
| `LM` | left message |
| `Co` | company |

### User

| Field | Value |
| --- | --- |
| `first_name` | `Jordan` |
| `last_name` | `Lee` |
| `email` | `jordan.lee@example.com` |

Use the unique email to find or create the user.

### Redaction types

Create these four types:

```text
PERSONAL_INFO
CONFIDENTIAL
PRIVILEGED
HIGHLIGHT
```

Use each unique name to find or create its record. Leave `deleted_at` null.

### Cases

| Case number | Status | Summary |
| --- | --- | --- |
| `CASE-1001` | `OPEN` | null |
| `CASE-1002` | `IN_PROGRESS` | null |
| `CASE-1003` | `CLOSED` | null |

Use `case_number` to find or create each case. Keep `ai_summary` null because summary generation has not been implemented.

### Activities

Use `activity_uid` to find or create each activity.

#### `ACT-1001-01`

- Case: `CASE-1001`
- Type: `Call - Inbound`
- Description:

```text
Spoke with cust Maria Lopez re cust concerns. Cust called from (555) 014-7821 re acct 884129. Cust sts her father had the veh in drive and the veh accelerated unexpectedly before striking a garage wall. Internal recs indicate maximum settlement authorization is $4,000. Co counsel adv team not to admit liability until investigation is complete. Cust sks c/b from case mgr.
```

#### `ACT-1001-02`

- Case: `CASE-1001`
- Type: `Internal Note`
- Description:

```text
Outbound c/b to cust. Adv cust to submit repair docs and written req to Northstar Claims Dept. Cust thanked and requires no further asst.
```

#### `ACT-1002-01`

- Case: `CASE-1002`
- Type: `Call - Outbound`
- Description:

```text
Clld cust Daniel Kim at (555) 011-2234 re acct 771205. Unable to reach cust. LM requesting c/b re veh inspection.
```

#### `ACT-1002-02`

- Case: `CASE-1002`
- Type: `Internal Note`
- Description:

```text
Reviewed internal pricing recs. Possible goodwill reimbursement limit is $1,500 pending mgr review. Do not disclose internal limit to cust.
```

#### `ACT-1003-01`

- Case: `CASE-1003`
- Type: `Close`
- Description:

```text
5 Point Close. Summary: Cust sts veh stalled after service. Action Taken: Adv cust inspection completed. Resolution: Cust notified of final decision. Cust satisfied: yes. No further asst.
```

## Saved redactions

Seed the following redactions for `ACT-1001-01`. These represent historical redactions already committed by the seeded reviewer. An `AI` source means the reviewer accepted an AI recommendation; it is not a pending recommendation.

| Redaction text | Type | Source |
| --- | --- | --- |
| `Maria Lopez` | `PERSONAL_INFO` | `AI` |
| `(555) 014-7821` | `PERSONAL_INFO` | `MANUAL` |
| `884129` | `PERSONAL_INFO` | `AI` |
| `maximum settlement authorization is $4,000` | `CONFIDENTIAL` | `MANUAL` |
| `Co counsel adv team not to admit liability until investigation is complete.` | `PRIVILEGED` | `AI` |
| `veh accelerated unexpectedly` | `HIGHLIGHT` | `MANUAL` |

For every redaction:

1. Calculate `starting_position` from the activity description rather than hard-coding it.
2. Fail clearly if the target text is missing or occurs more than once.
3. Verify before insertion that:

```python
end_position = starting_position + len(redaction_text)
activity.description[starting_position:end_position] == redaction_text
```

Since `redactions` has no natural unique key, detect an existing seed redaction using its activity, redaction type, user, source, text, and starting position before inserting it.

## Tests

Keep the seeding logic callable with a supplied SQLAlchemy session so it can be tested against a temporary database.

Add tests confirming:

1. The expected user, four redaction types, three cases, five activities, and six redactions are created.
2. Running the seed function twice does not change those counts.
3. Every activity belongs to the correct case.
4. Every redaction belongs to the correct activity, type, and user.
5. Every redaction's stored text matches the activity slice at its stored starting position.
6. All three case statuses, all four redaction types, and both redaction sources are represented.
7. Seeded activity descriptions remain exactly equal to the specified abbreviated source notes.

Use the project's existing test setup and do not modify the developer's normal local database during automated tests.

## Verification

Run from `backend/`:

```bash
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m app.seed
```

After the second seed run, confirm these totals:

```text
users: 1
redaction_types: 4
cases: 3
activities: 5
redactions: 6
```

Update the root `README.md` with the seed command. When finished, report the files changed, tests and commands run, resulting counts, and any deviations. Recommend—but do not implement—the next milestone.

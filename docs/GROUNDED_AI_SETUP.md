# Grounded recommendations

The existing Hugging Face/Qwen provider uses policy and examples from the single
PostgreSQL reference index. See [README](../README.md) for configuration and
[reference retrieval](REFERENCE_RETRIEVAL.md) for ingestion. There is no second
index or ungrounded fallback. Manual redactions are independent of retrieval.

## Generate without saving

`POST /activities/{activity_id}/ai-recommendations`:

1. Checks the activity exists, the case is open, and the input fits its limit.
2. Retrieves all six mandatory policy sections, matched glossary terms, and
   nearby examples. Removes the current activity's own labeled example from
   generation context. Examples provide interpretation, never proposed source text.
3. Calls the configured Qwen provider with bounded reference context and the
   original activity description as the only source of spans and offsets.
4. Corrects an offset only when the proposed exact text has one unique match.
   Validates allowed types, exact substrings, duplicates, and supporting policy.
5. Returns valid drafts, each with `redaction_type`, `redaction_text`,
   `starting_position`, `reason`, and `supporting_policy` (chunk ID, content hash,
   section, excerpt). No case or redaction is saved.

The shared `recommendation_service.py` serves both this endpoint and the
[LangGraph redaction branch](CASE_ANALYSIS.md). Retrieval inherits the caller's
tracing context. The separate inspection endpoint explicitly disables tracing.
Input is limited to 12,000 characters; grounding context to 16,000 characters.
Unknown activity returns 404, closed case 409, oversized input 422, unavailable
retrieval 503, and provider failure 502. Zero valid proposals is a successful
empty list. Model confidence is not used as approval authority.

## Accept or reject independently

`POST /activities/{activity_id}/ai-recommendations/accept` accepts one complete
returned recommendation. The server locks the activity, rechecks case status,
active type, exact current span, and duplicates. It resolves current policy from
the reference table and compares the supplied ID/hash/section/excerpt against it.
Changed or fabricated evidence returns 422; missing indexed policy returns 503.
A duplicate saved span returns 409. The reason is advisory and is never authority
for acceptance or persisted as a reviewer decision.

Successful acceptance saves one `Redaction` with `source=AI` and the configured
demo reviewer, returning 201. The original description is unchanged. Rejection
only removes the draft from React state. Summary approval never accepts a
redaction, and redaction approval never saves the summary.

SQLite can display/delete existing AI redactions, but normal SQLite setup has no
indexed policy or live retrieval. Do not interpret fake-retriever tests on SQLite
as support for live grounded generation. New grounded workflows use PostgreSQL.

## Verification and limits

[Backend and frontend tests](../README.md#verification) cover no-write generation,
exact offsets, duplicate and invalid spans, type/policy checks, tampered evidence,
changed source/policy, errors, and explicit UI acceptance/rejection. Test models
and retrievers are fake and send no text to external services.

A supporting rule is evidence for the reviewer, not proof of semantic correctness.
A model can select an overly broad span or apply a rule incorrectly. Retrieval
examples are synthetic and some overlap with seed cases; they are not a held-out
evaluation. Use the original note, policy, and judgment before saving any result.

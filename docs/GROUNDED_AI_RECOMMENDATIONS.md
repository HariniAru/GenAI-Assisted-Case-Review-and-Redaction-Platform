# Milestone: Ground AI redaction suggestions in retrieved rules

Work on `postgres-migration`. Read `AGENTS.md`, `docs/REFERENCE_RETRIEVAL.md`, `docs/rag_reference_corpus.md`, and the existing AI/retrieval endpoints and `ActivityCard` before editing. Retrieval already exists through `ReferenceRetriever` and `GET /activities/{activity_id}/references`; reuse it. Do not build a second index.

## Goal

When a reviewer clicks **Generate AI recommendations**, retrieve relevant reference material, generate suggestions using that material, and show the supporting **policy rule** with each suggestion. Keep suggestions advisory until the reviewer accepts them.

## Implement

1. In `POST /activities/{activity_id}/ai-recommendations`, invoke the existing retriever for the activity description. Supply the mandatory policy sections, matching glossary terms, and a few relevant examples to the existing Hugging Face/Qwen provider. Exclude examples whose `activity_uid` equals the current activity's UID from the generation prompt to avoid handing the model that activity's labeled answer. The **current database description** remains the only source for suggested text and character offsets. Keep prompts bounded and make the policy take precedence over examples.
2. Preserve structured output and the existing server-side exact-substring, position, type, duplicate, and closed-case checks. Extend the recommendation response with a stable supporting policy reference (chunk ID and section, plus a short excerpt) chosen/verified by the server for the suggested label. Do not accept invented references or use an example as the sole authority. If retrieval is unavailable, return a clear error; do not silently generate ungrounded suggestions.
3. In `ActivityCard`, show the supporting rule next to each proposed span and reason. Keep **Accept** and **Reject** explicit. Generating or rejecting must not save a redaction. Accept must revalidate the proposed span against the current activity before saving with `source=AI`; do not trust a client-supplied reason, offset, or evidence reference without server checks. Preserve the manual redaction flow.

## Verify

- Add focused backend tests with fake retriever/model: relevant policy appears in the model context; the same-activity example is excluded; valid suggestions carry a real policy reference; invented/invalid offsets, unsupported types, duplicates, and closed cases are handled; no recommendation is saved before acceptance; acceptance still validates against current text.
- Add a focused frontend interaction test showing the rule, Accept/Reject behavior, and a useful retrieval-error state. Run backend tests on PostgreSQL and frontend lint, tests, and build. Manually inspect one case in the browser if available.
- Update the API/setup notes and report commands, results, a sample rule shown with a suggestion, and limitations. Do not add LangGraph, change case summaries, add travel data, or merge into `main` in this milestone.

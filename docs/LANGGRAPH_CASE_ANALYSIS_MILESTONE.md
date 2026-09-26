# Milestone: Parallel case analysis with LangGraph

Work in the existing `postgres-migration` branch. First inspect Git status and read `AGENTS.md`, `docs/REFERENCE_RETRIEVAL.md`, `docs/GROUNDED_AI_RECOMMENDATIONS.md` if present, and the current AI, retrieval, and React code. Preserve uncommitted work. Reuse the grounded recommendation flow if it exists locally; if that preceding milestone is unfinished, complete or clearly identify the dependency before wiring the graph.

## Goal

Add one **Analyze case** action. LangGraph loads the case once, runs two **independent parallel branches**, and returns unsaved drafts for reviewer verification in React:

```text
load case ┬─ retrieve redaction rules per activity → recommend → validate ─┬─ return drafts
          └─ load summary guidance → draft case summary ────────────────────┘
```

The summary must not depend on generated or approved redactions. The reviewer accepts/rejects redactions individually and approves/edits the summary separately in the UI. Do not use LangGraph `interrupt()`, a checkpointer, or a `thread_id` for this milestone; the graph ends when it returns drafts.

## Implement

1. Add a small typed `StateGraph` whose state includes `case_id`, a snapshot of the case activities, retrieved reference metadata, raw and validated suggestions grouped by activity ID, summary guidance, and an unsaved summary draft. Use separate state keys for the two branches; join only after both finish. Keep nodes focused and call existing service functions rather than making HTTP calls to this app's own endpoints.
2. Redaction branch: for each activity, reuse the current LangChain retriever and grounded Qwen recommendation logic. Include mandatory policy and relevant examples, excluding the current activity's own labeled example from the generation prompt. Reuse exact-substring/offset, allowed-type, duplicate, and policy-reference validation. Return only valid draft suggestions with supporting rules; do not insert redactions.
3. Summary branch: load the corpus's summary style guide and generate one factual, customer-facing case summary from the actual case activities. Do not depend on the redaction branch or save `Case.ai_summary` in this node. Keep internal caps, counsel instructions, and unsupported conclusions out of the draft; show that a reviewer must verify it.
4. Expose a case-level endpoint (for example `POST /cases/{case_id}/analyze`) that invokes the graph and returns both drafts, grouped by activity and summary. Unknown/closed cases and retrieval/model failures should have clear responses and no partial database writes. Keep database sessions scoped to each concurrent branch; do not share a SQLAlchemy `Session` across parallel nodes.
5. Add an **Analyze case** action to the case detail UI. Display the summary draft with edit/approve/discard controls and the redaction drafts with their existing individual Accept/Reject controls. Approval of one type must not approve the other. Revalidate redactions on acceptance. Add an explicit summary approval endpoint that saves only the reviewer-approved text; preserve existing approved summaries. Remove automatic summary generation/saving from case-list and case-detail loading. Keep manual redactions working.

## Verify and document

- Use fake retriever/model responses to test that both branches use the same case snapshot but remain independent, the graph waits for both, invalid spans are excluded, output is grouped correctly, and generation causes **zero** case/redaction writes. Test no-activity, closed-case, and failure behavior.
- Test UI independence: redaction Accept/Reject does not approve the summary; summary approval does not accept redactions; drafts are clearly labeled and approval persists only the chosen result. Run backend tests on PostgreSQL, plus frontend lint, tests, and build; manually check a seeded case if possible.
- Update README/API notes with the graph, endpoint, and commands. Report files changed, tests actually run, sample draft response, and limitations. Keep the milestone reviewable; do not add travel cases, change the model provider, or merge into `main`.

# AI Recommendations

## Goal

Add AI-assisted redaction recommendations to the existing case-review application.

The AI may suggest redactions, but it must never create database records automatically. Recommendations remain temporary until a reviewer accepts them. Rejecting a recommendation removes it without changing the database.

Complete only this milestone. Do not add RAG, LangGraph, case summaries, authentication, deployment infrastructure, or unrelated schema changes. Ask before making a broader change that is genuinely required.

## Before Making Changes

1. Read `AGENTS.md` and inspect the existing backend, frontend, API routes, models, schemas, tests, and dependency files.
2. Reuse the current redaction validation and creation logic instead of duplicating it.
3. Preserve all existing manual-redaction behavior.
4. Follow the project's current naming, routing, error-handling, and testing conventions.

## 1. Configure the Hugging Face Client

- Add the official `huggingface_hub` Python package to the backend dependency configuration.
- Use `huggingface_hub.InferenceClient` to call Hugging Face Inference Providers.
- Read the token from the existing `HF_TOKEN` environment variable.
- Add an `HF_MODEL` setting with `Qwen/Qwen3-32B` as its default.
- Add an `HF_PROVIDER` setting with `nscale` as its default. Keep it configurable so another compatible provider, or `auto`, can be used without code changes.
- Use strict Structured Outputs generated from the Pydantic response model.
- Add `/no_think` to the model instructions because this is a narrow extraction task.
- Never hardcode, log, return, or expose the token to the React application.
- Ensure `.env` remains ignored by Git and add only empty token placeholders to `.env.example`.

Expected environment configuration:

```env
LLM_PROVIDER=huggingface
HF_TOKEN=
HF_MODEL=Qwen/Qwen3-32B
HF_PROVIDER=nscale
```

Create a small `RecommendationProvider` abstraction and a `HuggingFaceRecommendationProvider` implementation so tests can replace the real call with a fake provider. Do not introduce a large multi-provider framework.

Conceptual SDK usage:

```python
from huggingface_hub import InferenceClient

client = InferenceClient(
    provider=settings.hf_provider,
    api_key=settings.hf_token,
)

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "AIRecommendationResponse",
        "schema": AIRecommendationResponse.model_json_schema(),
        "strict": True,
    },
}

response = client.chat_completion(
    model=settings.hf_model,
    messages=[
        {"role": "system", "content": f"{system_prompt}\n/no_think"},
        {"role": "user", "content": activity.description},
    ],
    response_format=response_format,
)

content = response.choices[0].message.content
recommendations = AIRecommendationResponse.model_validate_json(content)
```

Adapt this example to the project's existing configuration and schema structure. Fail with a controlled configuration error if `HF_TOKEN` is missing. If the configured provider does not support the model or schema, return a controlled provider error; do not silently switch models.

## 2. Define the Temporary Recommendation Format

Create Pydantic response models equivalent to:

```json
{
  "recommendations": [
    {
      "redaction_type": "PERSONAL_INFO",
      "redaction_text": "(555) 014-7821",
      "starting_position": 34,
      "reason": "Customer phone number"
    }
  ]
}
```

Each recommendation must contain:

- `redaction_type`: the name of an existing redaction type
- `redaction_text`: an exact substring copied from the activity description
- `starting_position`: the zero-based character position in the original description
- `reason`: a brief reviewer-facing explanation

Do not include a recommendation database ID. Recommendations are response objects, not database entities.

## 3. Build the Model Instructions

The backend must construct a focused prompt that provides:

- The immutable activity description
- The available redaction types and their descriptions, loaded from the database
- Clear instructions to copy text exactly from the description
- Clear instructions to return zero-based character positions
- Clear instructions not to rewrite, normalize, expand abbreviations, or invent text
- Permission to return an empty recommendation list when nothing should be redacted

The model should identify only spans supported by the source text. The backend—not the model—is responsible for deciding whether the output is valid.

Use only synthetic project data with the API. Do not send real customer records or employer/client data.

## 4. Generate Recommendations

Add an endpoint consistent with the existing route structure, conceptually:

```http
POST /activities/{activity_id}/ai-recommendations
```

Behavior:

1. Retrieve the activity or return `404`.
2. Load the configured redaction types.
3. Call `Qwen/Qwen3-32B` through the configured Hugging Face Inference Provider.
4. Validate every returned recommendation.
5. Return the valid recommendations to React.
6. Do not insert, update, or delete any database record.

For every recommendation, verify:

- `starting_position >= 0`
- `ending_position = starting_position + len(redaction_text)` does not exceed the description length
- `description[starting_position:ending_position] == redaction_text`
- The redaction type exists in the database
- The same recommendation is not returned more than once
- An identical saved redaction does not already exist

Discard invalid individual recommendations safely. If the complete model response is missing, refused, or unusable, return a controlled API error instead of returning unvalidated data.

Handle missing configuration, timeouts, rate limits, exhausted credits, malformed responses, and Hugging Face provider failures without exposing raw exceptions or secrets to the frontend.

## 5. Accept or Reject Recommendations

Keep returned recommendations in React component state only.

### Accept

Provide an accept mutation consistent with the existing API design, conceptually:

```http
POST /activities/{activity_id}/ai-recommendations/accept
```

Send the selected recommendation fields in the request body. On the backend:

1. Retrieve the activity.
2. Repeat the type, bounds, and exact-substring validation. Never trust the browser payload.
3. Reuse the existing redaction creation service.
4. Create one normal redaction record.
5. Set `source` to `AI` on the server; do not trust a client-supplied source.
6. Return the saved redaction.

After success, remove the temporary recommendation and update or refetch the activity's saved redactions so the accepted span uses the existing saved-redaction display.

### Reject

Rejecting requires no backend request because the recommendation has not been saved. Remove it from React state only.

## 6. Add the React Workflow

For each activity:

- Add a `Generate AI recommendations` button.
- Show a loading state while the request runs.
- Show a clear empty state when no recommendations are returned.
- Show a safe, concise error message when generation fails.
- Display temporary recommendations distinctly from saved redactions.
- Show each recommendation's text, type, reason, and `Accept` and `Reject` controls.
- Prevent duplicate submissions while generation or acceptance is in progress.
- Keep existing manual create, edit, and delete controls working.

Do not display temporary recommendations as though they are approved redactions.

## 7. Tests

Automated tests must not make real Hugging Face API calls or require `HF_TOKEN`.

Backend tests should use a fake provider and verify:

- Generating recommendations returns validated structured data.
- Generation does not create redaction records.
- An empty recommendation list is supported.
- A nonexistent activity returns `404`.
- Invalid positions or mismatched text are discarded or rejected as designed.
- Unknown redaction types are discarded or rejected.
- Accepting creates exactly one redaction with `source = AI`.
- Accepting invalid or modified recommendation data fails validation.
- Provider failures produce a controlled API error.

Frontend tests should verify:

- The generate button and loading state.
- Rendering returned recommendations.
- Reject removes a recommendation without a mutation request.
- Accept calls the API and moves the item into the saved-redaction display.
- Empty and error states.
- Existing manual-redaction functionality still works.

## Completion Criteria

This milestone is complete when:

- The backend can request structured recommendations from `Qwen/Qwen3-32B` using `HF_TOKEN`.
- Generated recommendations are validated against the immutable activity description.
- Generating or rejecting recommendations makes no database changes.
- Accepting a recommendation creates a normal redaction with `source = AI`.
- Temporary and saved redactions are clearly distinguished in the UI.
- Backend and frontend tests pass without calling the real Hugging Face API.
- A manual local test using synthetic data succeeds with the real API key.

When finished, report the files changed, commands used to run the tests, and the manual steps required to verify generation, rejection, and acceptance.

## Hugging Face References

- Qwen3-32B model: https://huggingface.co/Qwen/Qwen3-32B
- Inference Providers: https://huggingface.co/docs/inference-providers/index
- Chat Completion API: https://huggingface.co/docs/inference-providers/en/tasks/chat-completion
- Structured Outputs: https://huggingface.co/docs/inference-providers/en/guides/structured-output

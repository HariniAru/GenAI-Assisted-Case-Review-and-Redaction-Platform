# Local Studio and LangSmith tracing

Studio visualizes and runs the existing `case_analysis` graph. LangSmith stores
traces from both Studio runs and the application's **Analyze case** endpoint.
The graph still only returns drafts; approvals remain in the React/FastAPI flow.

## Configuration

Keep your existing key in ignored `backend/.env`:

```dotenv
LANGSMITH_API_KEY=<your-key>
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=case-review
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Use your existing project name if different. For a region other than the US,
use that workspace's API endpoint. Keys spanning multiple workspaces may also
need `LANGSMITH_WORKSPACE_ID`. Never paste keys into `langgraph.json`, source,
screenshots, or commits.

Keep `DATABASE_URL` in `.env.postgres`. For Studio, the command loads `.env`
first and `.env.postgres` second; `langgraph.json` also points at `.env.postgres`.
This matters because the Studio server loads its configured env file with
override enabled: pointing that configuration at `.env` would restore the
historical SQLite URL even when uv supplied PostgreSQL. Studio now refuses to
start with a SQLite URL. Do not duplicate LangSmith variables between the files;
keep them in `.env`. Restart both servers after changing settings. For normal
API commands, exported shell variables take precedence over uv's env file.

Tracing is off by default in the example configuration. Enabling it sends
synthetic activity text, retrieved context, model inputs, and drafts to your
LangSmith workspace. Credentials are not put in graph state or trace inputs.
Use only this project's synthetic data. Set `LANGSMITH_TRACING=false` and restart
to disable hosted tracing. Retrieval inspection endpoints remain untraced.

## Launch Studio

Ensure the existing PostgreSQL Docker service is running. No additional Docker
service is needed for Studio. Use Python 3.11 or newer for the optional server:

```bash
# From repository root
docker compose --env-file backend/.env.postgres up -d --wait
cd backend
uv sync --locked --extra dev --extra studio
uv run --extra studio --env-file .env --env-file .env.postgres langgraph dev --host 127.0.0.1
```

Open the Studio URL printed by the server, normally:

<https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024>

Sign into the LangSmith account associated with your key. Select `case_analysis`,
start a new run, and supply only a database case ID (not its CASE-1002 label):

```json
{"case_id": 2}
```

Select an open case from the application's current case list; case 2 is open
in the original seed but may have been closed during review. The reference
corpus must already be ingested and the existing Hugging Face credentials valid.
Running analysis invokes that model and can incur usage charges. View individual
nodes, their inputs/outputs, and the joined `result` containing unsaved drafts.
Use a new Studio run/thread for each analysis rather than resuming old drafts.
Studio is a debugging surface; approve summaries/redactions in the application.

The development server is bound to loopback and has no application authentication.
It uses its own local run/checkpoint storage under `backend/.langgraph_api/`, which
Git ignores. This is an explicit development-only extension of the preceding
milestone: the application graph still has no custom checkpointer or interrupt,
and the FastAPI endpoint still needs no thread ID. Stop Studio with Ctrl+C.

## Trace the application

Run the normal API in another terminal:

```bash
cd backend
uv run --extra studio --env-file .env.postgres uvicorn app.main:app --reload
```

Start the frontend as usual and select **Analyze case**. In LangSmith, open the
project named by `LANGSMITH_PROJECT` and inspect the `case_analysis` trace.
It includes the parallel branches and `Qwen summary`/`Qwen redactions` child runs.
Provider child runs record function inputs and parsed outputs; they do not yet
provide token/cost accounting. Studio also emits graph traces; its server may
choose its own root run name. Opening case pages alone does not invoke analysis.

Keep `--extra studio` when using both servers in the same virtual environment so
uv does not remove Studio's optional packages. It is unnecessary for API-only use.

The API's tracing context uses Pydantic settings and an explicit LangSmith client,
so the key in `.env` works without exporting it to the shell. Studio gets the key
from uv's `.env` loading and PostgreSQL from `langgraph.json`. The optional `studio` extra isolates the larger
development-server dependencies from the normal API install. The directly used
`langsmith` SDK is now declared explicitly in production dependencies.

## Verification

```bash
cd backend
uv run --extra dev --extra studio ruff check .
uv run --extra dev --extra studio ruff format --check .
uv run --extra dev --extra studio --env-file .env.postgres pytest -q
env -u TEST_DATABASE_URL uv run --extra dev --extra studio pytest -q
```

Tests disable external tracing and use mocked trace transport to check that all
graph nodes are recorded when enabled. They also verify local `.env` settings,
the disabled path, the Studio input schema, and existing approval behavior.

Verified during setup: Ruff lint/format passed; PostgreSQL **41 tests passed**;
SQLite **37 passed, 4 skipped**.
The Studio health and registered graph schema
endpoints returned 200. A fabricated connection trace containing no case data
was uploaded to LangSmith and read back successfully using the configured key.
After explicit user approval, case 2 completed through the local Studio server
using PostgreSQL and the live Qwen provider: one summary draft and four validated
redaction proposals across two activities. A before/after comparison confirmed
all case and redaction rows were unchanged. The initial attempt exposed the env
override issue described above; the corrected run succeeded. Browser interaction
itself was not tested. LangSmith read-back confirmed the root graph, both branches,
two retriever runs, and all three Qwen child runs completed without errors.

Official references: [local development server](https://docs.langchain.com/langsmith/local-dev-testing),
[tracing configuration](https://docs.langchain.com/langsmith/trace-without-env-vars),
and [LangGraph tracing](https://docs.langchain.com/langsmith/trace-with-langgraph).

# Agent Atlas

An autonomous background task operator built on the [Google Agent Development
Kit (ADK)](https://adk.dev) and Gemini. You submit a goal; Atlas decomposes it
into a plan, executes it step-by-step with real tools (web research, document
ingest, data transformations), and writes a deliverable — asynchronously, in
the background, with every step persisted to Firestore.

Built for the [All Things Agentic Hackathon](https://allthingsagentic.devpost.com/)
(Taskmaster track). Runs on Cloud Run with Cloud Firestore for state and Cloud
Scheduler for async wake-ups.

## Overview

Most agent tutorials produce a stateless chatbot. Atlas is designed for the
opposite operating envelope: long-running, multi-step tasks that must survive
container restarts, scale-to-zero periods, and days of idle time.

Three properties make this work:

1. **Firestore is the source of truth.** Task state, plan steps, the event
   log, and long-term memory live in Firestore. The agent's system prompt is
   rendered from that state on every wake-up — it never infers progress from
   chat history.
2. **The queue drives execution.** Tasks are submitted as `PENDING`
   documents. A Cloud Scheduler cron wakes a Cloud Run worker that claims them
   with an atomic Firestore transaction, runs bounded agent turns, and
   re-queues unfinished work for the next tick.
3. **Tools are the interface to the world.** Search, fetch, ingest, transform,
   and deliver operations are typed functions whose schemas ADK generates from
   their signatures.

## Architecture

```
Dashboard ──POST /api/tasks──▶ Cloud Run (FastAPI)
Cloud Scheduler ──POST /cron/run──▶ Cloud Run
Cloud Run ──claim (transaction)──▶ Firestore
Cloud Run ──run_turn(state_delta)──▶ ADK Runner ──▶ Gemini
ADK Runner ──function calls──▶ Tools ──▶ Firestore / web / filesystem
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the diagram and
[docs/DESIGN.md](docs/DESIGN.md) for the engineering rationale, state model,
and failure-mode analysis.

## Features

- **Goal → plan**: a deterministic planner with optional Gemini refinement
  produces 3–6 concrete steps (`research`, `transform`, `ingest`, `memory`,
  `deliver`).
- **Autonomous execution**: the ADK agent sequences tool calls toward
  completion without supervision.
- **Data pipelines**: `transform_data` runs head / summary / clean / filter /
  sort / keep / count over CSV or JSON; `ingest_document` reads URLs, files,
  or inline text.
- **Durable memory**: `remember` / `recall` persist findings per task in
  Firestore across sessions.
- **Audit log**: every tool call and state transition is recorded as an event
  on the task.
- **Checkpoint-and-resume**: `current_step` lives in Firestore, so a worker
  picks up exactly where the previous one stopped.
- **Human steering**: message a running task to redirect it mid-flight.
- **Zero-GCP demo mode**: `STORE_BACKEND=local` runs the full system on JSON
  files, no account or API key required.

## Getting started

### Prerequisites

- Python 3.11+ (the runtime and tests)
- A Gemini API key ([AI Studio](https://aistudio.google.com/apikey)) for real
  model calls — optional for the local demo, which degrades gracefully
- Node.js (optional) — only used to serve the dashboard assets during local
  development; the Docker image serves them directly

### Local demo (no Google Cloud)

```bash
git clone https://github.com/ro161012/agent-atlas.git
cd agent-atlas

bash deploy/local.sh          # creates .venv, installs deps, starts uvicorn
# open http://localhost:8080
```

Or manually:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
export GEMINI_API_KEY=your-key        # optional
export STORE_BACKEND=local            # JSON-file ledger, no GCP needed
./.venv/bin/uvicorn app.api.main:app --port 8080
```

Submit a goal from the dashboard, then either wait for the next cron tick or
trigger a run immediately with `POST /api/tasks/{id}/run`.

### Deploy to Google Cloud

```bash
PROJECT_ID=your-project-id bash deploy/gcp.sh
```

The script enables the required APIs, creates the Firestore database and
Artifact Registry repo, builds via Cloud Build, deploys the container to Cloud
Run (scale-to-zero, unauthenticated for the demo), and registers a Cloud
Scheduler job that POSTs `/cron/run` every two minutes. See
[deploy/gcp.sh](deploy/gcp.sh) and [cloudbuild.yaml](cloudbuild.yaml).

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/tasks` | Submit `{"goal": "...", "title": "..."}` |
| `GET` | `/api/tasks` | List tasks, newest first |
| `GET` | `/api/tasks/{id}` | Task, plan, and event log |
| `POST` | `/api/tasks/{id}/run` | Execute one agent turn immediately |
| `POST` | `/api/tasks/{id}/message` | Steer a task: `{"message": "..."}` |
| `POST` | `/cron/run` | Drain the task queue (Cloud Scheduler hook) |
| `GET` | `/healthz` | Liveness + config |

## Project layout

```
app/
├── agent.py          # ADK LlmAgent: instruction template, state seeding, runner
├── planner.py        # goal → step plan (Gemini-refined, heuristic fallback)
├── store.py          # Firestore ledger + LocalStore (JSON) fallback
├── worker.py         # async drain loop: claim → run turn → persist → re-queue
├── state_schema.py   # task/step state machine
├── tools/
│   ├── web.py        # web_search, fetch_url
│   ├── data.py       # ingest_document, transform_data, write_deliverable
│   ├── ledger.py     # record_step, complete_task
│   └── memory.py     # remember, recall
└── api/main.py       # FastAPI app: REST + cron + static dashboard
web/                  # dashboard (vanilla HTML/CSS/JS)
deploy/               # local.sh, gcp.sh
docs/                 # ARCHITECTURE.md, DESIGN.md
tests/                # pytest suite (no network or GCP dependencies)
```

## Testing

```bash
pip install -r requirements.txt pytest ruff
ruff check app tests && ruff format --check app tests
pytest
```

The suite covers the planner, both storage backends, the data-transform tools,
and a full task lifecycle (plan → execute → complete) with no network access.
CI runs the same checks on Python 3.11 and 3.12 (see
[.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Configuration

All configuration is via environment variables (see [.env.example](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | Gemini API key (or use Vertex: `GEMINI_PROJECT` / `GEMINI_LOCATION`) |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Model identifier |
| `STORE_BACKEND` | `firestore` | `firestore` or `local` |
| `FIRESTORE_PROJECT` | — | GCP project for Firestore (defaults to ADC) |
| `FIRESTORE_PREFIX` | `atlas` | Collection prefix |
| `LOCAL_STORE_PATH` | `./atlas_data` | Local-backend data dir |
| `SPRING_BATCH` | `5` | Tasks per cron cycle |
| `MAX_TURNS_PER_STEP` | `8` | Turns per task per cycle |
| `MAX_STEPS_PER_TASK` | `30` | Total turn budget before a task fails |
| `SERPAPI_KEY` | — | Enables live web search |

## Security notes

- The API has no authentication; use Cloud Run's own access controls or add
  auth for anything beyond a demo.
- Firestore rules allow server (service-account) writes only; see
  [firestore.rules](firestore.rules).
- Keys are read from the environment; use Secret Manager in production.
- A demo install of the scheduler should be deleted after use to avoid ongoing
  cron invocations.

## License

MIT. See [LICENSE](LICENSE).

Submission materials: [DEVPOST_SUBMISSION.md](DEVPOST_SUBMISSION.md) and
[VIDEO_SCRIPT.md](VIDEO_SCRIPT.md).

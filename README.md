# ◈ Agent Atlas — the autonomous task operator

**All Things Agentic Hackathon · Taskmaster track**

> "Most AI today waits for you to ask. Atlas doesn't."

Agent Atlas is an **autonomous background agent** built on **Google ADK + Gemini**
that takes a messy, multi-step goal — "research X, clean this dataset, write me a
report" — decomposes it into a durable plan, and **executes it in the background**
while you do something else. Every step, tool call, and finding is persisted to
**Cloud Firestore**, so a Cloud Run container can scale to zero between ticks and
a worker picks up exactly where the last one left off.

Built for the [All Things Agentic Hackathon](https://allthingsagentic.devpost.com/).
Runs on **Gemini 3.5** (via Gemini API or Vertex AI), **Google ADK**, and
**Cloud Run + Firestore + Cloud Scheduler**.

---

## ✨ What it does

| Capability | How |
|---|---|
| **Goal → plan** | Planner decomposes a fuzzy request into 3–6 concrete steps (`research`, `transform`, `ingest`, `memory`, `deliver`) |
| **Autonomous execution** | The ADK agent reasons with Gemini and takes action with real tools — live web search, URL fetch, document ingest, data pipelines |
| **Data pipelines** | `transform_data` runs head / summary / clean / filter / sort / keep / count over CSV or JSON; deliverables written to disk (GCS in prod) |
| **Durable memory** | `remember` / `recall` persist findings in Firestore — context survives *days*, not just one chat |
| **Async, always-on** | Tasks sit in a Firestore queue; Cloud Scheduler pings `/cron/run`; workers drain the queue, re-queueing unfinished work for the next tick |
| **Checkpoint-and-resume** | The agent reads its position from Firestore-backed session state (`current_step`), never from chat history — no hallucinated progress, no lost context |
| **Human steering** | Submit a goal and walk away, or drop in later with "focus on pricing data" via the dashboard |

---

## 🏗️ Architecture

```
┌────────────┐      POST /api/tasks        ┌─────────────────────────────────────┐
│  Dashboard │ ──────────────────────────▶ │  Cloud Run (uvicorn + FastAPI)     │
│  (web UI)  │ ◀────────────────────────── │  ├─ POST /api/tasks   submit goal  │
└────────────┘   task + live event log     │  ├─ POST /cron/run   drain queue   │
                                           │  └─ GET  /           dashboard     │
┌────────────┐   every 2 min               │            │                       │
│  Cloud     │ ───── POST /cron/run ─────▶ │  Worker: claims tasks, drives the  │
│  Scheduler │                             │  ADK Runner (Gemini 3.5) turn by   │
└────────────┘                             │  turn, re-seeding session state    │
                                           └───────────┬───────────┬───────────┘
                                                       │ reads/writes
                                                       ▼
                                           ┌─────────────────────────────┐
                                           │  Firestore (source of truth)│
                                           │  tasks / steps / events /   │
                                           │  memory — survives cold     │
                                           │  starts & scale-to-zero     │
                                           └─────────────────────────────┘
```

- **Compute** — Cloud Run (scales to 0; only alive while working)
- **Async trigger** — Cloud Scheduler HTTP cron → `/cron/run`
- **State** — Cloud Firestore: task queue, step ledger, event log, long-term memory
- **Brain** — Google ADK `LlmAgent` + Gemini (Gemini API or Vertex AI)
- **Tools** — ADK function tools: `web_search`, `fetch_url`, `ingest_document`,
  `transform_data`, `write_deliverable`, `remember`/`recall`, `record_step`,
  `complete_task`

Full diagram + design notes: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## 🚀 Spin-up instructions

### Option A — local demo, zero Google Cloud (2 minutes)

Requires **Python 3.11+** and a free `GEMINI_API_KEY`
([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) — or no key
at all (the planner falls back to a heuristic plan and the agent still runs its
toolset with structured reasoning).

```bash
git clone https://github.com/ro161012/agent-atlas.git
cd agent-atlas

# one-command launcher (creates .venv, installs deps)
bash deploy/local.sh
#   → open http://localhost:8080

# or manually:
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
export GEMINI_API_KEY=your-key          # optional but recommended
export STORE_BACKEND=local              # JSON-file ledger, no GCP needed
./.venv/bin/uvicorn app.api.main:app --port 8080
```

Then in the dashboard: paste a goal → watch Atlas plan it → hit **Run a turn**
(or just wait for the next cron tick) → watch the event log fill with tool calls
and progress. With `STORE_BACKEND=local`, everything also works offline:
`export GEMINI_API_KEY=` and try "Clean this CSV … write cleaned.csv".

### Option B — deploy to Google Cloud (production path)

```bash
# 1) prerequisites
gcloud auth login && gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login

# 2) set secrets (Gemini API key, or Vertex AI project+location)
gcloud secrets create atlas-gemini-key --data-file=key.txt   # optional

# 3) one script does: APIs → Firestore → build → Cloud Run → Scheduler cron
PROJECT_ID=YOUR_PROJECT_ID bash deploy/gcp.sh
```

Under the hood `deploy/gcp.sh` runs the Cloud Build pipeline in
[`cloudbuild.yaml`](cloudbuild.yaml), deploys the container to Cloud Run
(unauth access for the demo), and creates a Cloud Scheduler job that POSTs
`/cron/run` every 2 minutes. The service authenticates to Firestore via its
default service account — no keys in the container.

> **Cost note:** Cloud Run scales to zero; the Firestore queue + 2-min cron keep
> costs near zero between submissions. Kill the scheduler after your demo.

### Verify it's running

```bash
curl http://localhost:8080/healthz
# {"status":"ok","model":"gemini-3.5-flash","store":"firestore"}

# submit a goal via the API
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"goal":"Research the top 5 open-source AI coding agents and write competitive_analysis.md"}'

# force a drain (normally Cloud Scheduler does this)
curl -X POST http://localhost:8080/cron/run

# inspect the task
curl http://localhost:8080/api/tasks/TASK_ID
```

---

## 🔌 API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/tasks` | Submit `{"goal": "…", "title": "…"}` → plans + queues |
| `GET` | `/api/tasks` | List tasks (newest first) |
| `GET` | `/api/tasks/{id}` | Task + plan + event log |
| `POST` | `/api/tasks/{id}/run` | Execute one agent turn immediately |
| `POST` | `/api/tasks/{id}/message` | Steer an existing task with `{"message": "…"}` |
| `POST` | `/cron/run` | Cloud Scheduler hook — drain the queue |
| `GET` | `/healthz` | Liveness + config echo |

---

## 📂 Repo layout

```
app/
├── agent.py          # ADK LlmAgent: instruction, state seeding, run_turn()
├── planner.py        # goal → step plan (Gemini-refined w/ heuristic fallback)
├── store.py          # Firestore ledger + LocalStore (JSON) fallback
├── worker.py         # async drain loop: claim → run turn → persist → re-queue
├── state_schema.py   # TaskStatus / StepStatus state machine
├── tools/
│   ├── web.py        # web_search (SerpAPI) + fetch_url
│   ├── data.py       # ingest_document, transform_data, write_deliverable
│   ├── ledger.py     # record_step, complete_task (durable progress)
│   └── memory.py     # remember / recall (durable long-term memory)
└── api/main.py       # FastAPI: REST + cron + dashboard
web/                  # vanilla dashboard (index.html / app.js / style.css)
deploy/               # local.sh + gcp.sh launchers
cloudbuild.yaml       # CI: build → Artifact Registry → Cloud Run
firestore.rules       # demo rules (server-authoritative writes)
docs/ARCHITECTURE.md  # design deep-dive + Mermaid diagram
examples/sample_goals.json
tests/                # unit tests for planner + local store
```

---

## 🧪 Tests

```bash
./.venv/bin/python -m pytest tests/ -q
```

Covers the heuristic planner and the local store backend (create/claim/plan/
memory) without any network or GCP dependencies.

---

## ✅ Hackathon requirements checklist

| Requirement | Where |
|---|---|
| Gemini 3.5 (Gemini API or Vertex AI) | `app/agent.py` — `Gemini(model=…)`, env-configurable, defaults to `gemini-3.5-flash` |
| Google Agent Framework | Google **ADK**: `LlmAgent`, `Runner.run_async`, `ToolContext`, function tools, session state, callbacks |
| Google Cloud infrastructure | **Cloud Run** (compute), **Firestore** (queue/state/memory), **Cloud Scheduler** (async trigger) |
| Async, beyond chat | Firestore queue + cron worker; tasks run to completion unattended |
| Data pipelines | `transform_data`, `ingest_document`, `write_deliverable` |
| Durable context | Firestore-backed step ledger + `remember`/`recall` memory bank |
| Reproducible setup | This README (spin-up) + `deploy/` scripts |
| Architecture diagram | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) + `docs/architecture.svg` |

See [`DEVPOST_SUBMISSION.md`](DEVPOST_SUBMISSION.md) for the full write-up, and
[`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md) for the ~4-minute demo script.

---

## 📄 License

MIT © 2026 ro161012 — built for the All Things Agentic Hackathon.

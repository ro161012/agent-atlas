# Agent Atlas — Devpost Submission

**Track:** The Taskmaster
**Repo:** https://github.com/ro161012/agent-atlas
**Demo video:** see VIDEO_SCRIPT.md (script for the ~4-min submission video)

---

## Tagline
**Agent Atlas** — an autonomous background task operator that takes a messy,
multi-step goal, plans it, and *executes it* on Google Cloud while you do
something else.

## Description

### The problem
Most AI today waits for you to ask. The next generation doesn't: agents take a
goal, make a plan, and actually carry it out. But the *hard* part isn't writing
a plan — it's **finishing the job asynchronously**: surviving container
restarts, keeping context across days, not hallucinating progress, and taking
real actions (searching, transforming data, writing deliverables) instead of
just talking.

### The solution
Atlas is a Taskmaster-track agent built with **Google ADK + Gemini 3.5** that
runs as a durable background process on **Cloud Run + Firestore + Cloud
Scheduler**:

1. **Submit a goal** ("research the top 5 open-source AI coding agents and write
   competitive_analysis.md") through the dashboard or REST API.
2. **Atlas plans** — the goal is decomposed into 3–6 concrete steps
   (research / transform / ingest / memory / deliver), Gemini-refined when a
   key is present, with a deterministic fallback so nothing blocks.
3. **Atlas executes in the background** — a Cloud Scheduler cron wakes a Cloud
   Run worker every 2 minutes; the worker claims queued tasks with an atomic
   Firestore transaction and drives the ADK agent turn-by-turn with real tools:
   live web search, URL fetching, document ingest, CSV/JSON data pipelines, and
   deliverable writing.
4. **Progress is durable** — every step, tool call, and finding is persisted to
   Firestore. On every wake-up the agent's system prompt is re-rendered from
   durable state (`current_step`, plan, memory) via ADK `state_delta` — it
   *knows* where it is, it never *guesses*.
5. **Check in anytime** — the dashboard shows a live event log; you can steer
   with messages ("focus on pricing data") or let it run to completion.

### Why it's not a chatbot
- **Takes action:** web search, URL fetch, document ingest, data transforms, and
  file deliverables — not prose.
- **Runs async:** a Firestore queue + cron-driven workers; scale-to-zero
  friendly; tasks survive restarts mid-step.
- **Remembers:** a Firestore-backed memory bank (`remember`/`recall`) spans
  sessions and days, not just one chat.
- **Checkpoint-and-resume:** the model reads its position from state, never from
  replayed chat history — no hallucinated "completed" steps.

---

## Features & functionality

1. **Goal → plan decomposition** — heuristic-by-default, Gemini-refined when a
   key is configured (planner.py).
2. **Autonomous multi-step execution** — ADK agent drives its own tool sequence
   toward completion (worker.py + agent.py).
3. **Live web research** — `web_search` (SerpAPI Google) + `fetch_url` with
   HTML→text extraction.
4. **Data pipelines** — `transform_data` supports head / summary / clean /
   filter / sort / keep-columns / count over CSV or JSON; `ingest_document`
   pulls URLs, files, or inline text.
5. **Deliverables** — `write_deliverable` writes reports/CSVs/JSON to disk
   (GCS-ready in production).
6. **Durable task ledger** — Firestore stores tasks, steps, and a full event
   log; atomic claim prevents double execution.
7. **Memory bank** — `remember` / `recall` persist findings per project across
   days of asynchronous operation.
8. **Human steering** — message a running task ("focus on X") and it adapts.
9. **Dashboard** — zero-build static UI served by FastAPI: submit, watch live
   event log, run a turn, steer.
10. **Zero-GCP local demo** — `STORE_BACKEND=local` runs the full system on JSON
    files with no account and no API key.

---

## Technologies used

| Layer | Technology |
|---|---|
| Agent framework | **Google ADK** (LlmAgent, `Runner.run_async`, ToolContext, function tools, session state) |
| Model | **Gemini 3.5** via Gemini API or Vertex AI (env-configurable, defaults `gemini-3.5-flash`) |
| Compute | **Cloud Run** (containerized, scale-to-zero) |
| Async trigger | **Cloud Scheduler** (HTTP cron → `/cron/run`) |
| State & memory | **Cloud Firestore** (queue, step ledger, event log, memory bank) |
| API layer | FastAPI + uvicorn |
| Build/CI | Docker + Cloud Build (`cloudbuild.yaml`) |
| Web UI | Vanilla HTML/CSS/JS dashboard served by FastAPI |
| Tests | pytest (planner + local store) |

## Other data sources used
- SerpAPI Google Search (optional `SERPAPI_KEY`) for live web research
- Arbitrary user-supplied URLs, documents, and CSV/JSON datasets

---

## Findings & learnings

1. **State beats history.** The single biggest reliability win was moving the
   agent's position out of the conversation and into a durable ledger, then
   re-rendering the system prompt from it on every wake-up. It eliminated
   hallucinated progress and made scale-to-zero trivial.
2. **The queue is the orchestrator.** A Firestore queue + atomic claim +
   cron-driven drain is dramatically simpler and cheaper than a long-lived
   polling process — and it fails open: a crashed container just leaves the task
   for the next tick.
3. **ADK's design pays off.** Tools-as-typed-functions with `ToolContext` state
   injection made the durable-progress pattern nearly free; function-call
   events drop straight into an audit log.
4. **Deterministic fallbacks keep demos alive.** Gemini-refined planning with a
   heuristic fallback and a tool `status: unavailable` path means the demo never
   hard-fails on a missing API key — a huge demo-day safety net.

---

## Judging criteria alignment

| Criterion | How Atlas scores |
|---|---|
| **Innovation & Operational Utility (40%)** | Autonomous action: it searches, ingests, transforms, and writes deliverables with zero hand-holding; async by design; multi-day memory. |
| **Architectural Discipline & Tech Stack (30%)** | Decoupled queue/worker/ledger; durable state machine; atomic claims; bounded step budgets; failure recovery; clean ADK + Cloud Run + Firestore stack. |
| **Demo & Production Readiness (30%)** | Live unedited demo in ~4 min; reproducible spin-up (README + deploy scripts); architecture diagram (docs/ARCHITECTURE.md + SVG); visible Cloud Run/Firestore proof in the video. |

---

## Built for
**All Things Agentic Hackathon** — Taskmaster track.
**Team:** Solo project by ro161012

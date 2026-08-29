# Agent Atlas — Devpost Submission

**Track:** The Taskmaster
**Repo:** https://github.com/ro161012/agent-atlas
**Demo video:** see VIDEO_SCRIPT.md (script for the ~4-minute submission video)

## Tagline

Agent Atlas is an autonomous background task operator that takes a messy,
multi-step goal, plans it, and executes it end-to-end on Google Cloud while you
do something else.

## Description

### The problem

The hard part of an agent isn't writing a plan — it's finishing the job.
Production agents run asynchronously, in the background, for hours or days.
They must survive container restarts and scale-to-zero periods, keep context
across sessions, never hallucinate progress, and take real actions (searching,
transforming data, writing deliverables) instead of just talking.

### The solution

Atlas is a Taskmaster-track agent built with Google ADK + Gemini 3.5 that runs
as a durable background process on Cloud Run, Cloud Firestore, and Cloud
Scheduler:

1. **Submit a goal** through the dashboard or REST API — e.g. "research the
   top 5 open-source AI coding agents and write competitive_analysis.md".
2. **Atlas plans.** The goal is decomposed into 3–6 concrete steps
   (research / transform / ingest / memory / deliver), Gemini-refined when a
   key is configured, with a deterministic fallback so the pipeline never
   blocks on the model.
3. **Atlas executes in the background.** A Cloud Scheduler cron wakes a Cloud
   Run worker every two minutes. The worker claims queued tasks with an atomic
   Firestore transaction and drives the ADK agent turn-by-turn with real tools:
   web search, URL fetching, document ingest, CSV/JSON data pipelines, and
   deliverable writing.
4. **Progress is durable.** Every step, tool call, and finding is persisted to
   Firestore. On each wake-up the system prompt is re-rendered from durable
   state (`current_step`, plan, memory) via ADK `state_delta` — the agent
   knows where it is; it never guesses.
5. **Check in anytime.** The dashboard exposes a live event log, and you can
   steer a running task with a message ("focus on pricing data") or let it run
   to completion.

### What distinguishes it from a chatbot

- **Takes action:** web search, URL fetch, document ingest, data transforms,
  and file deliverables — not prose.
- **Runs asynchronously:** a Firestore queue plus cron-driven workers;
  scale-to-zero friendly; tasks survive restarts mid-step.
- **Remembers:** a Firestore-backed memory bank spans sessions and days.
- **Checkpoint-and-resume:** the model reads its position from state, never
  from replayed chat history, so progress cannot be hallucinated.

## Features

1. Goal → plan decomposition (Gemini-refined, heuristic fallback)
2. Autonomous multi-step execution toward completion
3. Live web research (`web_search` via SerpAPI, `fetch_url` with HTML→text)
4. Data pipelines: head / summary / clean / filter / sort / keep / count over
   CSV or JSON; document ingest from URLs, files, or inline text
5. Deliverables written to disk (GCS-ready in production)
6. Durable task ledger in Firestore with atomic, transaction-safe claims
7. Long-term memory (`remember` / `recall`) scoped per task
8. Human steering of in-flight tasks
9. Dashboard: submit, watch the live event log, trigger a run, steer
10. Zero-GCP local mode (`STORE_BACKEND=local`) for instant demos

## Technologies used

| Layer | Technology |
|---|---|
| Agent framework | Google ADK (LlmAgent, `Runner.run_async`, `ToolContext`, function tools, session state) |
| Model | Gemini 3.5 via Gemini API or Vertex AI (env-configurable, default `gemini-3.5-flash`) |
| Compute | Cloud Run (containerized, scale-to-zero) |
| Async trigger | Cloud Scheduler (HTTP cron → `/cron/run`) |
| State and memory | Cloud Firestore (queue, step ledger, event log, memory bank) |
| API layer | FastAPI + uvicorn |
| Build/CI | Docker + Cloud Build; GitHub Actions (lint, format, tests) |
| Web UI | Vanilla HTML/CSS/JS served by FastAPI |
| Tests | pytest (planner, stores, transforms, full lifecycle) |

## Other data sources used

- SerpAPI Google Search (optional `SERPAPI_KEY`) for live web research
- Arbitrary user-supplied URLs, documents, and CSV/JSON datasets

## Findings and learnings

1. **State beats history.** Moving the agent's position out of the
   conversation and into a durable ledger, then re-rendering the system prompt
   from it on every wake-up, eliminated hallucinated progress and made
   scale-to-zero trivial.
2. **The queue is the orchestrator.** A Firestore queue with atomic claim and
   a cron-driven drain is simpler and cheaper than a long-lived poller, and it
   fails open: a crashed container just leaves the task for the next tick.
3. **ADK's design pays off.** Tools-as-typed-functions with `ToolContext` state
   injection made the durable-progress pattern nearly free, and function-call
   events drop straight into an audit log.
4. **Deterministic fallbacks keep demos alive.** Gemini-refined planning with
   a heuristic fallback, and tools that report `status: unavailable` instead
   of raising, mean the demo never hard-fails on a missing API key.

## Built for

All Things Agentic Hackathon — Taskmaster track. Solo project by ro161012.

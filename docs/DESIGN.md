# Design

## 1. Goals and non-goals

**Goals**

- Accept a natural-language goal and execute it to completion without a human
  in the loop, using Google ADK + Gemini.
- Survive container restarts and scale-to-zero: no in-flight task may depend on
  process memory.
- Keep a full audit trail of every tool call and state transition.
- Run at near-zero cost when idle.

**Non-goals**

- General chat. Atlas is a task executor; interactive Q&A is only supported as
  a way to steer an existing task.
- A hosted multi-tenant product. Auth, quotas, and per-user isolation are out
  of scope for this submission (noted in §7).

## 2. Architecture

```
Dashboard ──POST /api/tasks──▶ Cloud Run (FastAPI)
Cloud Scheduler ──POST /cron/run──▶ Cloud Run
Cloud Run ──claim (transaction)──▶ Firestore
Cloud Run ──run_turn(state_delta)──▶ ADK Runner ──▶ Gemini
ADK Runner ──function calls──▶ Tools ──▶ Firestore / web / filesystem
```

Three components matter:

1. **Firestore is the source of truth.** Tasks, plan steps, the event log, and
   long-term memory live in Firestore. The agent's system instruction is
   rendered from session state (`{goal}`, `{plan}`, `{current_step}`), which
   the worker re-seeds from Firestore on every wake-up via `state_delta`.
2. **The queue drives execution.** Tasks are submitted as `PENDING` documents.
   A cron-triggered worker claims them with an atomic Firestore transaction,
   runs bounded agent turns, persists events, and re-queues unfinished work for
   the next tick. Multiple Cloud Run instances can safely coexist.
3. **Tools are the interface to the world.** Search, fetch, ingest, transform,
   and deliver operations are plain typed functions; ADK generates their
   schemas from signatures and injects `ToolContext` for session state.

## 3. State model

```
Task:   PENDING → PLANNING → PENDING → RUNNING ⇄ PENDING (re-queue)
                                          ├→ WAITING   (human input)
                                          ├→ COMPLETED
                                          └→ FAILED    (error / step budget)
Step:   PENDING → IN_PROGRESS → DONE | BLOCKED
```

- The ledger stores `current_step` per task; steps are addressed by index.
- Tools (`record_step`, `complete_task`) are the *only* writers of task status;
  the model cannot advance progress by talking about it.
- A per-task `memory_scope` (`task:{id}`) namespaces durable `remember`/`recall`
  entries, so a task resumed days later rehydrates its own context.

## 4. Failure modes

| Failure | Behavior |
|---|---|
| Container dies mid-step | Step never marked `DONE`; next tick re-claims and continues. |
| Gemini API error / timeout | Turn raises; worker marks task `FAILED` and records the error event. |
| Task loops | `MAX_STEPS_PER_TASK` budget fails runaway tasks. |
| Two workers claim the same task | Firestore transaction makes claim atomic; loser gets nothing. |
| No composite indexes on fresh Firestore | Queries use single-field filters only and sort in Python. |
| Missing API keys (local demo) | Planner falls back to a deterministic plan; tools report `status: unavailable`. |

## 5. Cost posture

- Cloud Run scales to zero; no compute exists between cron ticks.
- Cron interval and batch sizes are configurable (`SPRING_BATCH`,
  `MAX_TURNS_PER_STEP`, `MAX_STEPS_PER_TASK`).
- The deployment script should be paired with a scheduler delete after the
  demo window (see `deploy/gcp.sh`).

## 6. Alternative storage designs considered

- **ADK `DatabaseSessionService` (SQLite/Cloud SQL)** — best for turn-level
  resumability; rejected as the *primary* store because Firestore already
  provides the queue, memory, and audit log with one credential and zero index
  management. Could be layered on later for crash-mid-turn recovery.
- **Pub/Sub as the queue** — cleaner fan-out, but adds a second system to
  operate and observe; Firestore's transactional claim is sufficient at this
  scale and keeps the demo to one storage backend.
- **Long-lived poller process** — simplest to reason about, but burns always-on
  compute and contradicts the scale-to-zero goal.

## 7. Known limitations (out of scope for this submission)

- No authentication on the API; intended for demo use behind the Cloud Run
  URL's own access controls.
- Deliverables write to local disk; production should target Cloud Storage.
- Single-region, single-project assumptions throughout.
- The plan is Gemini-refined when a key is configured, otherwise heuristic —
  the heuristic path is intentionally generic.

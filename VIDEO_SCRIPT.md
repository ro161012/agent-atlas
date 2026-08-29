# Agent Atlas — ~4-Minute Demo Video Script

**Total runtime:** ~4:00 · **Format:** screen recording + voiceover
**Tone:** measured, factual; the execution demo is recorded live, unedited

---

## [0:00–0:30] Hook and problem

**SCREEN:** Title card → dashboard

> "Most AI today waits for you to ask. The next generation doesn't. Agent
> Atlas is an autonomous background task operator: give it a messy, multi-step
> goal and it plans, executes with real tools, and writes the deliverable —
> while you do something else. The hard part is finishing the job asynchronously,
> and that's what this system is built for."

---

## [0:30–1:00] Architecture, in brief

**SCREEN:** docs/architecture.svg

> "Three ideas. One: the agent's position lives in Firestore, not chat history
> — a durable step ledger that survives restarts. Two: tasks sit in a Firestore
> queue, and a Cloud Scheduler cron wakes a Cloud Run worker to drain it. Three:
> on every wake-up, the system prompt is re-rendered from that durable state.
> The container scales to zero; the work never forgets where it is."

---

## [1:00–2:15] Live execution demo

**SCREEN:** dashboard → submit goal → trigger a run

> "Live now. I'll submit a goal: research the top 5 open-source AI coding
> agents and write competitive_analysis.md. The planner produces five steps.
> I'll trigger a run — normally the scheduler does this every two minutes.
> Watch the event log: the agent searches the web, fetches pages, remembers
> findings, and writes the deliverable. Every tool call is persisted to
> Firestore."

**SCREEN:** `GET /api/tasks/{id}` → task completed with result
**SCREEN:** list `deliverables/`, show the report

> "Task complete. The report is on disk, the event log shows every action, and
> the outcome is recorded."

---

## [2:15–2:45] Data pipeline demo

**SCREEN:** submit the CSV-cleaning goal → run → show cleaned.csv

> "Second scenario: a messy CSV with empty rows and stray whitespace. Atlas
> ingests it, cleans it, and writes cleaned.csv — a real transformation, not a
> summary."

---

## [2:45–3:20] Durable memory and steering

**SCREEN:** earlier research task → send "focus on pricing data"

> "Because progress and findings live in Firestore, you can steer mid-flight —
> 'focus on pricing data' — and Atlas adapts, retaining what it learned
> earlier. The same mechanism works across days, not just minutes."

---

## [3:20–3:50] Proof of Google Cloud deployment

**SCREEN:** Cloud Console → Cloud Run → atlas service
**SCREEN:** Firestore console → atlas collections (tasks, steps, events)

> "This is the point: it runs on Google Cloud. Cloud Run is deployed and scales
> to zero between ticks, so it costs almost nothing at rest. Here is the
> Firestore ledger — tasks, steps, events, memory — the durable source of
> truth."

---

## [3:50–4:00] Close

> "Atlas is a Taskmaster: it plans, acts, remembers, and finishes — autonomously,
> in the background. Built with Google ADK, Gemini 3.5, Cloud Run, and
> Firestore. The repository and spin-up instructions are below; it runs locally
> with zero GCP in two minutes. Thank you."

---

## Production notes

- 1920×1080, 30 fps; clean voiceover; no background music.
- Record the execution demo in one take (unedited).
- Prep: export `GEMINI_API_KEY` and run the dashboard locally
  (`deploy/local.sh`), or use the deployed Cloud Run URL.
- After recording, delete the scheduler job to stop cron invocations
  (`gcloud scheduler jobs delete atlas-cron`).

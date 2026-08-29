# Agent Atlas — ~4-Minute Demo Video Script

**Total runtime:** ~4:00 · **Format:** screen recording + voiceover
**Tone:** confident, crisp, live — no cuts in the execution demo

---

## [0:00–0:30] Hook + problem

**SCREEN:** Title card → dashboard empty state

> "Most AI today waits for you to ask. The next generation doesn't. Meet Agent
> Atlas — an autonomous background task operator. Give it a messy, multi-step
> goal, and it plans it, executes it with real tools, and writes the
> deliverable — while you do something else."

---

## [0:30–1:00] The architecture, fast

**SCREEN:** Architecture diagram (docs/architecture.svg)

> "Three ideas make this work. One: the agent's position lives in Firestore,
> not chat history — a durable step ledger that survives restarts. Two: tasks
> sit in a Firestore queue and a Cloud Scheduler cron wakes a Cloud Run worker
> to drain it. Three: every wake-up, the agent's system prompt is re-rendered
> from that durable state. The container can scale to zero; the work never
> forgets where it is."

---

## [1:00–2:15] LIVE demo — the money shot

**SCREEN:** Dashboard → paste a goal → submit → **Run a turn**

> "Let's do it live. I'll paste a goal: *research the top 5 open-source AI
> coding agents and write competitive_analysis.md.* Submit. Watch the plan —
> five steps. Now I'll trigger a run — normally Cloud Scheduler does this every
> two minutes. Watch the event log: the agent searches the web, fetches pages,
> remembers findings, and writes the deliverable — step by step, persisted to
> Firestore after every tool call."

**SCREEN:** show `GET /api/tasks/{id}` with the completed task + `result`
**SCREEN:** `ls deliverables/` and `cat competitive_analysis.md` (head)

> "Task complete. The report is on disk, the event log shows every action, and
> the result is recorded — proof it really happened."

---

## [2:15–2:45] Second demo: the data pipeline

**SCREEN:** submit the CSV-cleaning example → run → show cleaned.csv

> "Now the data-pipeline side. A messy CSV: empty rows, stray whitespace. Atlas
> ingests it, cleans it, and writes cleaned.csv — a real transformation, not a
> summary."

---

## [2:45–3:20] Durable memory + steering

**SCREEN:** switch to the earlier research task → send message "focus on pricing data"

> "And because progress and findings live in Firestore, you can steer mid-flight
> — 'focus on pricing data' — and Atlas adapts, remembering what it learned
> earlier. Same pattern works across days, not just minutes."

---

## [3:20–3:50] Proof it runs on Google Cloud

**SCREEN:** Google Cloud Console → Cloud Run → atlas service (health, region)
**SCREEN:** Firestore console → atlas collection → task docs + step docs

> "This is the whole point: it runs on Google Cloud. Cloud Run is live — it
> scales to zero between ticks, so it costs almost nothing. Here's the Firestore
> ledger — tasks, steps, events, memory — the durable source of truth."

---

## [3:50–4:00] Close

> "Atlas is a Taskmaster: it plans, acts, remembers, and finishes — autonomously,
> in the background. Built with Google ADK, Gemini 3.5, Cloud Run, and
> Firestore. Repo and spin-up instructions are below — it runs locally with zero
> GCP in two minutes. Thank you."

---

## Production notes

- **Recording:** 1920×1080, 30fps; OBS or QuickTime; clean voiceover.
- **Do it live:** record the execution demo in one take (unedited), per the
  brief's "live, unedited demo" preference; screen-record the Cloud Run and
  Firestore consoles straight after.
- **Prep:** warm the Gemini API key; run the dashboard locally (`deploy/local.sh`)
  or against the deployed Cloud Run URL.
- **Cost:** deploy, record, then delete the scheduler job to stop cron costs.

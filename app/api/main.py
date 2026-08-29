"""FastAPI service: submit goals, watch them execute, steer with messages.

Routes
------
* POST /api/tasks            submit a new goal (planned + queued immediately)
* GET  /api/tasks            list tasks
* GET  /api/tasks/{id}       task + plan + event log
* POST /api/tasks/{id}/run   execute one agent turn now (demo-friendly)
* POST /api/tasks/{id}/message  steer an existing task (chat)
* POST /cron/run             Cloud Scheduler hook: drain the queue
* GET  /healthz              liveness probe
* GET  /                     the dashboard (static web/)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent import build_agent, new_session_service
from ..config import get
from ..planner import make_plan
from ..state_schema import TaskStatus
from ..store import get_store
from ..worker import post_user_message, run_scheduled_cycle

logger = logging.getLogger(__name__)

store = get_store()
agent = build_agent()
session_service = new_session_service()

app = FastAPI(title="Agent Atlas", version="1.0.0")
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


class CreateTaskBody(BaseModel):
    goal: str
    title: Optional[str] = None


class MessageBody(BaseModel):
    message: str


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "model": get("gemini_model"), "store": get("store_backend")}


@app.post("/api/tasks")
def create_task(body: CreateTaskBody) -> dict:
    goal = body.goal.strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")
    task_id = store.create_task(goal=goal, title=body.title)
    store.update_task(task_id, status=TaskStatus.PLANNING.value)
    plan = make_plan(goal)
    store.set_plan(task_id, plan)
    store.update_task(task_id, status=TaskStatus.PENDING.value)
    store.record_event(task_id, "plan", {"steps": len(plan)})
    return {"task_id": task_id, "plan": plan}


@app.get("/api/tasks")
def list_tasks() -> dict:
    return {"tasks": store.list_tasks()}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task": task,
        "plan": store.get_plan(task_id),
        "events": store.get_events(task_id),
    }


@app.post("/api/tasks/{task_id}/run")
async def run_task_now(task_id: str) -> dict:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.get("status") in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
        return {"task_id": task_id, "status": task.get("status"), "note": "terminal state; nothing to run"}
    store.update_task(task_id, status=TaskStatus.PENDING.value)
    from ..worker import run_one_turn  # local import to keep startup light

    try:
        await run_one_turn(store, build_runner_for(task_id), task)
    except Exception as exc:  # noqa: BLE001 - same graceful path as the worker
        logger.exception("Task %s failed during manual run", task_id)
        store.record_event(task_id, "error", {"message": str(exc)})
        store.update_task(
            task_id,
            status=TaskStatus.FAILED.value,
            result=f"Execution error: {exc}",
        )
    return {"task_id": task_id, "status": store.get_task(task_id).get("status")}


@app.post("/api/tasks/{task_id}/message")
async def message_task(task_id: str, body: MessageBody) -> dict:
    return await post_user_message(store, agent, session_service, task_id, body.message)


@app.post("/cron/run")
async def cron_run() -> dict:
    summary = await run_scheduled_cycle(store, agent, session_service)
    logger.info("cron cycle summary=%s", summary)
    return summary


def build_runner_for(task_id: str):
    from ..agent import build_runner

    return build_runner(agent, session_service)


# Dashboard (static). Mounted last so /api and /cron routes win.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
else:  # pragma: no cover - fallback when running from a different cwd
    @app.get("/")
    def _root() -> FileResponse:
        return FileResponse(str(WEB_DIR / "index.html"))
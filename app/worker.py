"""The async executor.

Cloud Scheduler pings ``POST /cron/run`` on an interval; the endpoint calls
``run_scheduled_cycle`` which:

1. claims up to ``spring_batch`` PENDING tasks atomically from Firestore,
2. for each task, runs agent turns against the ADK runner, re-seeding the
   session state from the Firestore ledger on every wake-up,
3. persists every event back to the ledger, and
4. re-queues unfinished tasks so the *next* tick continues where they stopped.

Containers can scale to zero between ticks: nothing about a task's progress
lives in container memory.
"""

from __future__ import annotations

import logging
from typing import Any

from .agent import build_runner, run_turn
from .config import get
from .state_schema import TaskStatus

logger = logging.getLogger(__name__)

USER_ID = "atlas-worker"


def _plan_text(plan: list[dict]) -> str:
    if not plan:
        return "No plan yet — form one yourself, then act."
    return "\n".join(
        f"{i}. [{p.get('kind', 'research')}] {p.get('title', '')}" for i, p in enumerate(plan)
    )


def _state_delta(store: Any, task: dict, plan: list[dict]) -> dict:
    return {
        "task_id": task["id"],
        "goal": task.get("goal", ""),
        "plan": _plan_text(plan),
        "current_step": int(task.get("current_step", 0)),
        "total_steps": len(plan),
        "memory_scope": f"task:{task['id']}",
    }


async def run_one_turn(store: Any, runner: Any, task: dict) -> dict:
    """Run a single agent turn for a claimed task and persist the event log."""
    task_id = task["id"]
    plan = store.get_plan(task_id)
    events = await run_turn(
        runner,
        user_id=USER_ID,
        session_id=task_id,
        message=(
            "Continue executing the plan. Make real progress on the current step "
            "with your tools, then persist progress with record_step. If every "
            "step is done, call complete_task."
        ),
        state_delta=_state_delta(store, task, plan),
    )
    for ev in events:
        store.record_event(task_id, "agent", ev, index=int(task.get("current_step", 0)))
    return {"task_id": task_id, "events": len(events)}


async def run_scheduled_cycle(store: Any, agent: Any, session_service: Any) -> dict:
    """Drain the Firestore queue: process tasks until budget or empty queue."""
    runner = build_runner(agent, session_service)
    batch = max(1, int(get("spring_batch")))
    max_turns = max(1, int(get("max_turns_per_step")))
    max_steps = max(1, int(get("max_steps_per_task")))

    processed = 0
    turns_used = 0
    summary = {"claimed": 0, "completed": 0, "failed": 0, "requeued": 0, "turns": 0}

    for _ in range(batch):
        task = store.claim_next_task(batch=1)
        if task is None:
            break
        summary["claimed"] += 1
        processed += 1
        task_id = task["id"]

        turns_for_this_task = 0
        while True:
            task = store.get_task(task_id) or task
            if task.get("status") in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
                if task.get("status") == TaskStatus.COMPLETED.value:
                    summary["completed"] += 1
                break
            if int(task.get("attempts", 0)) > max_steps:
                store.update_task(task_id, status=TaskStatus.FAILED.value, result="Exceeded step budget.")
                summary["failed"] += 1
                break
            if turns_for_this_task >= max_turns:
                store.update_task(task_id, status=TaskStatus.PENDING.value)
                summary["requeued"] += 1
                break

            try:
                await run_one_turn(store, runner, task)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Task %s errored", task_id)
                store.record_event(task_id, "error", {"message": str(exc)})
                store.update_task(task_id, status=TaskStatus.FAILED.value, result=f"Execution error: {exc}")
                summary["failed"] += 1
                break
            turns_for_this_task += 1
            turns_used += 1
            summary["turns"] += 1

            if turns_used >= batch * max_turns:
                # Budget exhausted for this tick; leave remaining task queued.
                store.update_task(task_id, status=TaskStatus.PENDING.value)
                summary["requeued"] += 1
                break

    summary["processed"] = processed
    return summary


async def post_user_message(store: Any, agent: Any, session_service: Any, task_id: str, message: str) -> dict:
    """Run a human-steered turn against an existing task (live chat/demo mode)."""
    task = store.get_task(task_id)
    if task is None:
        return {"status": "error", "message": "Task not found."}
    runner = build_runner(agent, session_service)
    plan = store.get_plan(task_id)
    events = await run_turn(
        runner,
        user_id=USER_ID,
        session_id=task_id,
        message=message,
        state_delta=_state_delta(store, task, plan),
    )
    for ev in events:
        store.record_event(task_id, "user_turn", ev, index=int(task.get("current_step", 0)))
    fresh = store.get_task(task_id)
    return {"status": "ok", "task": fresh, "events": events}
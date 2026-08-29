"""Ledger tools: how Atlas persists progress durably during a run.

These bridge the ADK session (reasoning context) and the Firestore ledger
(source of truth). The task_id and current position travel in session state
(``tool_context.state``), which the worker re-seeds from Firestore on every
wake-up — so progress never lives only in ephemeral chat history.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from ..state_schema import StepStatus, TaskStatus


def _task_id(ctx: ToolContext | None) -> str:
    return str(ctx.state.get("task_id") or "") if ctx else ""


def _resolve_store(ctx: ToolContext | None):
    """Use the store bound in state when present, else the configured singleton."""
    if ctx is not None and ctx.state.get("store_ref") is not None:
        return ctx.state.get("store_ref")
    from ..store import get_store  # deferred to avoid import cycles

    return get_store()


def record_step(
    index: int,
    status: str,
    note: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Record the outcome of one workflow step in the durable ledger.

    Args:
        index: The step number (0-based) this call refers to.
        status: One of 'DONE', 'IN_PROGRESS', 'BLOCKED'.
        note: A short human-readable summary of what happened for this step.

    Marks the step and, when DONE, advances the task's `current_step` so the
    next execution turn knows exactly where it left off.
    """
    task_id = _task_id(tool_context)
    step_status = StepStatus(status.upper())
    store = _resolve_store(tool_context)
    result = {
        "status": "ok",
        "task_id": task_id,
        "index": index,
        "step_status": step_status.value,
    }
    store.set_step_status(task_id, int(index), step_status, note or "")
    if step_status == StepStatus.DONE and tool_context is not None:
        current = int(tool_context.state.get("current_step", 0))
        nxt = max(current, int(index) + 1)
        tool_context.state["current_step"] = nxt
        store.update_task(task_id, current_step=nxt)
        result["current_step"] = nxt
    return result


def complete_task(
    summary: str,
    deliverables: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Mark the whole task COMPLETED with a final summary + deliverables.

    Args:
        summary: The final wrap-up the user / UI should see.
        deliverables: Comma-separated deliverable filenames (optional).
    """
    task_id = _task_id(tool_context)
    store = _resolve_store(tool_context)
    store.update_task(
        task_id,
        status=TaskStatus.COMPLETED.value,
        result=summary,
        deliverables=[d.strip() for d in deliverables.split(",") if d.strip()],
    )
    if tool_context is not None:
        tool_context.state["current_step"] = int(tool_context.state.get("total_steps", 0))
    return {"status": "ok", "task_id": task_id, "result": summary}


def set_goal_overview(
    overview: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Save a crisp one-paragraph overview of the goal for the whole session.

    Args:
        overview: A concise framing of the goal and the plan ahead.

    Stored to durable memory keyed by the task, so a worker that picks up the
    task days later re-starts from the same understanding.
    """
    task_id = _task_id(tool_context)
    store = _resolve_store(tool_context)
    store.remember(f"task:{task_id}", "overview", overview)
    return {"status": "ok", "task_id": task_id}

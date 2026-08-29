"""Durable long-term memory tools.

These let Atlas keep findings across *weeks* of asynchronous operation — the
"Memory Bank" idea from the Fortified Enterprise Fleet track — while still
working perfectly in the Taskmaster context.
"""

from __future__ import annotations

from google.adk.tools import ToolContext


def _scope(ctx: ToolContext | None) -> str:
    task_id = str(ctx.state.get("task_id") or "global") if ctx else "global"
    return (ctx.state.get("memory_scope") if ctx else None) or f"task:{task_id}"


def _resolve_store(ctx: ToolContext | None):
    if ctx is not None and ctx.state.get("store_ref") is not None:
        return ctx.state.get("store_ref")
    from ..store import get_store  # deferred to avoid import cycles

    return get_store()


def remember(
    key: str,
    value: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """Persist a fact/finding to long-term memory for this project.

    Args:
        key: A short slug naming the fact, e.g. 'competitor_names'.
        value: The fact or finding to remember.

    Survives container restarts and scale-to-zero, so later sessions can recall it.
    """
    store = _resolve_store(tool_context)
    scope = _scope(tool_context)
    store.remember(scope, key, value)
    return {"status": "ok", "key": key, "scope": scope}


def recall(
    key: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """Retrieve remembered facts. Empty `key` returns everything for this project.

    Args:
        key: The fact slug to look up, or '' to dump all facts.

    Returns the stored value(s).
    """
    store = _resolve_store(tool_context)
    scope = _scope(tool_context)
    if key:
        value = store.recall(scope, key)
        return {
            "status": "ok",
            "key": key,
            "found": value is not None,
            "value": value,
        }
    return {"status": "ok", "memory": store.recall_all(scope)}
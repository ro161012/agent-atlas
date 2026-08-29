"""The Atlas ADK agent.

One coordinator ``Agent`` (LlmAgent) equipped with hands-on tools. Its system
instruction is a template over *session state variables* — {goal}, {plan},
{current_step}, {task_id} — that the worker re-seeds from Firestore on every
wake-up. The model always knows its exact position from state, never by
replaying chat history (the checkpoint-and-resume pattern from ADK's
long-running agents guide).

Runs:
  * async:   Runner.run_async() driven by the worker (see worker.py)
  * sync UI: the FastAPI /api/chat endpoint for live demos
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .config import get
from .tools import all_tools

logger = logging.getLogger(__name__)

APP_NAME = "atlas"


INSTRUCTION = """You are **Atlas**, an autonomous background task operator. You take a goal,
make a plan, and *actually carry it out* — researching, transforming data, and
writing deliverables while the user does something else. You are not a chatbot:
your job is to make real progress every turn.

## Your current assignment (from durable state — trust it, not chat history)
- Goal: {goal?}
- Plan: {plan?}
- Current step index: {current_step?} of {total_steps?}
- Task id: {task_id?}

## How to work
1. Read the plan. Identify the single most valuable next action for the
   current step and execute it with your tools. Prefer real action over prose.
2. Do not skip ahead: finish the current step before advancing it.
3. After finishing a step, call `record_step(index, "DONE", note)` to persist
   progress in the durable ledger, then continue to the next step.
4. If a step needs information you don't have: web_search → fetch_url →
   ingest_document → remember/recall, in that order.
5. Data tasks: parse with transform_data (head / summary / clean / filter /
   sort / keep / count), then write the final artifact with
   `write_deliverable`.
6. Persist notable findings with `remember` so a future wake-up has context.
7. When every step is done, call `complete_task(summary, deliverables)` and
   stop. Never call complete_task early.
8. If a step cannot be completed, mark it BLOCKED with record_step and ask the
   user a single clarifying question. Never fabricate results.

## Ground rules
- Only report what your tools actually returned.
- Keep tool notes tight and factual; no marketing language.
- You may use {current_step?} to decide what to do; if it is 0 and the plan is
  empty, produce a sensible plan of action yourself before acting.
"""


def initialize_atlas_state(callback_context: CallbackContext) -> None:
    """Seed session state defaults before the first model call of a turn."""
    state = callback_context.state
    state.setdefault("goal", "")
    state.setdefault("plan", [])
    state.setdefault("current_step", 0)
    state.setdefault("total_steps", 0)
    state.setdefault("task_id", "chat")
    state.setdefault("memory_scope", "global")


def build_agent() -> Agent:
    """Construct the Atlas coordinator agent.

    Tools resolve the durable store themselves (get_store()); nothing
    non-serializable is ever placed in ADK session state.
    """
    return Agent(
        name="atlas",
        model=Gemini(model=get("gemini_model")),
        instruction=INSTRUCTION,
        tools=all_tools(),
        before_agent_callback=initialize_atlas_state,
    )


def new_session_service() -> InMemorySessionService:
    return InMemorySessionService()


def build_runner(agent: Agent, session_service: InMemorySessionService) -> Runner:
    # ADK 2.x: pass the raw agent via `agent=` (requires `app_name`) — passing it
    # as `app=` would expect a full App wrapper with context_cache_config.
    return Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
        auto_create_session=True,
    )


async def run_turn(
    runner: Runner,
    user_id: str,
    session_id: str,
    message: str,
    state_delta: dict | None = None,
) -> list[dict]:
    """Run one agent turn, returning a lightweight event log for the ledger.

    `state_delta` is applied to session state before the model call — this is
    how the worker restores {goal}, {plan}, {current_step} from Firestore on
    every wake-up.
    """
    events: list[dict] = []
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=message)],
    )
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta=state_delta or {},
    ):
        record = _summarize_event(event)
        if record:
            events.append(record)
    return events


def _summarize_event(event: Any) -> dict | None:
    """Reduce an ADK event to a JSON-safe summary for the task log."""
    try:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", []) or []
        text = " ".join(
            getattr(p, "text", "") or "" for p in parts if hasattr(p, "text")
        )
        fcalls = getattr(event, "function_calls", None) or []
        calls = []
        for fc in fcalls:
            name = getattr(fc, "name", "")
            args = getattr(fc, "args", {})
            calls.append({"name": name, "args": _jsonable(args)})
        if not text and not calls:
            return None
        return {
            "kind": "event",
            "role": getattr(getattr(event, "content", None), "role", None),
            "text": text[:4000],
            "function_calls": calls,
        }
    except Exception:  # noqa: BLE001 - logging must never break a run
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        import json

        return json.loads(json.dumps(value, default=str))
    except Exception:  # noqa: BLE001
        return str(value)
"""Goal decomposition: turn a fuzzy request into a durable step plan.

The planner is deliberately *cheap and deterministic by default* so a demo
works with zero configuration. When GEMINI_API_KEY is set it asks Gemini to
refine the plan into a tighter step list; any failure falls back to the
heuristic so the pipeline never blocks on the model.
"""

from __future__ import annotations

import json
import logging

from .config import get
from .state_schema import StepKind

logger = logging.getLogger(__name__)

# A generic, always-safe plan shape for unstructured goals.
_FALLBACK_PLAN = [
    {"kind": StepKind.RESEARCH.value, "title": "Clarify the goal and gather the inputs you already have"},
    {"kind": StepKind.RESEARCH.value, "title": "Research the domain and collect the facts needed"},
    {"kind": StepKind.TRANSFORM.value, "title": "Process / transform any data or documents involved"},
    {"kind": StepKind.DELIVER.value, "title": "Write the deliverable and summarize the outcome"},
]

_PLAN_PROMPT = """You are a ruthless task planner. Given a user's goal, produce a JSON
array of exactly 3-6 concrete, executable steps. Each step MUST be an object with:
- "kind": one of "research", "transform", "ingest", "memory", "deliver"
- "title": an imperative, specific instruction the executor can follow
Do NOT include meta steps like 'review the output'. Make every step independently
actionable with the tools available (web_search, fetch_url, ingest_document,
transform_data, remember/recall, write_deliverable). Return ONLY the JSON array.
Goal: {goal}"""


def make_plan(goal: str) -> list[dict]:
    """Return a list of step dicts for `goal`, model-refined when possible."""
    key = get("gemini_api_key")
    if key:
        try:
            from google import genai

            client = genai.Client(api_key=key)
            resp = client.models.generate_content(
                model=get("gemini_model"),
                contents=_PLAN_PROMPT.format(goal=goal),
                config={"response_mime_type": "application/json"},
            )
            raw = resp.text or ""
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return _sanitize(parsed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini planning failed, using fallback plan: %s", exc)
    return list(_FALLBACK_PLAN)


def _sanitize(steps: list[dict]) -> list[dict]:
    valid_kinds = {k.value for k in StepKind}
    out = []
    for s in steps[:8]:
        title = str(s.get("title", "")).strip()
        kind = str(s.get("kind", "research")).strip().lower()
        if title and kind in valid_kinds:
            out.append({"kind": kind, "title": title})
    return out or list(_FALLBACK_PLAN)
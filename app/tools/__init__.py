"""ADK function tools that give Atlas its hands in the world."""

from .web import fetch_url, web_search
from .data import (
    ingest_document,
    transform_data,
    write_deliverable,
    list_deliverables,
)
from .ledger import (
    record_step,
    complete_task,
    set_goal_overview,
)

ALL_TOOLS = [
    web_search,
    fetch_url,
    ingest_document,
    transform_data,
    write_deliverable,
    list_deliverables,
    record_step,
    complete_task,
    set_goal_overview,
]


def memory_tools() -> list:
    from .memory import recall, remember

    return [remember, recall]


def all_tools() -> list:
    return ALL_TOOLS + memory_tools()
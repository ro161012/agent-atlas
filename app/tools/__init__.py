"""ADK function tools that give Atlas its hands in the world."""

from .data import (
    ingest_document,
    list_deliverables,
    transform_data,
    write_deliverable,
)
from .ledger import (
    complete_task,
    record_step,
    set_goal_overview,
)
from .web import fetch_url, web_search

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

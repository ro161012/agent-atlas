"""Shared state-machine constants — the durable source of truth for a task.

The agent never *infers* where it is from chat history. It reads `current_step`
and statuses from Firestore (surfaced through ADK session `state_delta` and the
instruction template), the same checkpoint-and-resume pattern used for
long-running agents.
"""

from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "PENDING"  # submitted, queued for planning/execution
    PLANNING = "PLANNING"  # being decomposed into a step list
    RUNNING = "RUNNING"  # a worker is actively executing a turn
    WAITING = "WAITING"  # paused on an external/human dependency
    COMPLETED = "COMPLETED"  # all steps done, deliverable written
    FAILED = "FAILED"  # execution errored past retry budget
    CANCELLED = "CANCELLED"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


class StepKind(StrEnum):
    RESEARCH = "research"  # web_search / fetch_url
    TRANSFORM = "transform"  # data pipelines (CSV/JSON)
    INGEST = "ingest"  # read a document/url/table
    MEMORY = "memory"  # remember / recall durable context
    DELIVER = "deliver"  # write a deliverable / report

"""Full-lifecycle integration test (no network, no Gemini).

Simulates what the ADK agent does on each wake-up: claim a task, execute tools,
persist durable progress via the ledger, and complete. Exercises the real
tool + ledger + store code paths.
"""

import os
import tempfile

# Point config at a temp dir BEFORE importing any app modules (config is cached).
_ROOT = tempfile.mkdtemp(prefix="atlas_int_")
os.environ["STORE_BACKEND"] = "local"
os.environ["LOCAL_STORE_PATH"] = _ROOT

from app.state_schema import StepStatus, TaskStatus
from app.store import LocalStore
from app.tools.data import transform_data, write_deliverable
from app.tools.ledger import complete_task, record_step
from app.tools.memory import recall, remember


class FakeCtx:
    """Minimal stand-in for ADK ToolContext (just the state dict)."""

    def __init__(self, state: dict):
        self.state = state


def test_full_task_lifecycle():
    store = LocalStore(_ROOT)
    task_id = store.create_task("Clean a CSV and write a report")

    # 1. plan + claim (what the API + worker do)
    store.set_plan(
        task_id,
        [
            {"kind": "transform", "title": "Clean the CSV"},
            {"kind": "deliver", "title": "Write report.md"},
        ],
    )
    claimed = store.claim_next_task()
    assert claimed["id"] == task_id
    assert store.get_task(task_id)["status"] == TaskStatus.RUNNING.value

    ctx = FakeCtx({"task_id": task_id, "current_step": 0, "total_steps": 2})

    # 2. step 0: transform the messy CSV, persist progress
    messy = "name,age,city\nAlice,34,NYC\nBob,22,LA\n,29,NYC\nCarol, 41, SF "
    result = transform_data(messy, action="clean")
    assert result["status"] == "success"
    step = record_step(0, "DONE", "cleaned the CSV", tool_context=ctx)
    assert step["current_step"] == 1
    assert store.get_task(task_id)["current_step"] == 1
    assert store.get_plan(task_id)[0]["status"] == StepStatus.DONE.value

    # 3. durable memory
    remember("competitors", "A, B, C", tool_context=ctx)
    assert recall("competitors", tool_context=ctx)["value"] == "A, B, C"

    # 4. step 1: write the deliverable, complete the task
    out = write_deliverable("report.md", "# Report\n- cleaned rows")
    assert out["status"] == "success"
    record_step(1, "DONE", "wrote report", tool_context=ctx)
    complete_task("All done", "report.md", tool_context=ctx)

    task = store.get_task(task_id)
    assert task["status"] == TaskStatus.COMPLETED.value
    assert task["current_step"] == 2
    assert task["deliverables"] == ["report.md"]
    assert "All done" in task["result"]


def test_transform_actions():
    rows = '[{"a": 1, "b": "x"}, {"a": 2, "b": "y"}, {"a": 3, "b": "x"}]'
    filtered = transform_data(rows, action="filter", field="b", value="x")
    assert filtered["status"] == "success"
    import json

    assert len(json.loads(filtered["data"])) == 2
    summary = transform_data(rows, action="summary")
    assert "a" in summary["data"]

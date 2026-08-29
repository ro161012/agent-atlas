"""Unit tests for the durable ledger using the dependency-free LocalStore."""

import tempfile

from app.state_schema import StepStatus, TaskStatus
from app.store import LocalStore


def _fresh_store() -> LocalStore:
    return LocalStore(tempfile.mkdtemp(prefix="atlas_test_"))


def test_create_and_get_task():
    store = _fresh_store()
    task_id = store.create_task("Do the thing", title="Thing")
    task = store.get_task(task_id)
    assert task["title"] == "Thing"
    assert task["status"] == TaskStatus.PENDING.value
    assert task["current_step"] == 0


def test_claim_marks_running_and_advances_attempts():
    store = _fresh_store()
    task_id = store.create_task("First")
    store.create_task("Second")
    claimed = store.claim_next_task()
    assert claimed is not None
    assert claimed["id"] == task_id
    assert store.get_task(task_id)["status"] == TaskStatus.RUNNING.value
    assert store.get_task(task_id)["attempts"] == 1
    # second claim gets the other task
    assert store.claim_next_task()["id"] != task_id
    # queue is now empty
    assert store.claim_next_task() is None


def test_plan_and_step_status():
    store = _fresh_store()
    task_id = store.create_task("Plan me")
    steps = [
        {"kind": "research", "title": "Search"},
        {"kind": "deliver", "title": "Write report"},
    ]
    store.set_plan(task_id, steps)
    plan = store.get_plan(task_id)
    assert [p["title"] for p in plan] == ["Search", "Write report"]
    store.set_step_status(task_id, 0, StepStatus.DONE, note="searched")
    assert store.get_plan(task_id)[0]["status"] == StepStatus.DONE.value


def test_memory_roundtrip():
    store = _fresh_store()
    store.remember("task:abc", "competitors", "A, B, C")
    assert store.recall("task:abc", "competitors") == "A, B, C"
    assert store.recall("task:abc", "missing") is None
    assert store.recall_all("task:abc") == {"competitors": "A, B, C"}


def test_events_ordered():
    store = _fresh_store()
    task_id = store.create_task("Log me")
    store.record_event(task_id, "plan", {"steps": 2})
    store.record_event(task_id, "agent", {"text": "hi"})
    events = store.get_events(task_id)
    assert [e["kind"] for e in events] == ["plan", "agent"]

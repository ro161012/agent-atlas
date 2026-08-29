"""Durable task ledger.

Two backends behind one interface:

* ``FirestoreStore``  - the production path. Every task, step, run event and
  piece of long-term memory lives in Cloud Firestore so a Cloud Run container
  can scale to zero and a worker pick up exactly where a previous one left off.

* ``LocalStore``      - a dependency-free JSON-file backend so the whole system
  can be demoed locally with *no* GCP account (STORE_BACKEND=local).

Design notes:
  * Tasks are claimed with an atomic Firestore transaction so multiple Cloud Run
    instances never execute the same task twice.
  * Nothing is ever inferred from chat history; the agent's position comes from
    these documents.
"""

from __future__ import annotations

import datetime
import itertools
import json
import os
import uuid
from typing import Any, Optional

from .config import get
from .state_schema import StepStatus, TaskStatus


def _now() -> str:
    # Microsecond precision so same-instant writes still order deterministically.
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# Firestore backend
# --------------------------------------------------------------------------
class FirestoreStore:
    """Production ledger backed by Cloud Firestore."""

    def __init__(self, project: Optional[str] = None, prefix: str = "atlas"):
        from google.cloud import firestore  # lazy import so local demos work w/o dep

        kwargs = {"database": "(default)"}
        if project:
            kwargs["project"] = project
        self._db = firestore.Client(**kwargs)
        self._prefix = (prefix or "atlas").strip("/")
        self._tasks = self._db.collection(f"{self._prefix}/tasks/task")
        self._steps = self._db.collection(f"{self._prefix}/tasks/task_steps")
        self._events = self._db.collection(f"{self._prefix}/tasks/task_events")
        self._memory = self._db.collection(f"{self._prefix}/memory/kv")
        # Monotonic per-process sequence: deterministic FIFO tie-break when two
        # tasks share the same wall-clock timestamp (Windows timer ~15ms).
        self._seq = itertools.count()

    # ---- tasks ------------------------------------------------------------
    def create_task(self, goal: str, title: str = "", meta: dict | None = None) -> str:
        task_id = _new_id("task")
        self._tasks.document(task_id).set(
            {
                "id": task_id,
                "title": title or goal[:64],
                "goal": goal,
                "status": TaskStatus.PENDING.value,
                "current_step": 0,
                "total_steps": 0,
                "attempts": 0,
                "result": "",
                "deliverables": [],
                "created_at": _now(),
                "updated_at": _now(),
                "seq": next(self._seq),
                "meta": meta or {},
            }
        )
        return task_id

    def get_task(self, task_id: str) -> Optional[dict]:
        ref = self._tasks.document(task_id).get()
        return ref.to_dict() if ref.exists else None

    def update_task(self, task_id: str, **fields) -> None:
        fields["updated_at"] = _now()
        self._tasks.document(task_id).set(
            fields, merge=True
        )

    def list_tasks(self, limit: int = 50) -> list[dict]:
        docs = (
            self._tasks.order_by("created_at", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        return [d.to_dict() for d in docs]

    def claim_next_task(self, batch: int = 1) -> Optional[dict]:
        """Atomically pull the oldest PENDING/planready task and mark RUNNING."""
        try:
            return self._claim_via_transaction(batch)
        except Exception:
            # Fall back to a best-effort single claim if the transaction hiccups.
            return self._claim_non_atomic()

    def _claim_via_transaction(self, batch: int) -> Optional[dict]:
        from google.cloud import firestore  # deferred so local backend needs no dep

        transaction = self._db.transaction()
        claimed: list[dict] = []

        @firestore.transactional
        def _claim(tr):
            # NOTE: no order_by here on purpose — equality + order_by on
            # different fields would need a composite index on a fresh project.
            # We fetch a superset and sort in Python instead.
            query = (
                self._tasks.where("status", "==", TaskStatus.PENDING.value)
                .limit(batch * 8)
            )
            snaps = sorted(
                tr.get(query),
                key=lambda s: (
                    (s.to_dict() or {}).get("created_at", ""),
                    (s.to_dict() or {}).get("seq", 0),
                ),
            )[:batch]
            for snap in snaps:
                data = dict(snap.to_dict() or {})
                data["attempts"] = int(data.get("attempts", 0)) + 1
                data["status"] = TaskStatus.RUNNING.value
                data["updated_at"] = _now()
                tr.update(snap.reference, data)
                claimed.append(data)
            return claimed

        _claim(transaction)
        return claimed[0] if claimed else None

    def _claim_non_atomic(self) -> Optional[dict]:
        query = self._tasks.where("status", "==", TaskStatus.PENDING.value).limit(20)
        snaps = sorted(
            query.stream(),
            key=lambda s: (
                (s.to_dict() or {}).get("created_at", ""),
                (s.to_dict() or {}).get("seq", 0),
            ),
        )
        if not snaps:
            return None
        snap = snaps[0]
        data = dict(snap.to_dict() or {})
        self.update_task(snap.id, status=TaskStatus.RUNNING.value)
        return data

    def touch(self, task_id: str) -> None:
        self.update_task(task_id, status=TaskStatus.RUNNING.value)

    # ---- steps ------------------------------------------------------------
    def set_plan(self, task_id: str, steps: list[dict]) -> None:
        total = len(steps)
        self.update_task(task_id, total_steps=total)
        for i, step in enumerate(steps):
            doc = dict(step)
            doc["task_id"] = task_id
            doc["index"] = i
            doc.setdefault("status", StepStatus.PENDING.value)
            self._steps.document(f"{task_id}_{i}").set(doc, merge=True)
        # Drop any steps beyond the new plan (re-plan case).
        for snap in self._steps.where("task_id", "==", task_id).stream():
            idx = snap.id.rsplit("_", 1)[-1]
            if idx.isdigit() and int(idx) >= total:
                self._steps.document(snap.id).delete()

    def get_plan(self, task_id: str) -> list[dict]:
        docs = list(self._steps.where("task_id", "==", task_id).stream())
        docs.sort(key=lambda d: int((d.to_dict() or {}).get("index", 0)))
        return [d.to_dict() for d in docs]

    def set_step_status(self, task_id: str, index: int, status: StepStatus, note: str = "") -> None:
        self._steps.document(f"{task_id}_{index}").set(
            {
                "task_id": task_id,
                "index": index,
                "status": status.value,
                "note": note,
                "updated_at": _now(),
            },
            merge=True,
        )

    def record_event(self, task_id: str, kind: str, payload: Any, index: int = -1) -> None:
        self._events.document(f"{_new_id('ev')}").set(
            {
                "task_id": task_id,
                "kind": kind,
                "step_index": index,
                "payload": payload,
                "ts": _now(),
                "seq": next(self._seq),
            }
        )

    def get_events(self, task_id: str, limit: int = 200) -> list[dict]:
        docs = list(self._events.where("task_id", "==", task_id).stream())
        docs.sort(
            key=lambda d: (
                (d.to_dict() or {}).get("ts", ""),
                (d.to_dict() or {}).get("seq", 0),
            )
        )
        return [d.to_dict() for d in docs][-limit:]

    # ---- durable memory ----------------------------------------------------
    def remember(self, scope: str, key: str, value: Any) -> None:
        self._memory.document(f"{scope}_{key}").set(
            {"scope": scope, "key": key, "value": value, "ts": _now()}
        )

    def recall(self, scope: str, key: str) -> Any:
        ref = self._memory.document(f"{scope}_{key}").get()
        return (ref.to_dict() or {}).get("value") if ref.exists else None

    def recall_all(self, scope: str, limit: int = 200) -> dict:
        out = {}
        for d in self._memory.where("scope", "==", scope).limit(limit).stream():
            data = d.to_dict() or {}
            out[data.get("key")] = data.get("value")
        return out


# --------------------------------------------------------------------------
# Local (JSON) backend for GCP-free demos
# --------------------------------------------------------------------------
class LocalStore:
    """A dependency-free file backend. Each doc is stored as one JSON file."""

    def __init__(self, root: str):
        self.root = root
        self._tasks_dir = os.path.join(root, "tasks")
        self._steps_dir = os.path.join(root, "steps")
        self._events_dir = os.path.join(root, "events")
        self._memory_dir = os.path.join(root, "memory")
        for d in (self._tasks_dir, self._steps_dir, self._events_dir, self._memory_dir):
            os.makedirs(d, exist_ok=True)
        # Monotonic per-process sequence: deterministic FIFO tie-break.
        self._seq = itertools.count()

    @staticmethod
    def _fid(*parts: str) -> str:
        """Build a filesystem-safe id. On Windows a ':' inside a filename would
        create an NTFS Alternate Data Stream (invisible to listdir), so we
        sanitize it here along with '/'."""
        return "_".join(p.replace("/", "_").replace(":", "_") for p in parts)

    def _path(self, folder: str, fid: str) -> str:
        return os.path.join(folder, fid + ".json")

    def _write(self, path: str, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def _read(self, path: str) -> Optional[dict]:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return None

    def create_task(self, goal: str, title: str = "", meta: dict | None = None) -> str:
        task_id = _new_id("task")
        self._write(
            self._path(self._tasks_dir, task_id),
            {
                "id": task_id,
                "title": title or goal[:64],
                "goal": goal,
                "status": TaskStatus.PENDING.value,
                "current_step": 0,
                "total_steps": 0,
                "attempts": 0,
                "result": "",
                "deliverables": [],
                "created_at": _now(),
                "updated_at": _now(),
                "seq": next(self._seq),
                "meta": meta or {},
            },
        )
        return task_id

    def get_task(self, task_id: str) -> Optional[dict]:
        return self._read(self._path(self._tasks_dir, task_id))

    def update_task(self, task_id: str, **fields) -> None:
        path = self._path(self._tasks_dir, task_id)
        data = self._read(path) or {}
        fields["updated_at"] = _now()
        data.update(fields)
        self._write(path, data)

    def list_tasks(self, limit: int = 50) -> list[dict]:
        out = []
        for fn in sorted(os.listdir(self._tasks_dir), reverse=True):
            if not fn.endswith(".json"):
                continue
            data = self._read(os.path.join(self._tasks_dir, fn))
            if data:
                out.append(data)
            if len(out) >= limit:
                break
        return out

    def claim_next_task(self, batch: int = 1) -> Optional[dict]:
        candidates = []
        for fn in os.listdir(self._tasks_dir):
            if not fn.endswith(".json"):
                continue
            data = self._read(os.path.join(self._tasks_dir, fn))
            if data and data.get("status") == TaskStatus.PENDING.value:
                candidates.append(data)
        # FIFO: oldest pending task first, matching the Firestore backend.
        candidates.sort(key=lambda d: (d.get("created_at", ""), d.get("seq", 0)))
        if not candidates:
            return None
        data = candidates[0]
        attempts = int(data.get("attempts", 0)) + 1
        self.update_task(
            data["id"],
            status=TaskStatus.RUNNING.value,
            attempts=attempts,
        )
        data["status"] = TaskStatus.RUNNING.value
        data["attempts"] = attempts
        return data

    def touch(self, task_id: str) -> None:
        self.update_task(task_id, status=TaskStatus.RUNNING.value)

    def set_plan(self, task_id: str, steps: list[dict]) -> None:
        self.update_task(task_id, total_steps=len(steps))
        for i, step in enumerate(steps):
            doc = dict(step)
            doc["task_id"] = task_id
            doc["index"] = i
            doc.setdefault("status", StepStatus.PENDING.value)
            self._write(self._path(self._steps_dir, self._fid(task_id, str(i))), doc)

    def get_plan(self, task_id: str) -> list[dict]:
        out = []
        for i in range(10000):
            data = self._read(self._path(self._steps_dir, self._fid(task_id, str(i))))
            if not data:
                break
            out.append(data)
        return out

    def set_step_status(self, task_id: str, index: int, status: StepStatus, note: str = "") -> None:
        path = self._path(self._steps_dir, self._fid(task_id, str(index)))
        data = self._read(path) or {"task_id": task_id, "index": index}
        data["status"] = status.value
        data["note"] = note
        data["updated_at"] = _now()
        self._write(path, data)

    def record_event(self, task_id: str, kind: str, payload: Any, index: int = -1) -> None:
        self._write(
            self._path(self._events_dir, self._fid(task_id, _new_id("ev"))),
            {
                "task_id": task_id,
                "kind": kind,
                "step_index": index,
                "payload": payload,
                "ts": _now(),
                "seq": next(self._seq),
            },
        )

    def get_events(self, task_id: str, limit: int = 200) -> list[dict]:
        out = []
        prefix = self._fid(task_id) + "_"
        for fn in os.listdir(self._events_dir):
            if not fn.startswith(prefix) or not fn.endswith(".json"):
                continue
            data = self._read(os.path.join(self._events_dir, fn))
            if data:
                out.append(data)
        out.sort(key=lambda d: (d.get("ts", ""), d.get("seq", 0)))
        return out[-limit:]

    def remember(self, scope: str, key: str, value: Any) -> None:
        self._write(
            self._path(self._memory_dir, self._fid(scope, key)),
            {"scope": scope, "key": key, "value": value, "ts": _now()},
        )

    def recall(self, scope: str, key: str) -> Any:
        data = self._read(self._path(self._memory_dir, self._fid(scope, key)))
        return (data or {}).get("value")

    def recall_all(self, scope: str, limit: int = 200) -> dict:
        out = {}
        prefix = self._fid(scope) + "_"
        for fn in os.listdir(self._memory_dir):
            if not fn.startswith(prefix) or not fn.endswith(".json"):
                continue
            data = self._read(os.path.join(self._memory_dir, fn))
            if data:
                out[data.get("key")] = data.get("value")
        return out


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------
def get_store() -> FirestoreStore | LocalStore:
    backend = get("store_backend").lower()
    if backend in ("local", "json", "file", "memory"):
        return LocalStore(get("local_store_path"))
    return FirestoreStore(project=get("firestore_project") or None, prefix=get("firestore_prefix"))
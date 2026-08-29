"""Document ingest + data transformation tools.

These give Atlas the "handles the heavy lifting of data pipelines and
representations" capability the brief asks for: pull raw data (CSV/JSON/text),
normalize it, run arbitrary transforms, and drop a clean deliverable.
"""

from __future__ import annotations

import csv
import io
import json
import os

import httpx

from ..config import get

# Deliverables are written under LOCAL_STORE_PATH/deliverables (or a shared
# volume in production). Swap for a GCS bucket in a hardened deployment.
_OUT_ROOT = os.path.join(get("local_store_path"), "deliverables")


def _ensure_out() -> str:
    os.makedirs(_OUT_ROOT, exist_ok=True)
    return _OUT_ROOT


def _parse_table(raw: str) -> list[dict]:
    """Best-effort parse of tabular data (JSON array of objects or CSV)."""
    raw = raw.strip()
    if raw.startswith("["):
        return json.loads(raw)
    csv_io = io.StringIO(raw)
    reader = csv.DictReader(csv_io)
    rows = [dict(r) for r in reader]
    return rows


def transform_data(
    raw: str | list[dict], action: str, field: str = "", value: str = "", keep: str = ""
) -> dict:
    """Transform tabular data (a JSON array of row-objects or a CSV string).

    Args:
        raw: The dataset to transform, as a JSON list of objects or a CSV string.
        action: One of: 'head' (preview first rows), 'summary' (per-field stats),
            'clean' (trim + drop empty rows), 'filter' (keep rows where field==value),
            'sort' (sort rows ascending/descending by field), 'keep' (keep only the
            columns in `keep`, comma-separated), 'count'.
        field: Column name for filter/sort.
        value: Filter value or sort direction ('asc'|'desc', default 'asc').
        keep: Comma-separated columns to keep when action='keep'.

    Returns an action report and the resulting (re-rendered) dataset.
    """
    try:
        rows = _parse_table(raw) if isinstance(raw, str) else list(raw)
        result = _apply_action(rows, action, field, value, keep)
        return {
            "status": "success",
            "action": action,
            "rows_returned": len(result),
            "data": json.dumps(result, indent=2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"Transform failed: {exc}"}


def _apply_action(rows: list[dict], action: str, field: str, value: str, keep: str) -> list[dict]:
    action = (action or "summary").lower()
    if action == "head":
        return rows[:10]
    if action == "count":
        return [{"count": len(rows)}]
    if action == "clean":
        return [r for r in rows if r and any(str(v).strip() for v in r.values())]
    if action == "filter":
        return [r for r in rows if str(r.get(field, "")).lower() == value.lower()]
    if action == "sort":
        desc = value.lower() == "desc"
        return sorted(rows, key=lambda r: str(r.get(field, "")), reverse=desc)
    if action == "keep":
        cols = [c.strip() for c in keep.split(",") if c.strip()]
        return [{c: r.get(c) for c in cols if c in r} for r in rows]
    if action == "summary":
        return _summarize(rows)
    return rows


def _summarize(rows: list[dict]) -> list[dict]:
    fields: dict[str, list] = {}
    for row in rows:
        for k, v in row.items():
            fields.setdefault(k, []).append(v)
    out = []
    for k, vals in fields.items():
        numeric = []
        for v in vals:
            try:
                numeric.append(float(v))
            except (TypeError, ValueError):
                pass
        entry = {"field": k, "non_empty": sum(1 for v in vals if v not in (None, ""))}
        if numeric:
            entry.update(
                {
                    "min": min(numeric),
                    "max": max(numeric),
                    "mean": round(sum(numeric) / len(numeric), 3),
                    "count": len(numeric),
                }
            )
        out.append(entry)
    return out


def ingest_document(source: str, is_url: bool = True) -> dict:
    """Load a document for analysis: a public URL, a local file path, or raw text.

    Args:
        source: The URL, local path, or inline text/CSV to ingest.
        is_url: True if `source` is an http(s) URL to fetch.

    Returns normalized text or a parsed table the agent can pass to transform_data.
    """
    raw = None
    origin = "text"
    try:
        if is_url and source.startswith(("http://", "https://")):
            r = httpx.get(source, follow_redirects=True, timeout=30)
            r.raise_for_status()
            raw = r.text
            origin = "url"
        else:
            raw = source
            if os.path.isfile(source):
                with open(source, encoding="utf-8") as fh:
                    raw = fh.read()
                origin = "file"
        if raw is None:
            return {"status": "error", "error_message": "No content to ingest."}
        if origin == "url":
            raw = _to_text(raw)  # extract readable text from HTML
        return {"status": "success", "origin": origin, "text": raw[:40000]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": f"Ingest failed: {exc}"}


def write_deliverable(filename: str, content: str) -> dict:
    """Persist a finished deliverable (report, CSV, JSON, script) to disk.

    Args:
        filename: Name for the deliverable, e.g. 'competitive_analysis.md'.
        content: The full file content.

    Returns the file path the deliverable was written to.
    """
    try:
        out = _ensure_out()
        safe = os.path.basename(filename)
        path = os.path.join(out, safe)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return {"status": "success", "path": path, "bytes": len(content.encode())}
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error_message": f"Could not write deliverable: {exc}",
        }


def list_deliverables() -> dict:
    """List the deliverable files Atlas has produced for the current run."""
    try:
        out = _ensure_out()
        files = [
            {"name": f, "bytes": os.path.getsize(os.path.join(out, f))}
            for f in sorted(os.listdir(out))
            if os.path.isfile(os.path.join(out, f))
        ]
        return {"status": "success", "deliverables": files}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error_message": str(exc)}


def _to_text(html: str) -> str:
    import re

    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# Re-export helper used elsewhere.
to_text = _to_text
__all__: list[str] = [
    "ingest_document",
    "list_deliverables",
    "transform_data",
    "write_deliverable",
]

"""Unit tests for the goal planner (no network, no GCP)."""

import os

# Force the heuristic path so tests never hit the network.
os.environ.setdefault("GEMINI_API_KEY", "")


def test_fallback_plan_is_valid():
    from app.planner import make_plan

    plan = make_plan("Research X and write a report")
    assert 3 <= len(plan) <= 6
    for step in plan:
        assert step["title"]
        assert step["kind"] in {"research", "transform", "ingest", "memory", "deliver"}


def test_sanitize_drops_bad_steps():
    from app.planner import _sanitize

    cleaned = _sanitize(
        [
            {"kind": "research", "title": "Search for competitors"},
            {"kind": "bogus", "title": "should be dropped"},
            {"kind": "deliver", "title": ""},  # empty title dropped
            {"kind": "transform", "title": "Clean the CSV"},
        ]
    )
    kinds = [s["kind"] for s in cleaned]
    assert kinds == ["research", "transform"]


def test_sanitize_empty_returns_fallback():
    from app.planner import _sanitize

    assert len(_sanitize([])) >= 3
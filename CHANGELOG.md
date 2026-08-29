# Changelog

All notable changes to this project are documented in this file.

## [1.0.1] - 2026-08-29

### Fixed
- ADK 2.x compatibility: `Runner` now constructed with `agent=` + `app_name`
  (ADK 2.x requires an `App` wrapper for the `app=` argument).
- `LocalStore` filename sanitization: `:` in memory scopes previously produced
  NTFS alternate data streams on Windows, silently dropping data.
- Deterministic FIFO claiming and event ordering via microsecond timestamps
  and a monotonic `seq` tie-break.
- `attempts` counter now persisted on local claims.
- `/run` and `/message` endpoints fail tasks gracefully on model errors
  instead of returning HTTP 500.

### Added
- Full-lifecycle integration test (`tests/test_integration.py`).
- CI pipeline (`.github/workflows/ci.yml`), ruff lint/format checks,
  `pyproject.toml`, MIT `LICENSE`.

## [1.0.0] - 2026-08-29

Initial release: autonomous background task operator for the All Things
Agentic Hackathon (Taskmaster track). Google ADK + Gemini + Cloud Run +
Firestore + Cloud Scheduler, with a REST API, dashboard, and local
zero-GCP demo mode.

# Debug and one-off scripts

Standalone scripts used during development to inspect a local database, apply a manual
fix, or exercise an agent by hand. None of these are part of the test suite (`pytest.ini`
restricts collection to `tests/`), none are imported by the app, and none are run in CI.

They're kept (not deleted) because a few are still genuinely useful for local debugging
(for example `check_tables.py`, `reset_db.py`), but they're not maintained to the same
standard as `backend/scripts/*.py` (which are referenced from the README and docs) or
`backend/tests/*.py` (the actual test suite) — expect some to be stale or to assume a
specific local database state.

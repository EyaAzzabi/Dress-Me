"""Shared pytest fixtures for the DressMe backend suite.

An autouse fixture isolates every test from the developer's ``.env`` by forcing the
RecommendationAgent enrichment kill-switches off and the LLM provider to ``none``
(review-F2). Because ``get_settings`` is ``@lru_cache`` (``app/core/config.py``), we
clear the cache after setting the env vars so the *next* ``get_settings()`` call — in
any module — re-reads the environment. This is why we use ``setenv`` + ``cache_clear``
rather than patching ``app.core.config.get_settings``: that name is bound at import
time in each consumer module, so a single patch on the config module would not
propagate to ``ranking_model`` / ``orchestrator`` / ``recommendation_agent`` /
``llm_agent``.

Existing tests therefore run the exact fallback path: heuristic scoring, no RAG, no
LLM — independent of any committed artifact and of a developer's ``.env`` (which may
set ``LLM_PROVIDER=mistral``). New tests that exercise an enriched path re-enable the
relevant flag locally (e.g. ``monkeypatch.setenv("RANKING_ENABLED", "true")`` +
``get_settings.cache_clear()``).
"""

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolate_enrichment_flags(monkeypatch):
    monkeypatch.setenv("RANKING_ENABLED", "false")
    monkeypatch.setenv("CONTEXTUAL_RAG_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

"""Contextual RAG layer for the RecommendationAgent (axe 2).

The retrieval module (``context_retrieval.py``, added by FEAT-003) orchestrates the
existing ``vector_store`` (Pinecone) and ``catalog_index`` plus the DB to fetch outfit
references by context (occasion/weather/season). This package is intentionally thin —
it holds no state of its own.
"""

"""Contextual RAG retrieval for the RecommendationAgent (axe 2).

``retrieve_references`` orchestrates three existing pieces of infrastructure without
modifying any of them:

- ``vector_store`` (Pinecone) — item embeddings already indexed at upload time. An
  outfit of reference is the *mean* of its items' embeddings, computed on the fly so no
  second collection has to be kept in sync: a deleted item just stops contributing
  (it is dropped from Pinecone by ``metadata_agent.remove_item``).
- ``catalog_index`` — the bundled Tunisian catalog, searched cross-modally against the
  context text vector (``category=None`` — no occasion→category mapping, review-F6).
- the DB — historical references come from ``ScheduledOutfit`` (planned days) and
  ``WearLog`` grouped by date (worn days, one row per worn item/day — review-F8). The
  generated ``Outfit`` model is excluded: it has no wear date, only a creation date, so
  deriving a season from it would be semantically wrong.

This module is the RAG integration layer only — it owns no Pinecone access of its own
(``vector_store`` keeps its low-level responsibility). It never raises: Pinecone off,
an empty DB, deleted items and a missing catalog all degrade to empty structures with a
warning, so a recommendation never depends on the RAG layer to exist. Each historical
entry carries its mean outfit ``vec`` (review-F4) so the RecommendationAgent (FEAT-005)
can score ``history_fit`` without re-fetching Pinecone.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

import numpy as np
from sqlalchemy.orm import Session

from app.db import vector_store
from app.models.scheduled_outfit import ScheduledOutfit
from app.models.wear_log import WearLog
from app.services import seasons
from app.services.catalog_index import CatalogIndex

logger = logging.getLogger(__name__)

# A reference outfit worn in a season compatible with the requested season gets a small
# boost on top of the text·outfit similarity — same order of magnitude as the
# RecommendationAgent's STYLE_MATCH_BONUS. Fixed/calibrated, not learned (axe 2 has no
# labels to learn from).
SEASON_MATCH_BONUS = 0.1
# A reference group needs at least this many embeddings still in Pinecone to be scored;
# below that, deleted items have dropped too much of the outfit to trust the mean
# (review-F10).
MIN_EMBEDDINGS = 2


def retrieve_references(
    db: Session,
    user_id: uuid.UUID,
    context: dict,
    ctx_vec: np.ndarray,
    *,
    top_n_history: int = 3,
    top_k_catalog: int = 3,
) -> dict:
    """Fetch context-relevant outfit references for a user.

    Returns ``{"historical": [...], "catalog": {...}}`` (see module docstring for the
    graceful-degradation contract). Never raises.
    """
    return {
        "historical": _historical_references(db, user_id, context, ctx_vec, top_n_history),
        "catalog": _catalog_references(ctx_vec, top_k_catalog),
    }


def _historical_references(db, user_id, context, ctx_vec, top_n_history):
    try:
        groups = _reference_groups(db, user_id)
    except Exception:
        logger.warning("Contextual RAG: historical DB query failed; returning no references",
                       exc_info=True)
        return []

    ctx_vec = np.asarray(ctx_vec, dtype=np.float32)
    references = []
    for outfit_date, item_ids in groups:
        embeddings = vector_store.fetch_embeddings(item_ids)
        # Deleted items are gone from Pinecone (review-F10); keep only the ones still
        # present so the mean is over the items that actually back it.
        present = [item_id for item_id in item_ids if str(item_id) in embeddings]
        if len(present) < MIN_EMBEDDINGS:
            continue

        vec = np.mean(
            np.stack([np.asarray(embeddings[str(i)], dtype=np.float32) for i in present]),
            axis=0,
        )
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        season = seasons.season_for_date(outfit_date)
        score = float(vec @ ctx_vec)
        if seasons.season_compatible(season, context.get("season")):
            score += SEASON_MATCH_BONUS

        references.append({
            "item_ids": present,
            "score": float(score),
            "date": outfit_date,
            "season": season,
            "vec": vec,
        })

    references.sort(key=lambda r: r["score"], reverse=True)
    return references[:top_n_history]


def _reference_groups(db, user_id):
    """One ``(date, [item_id, ...])`` group per historical outfit: every ScheduledOutfit
    (native date + item_ids) plus WearLog entries grouped by date (one row per worn
    item/day — review-F8). The generated Outfit model is excluded (no wear date)."""
    groups: list[tuple[date, list[uuid.UUID]]] = []
    for scheduled in db.query(ScheduledOutfit).filter(ScheduledOutfit.owner_id == user_id).all():
        groups.append((scheduled.date, list(scheduled.item_ids)))

    worn_by_date: dict[date, list[uuid.UUID]] = {}
    for log in db.query(WearLog).filter(WearLog.owner_id == user_id).all():
        worn_by_date.setdefault(log.date, []).append(log.item_id)
    groups.extend(worn_by_date.items())

    return groups


def _catalog_references(ctx_vec, top_k_catalog):
    try:
        index = CatalogIndex()
        if not index.is_available():
            return {}
        matches = index.search(ctx_vec, category=None, limit=top_k_catalog)
        if not matches:
            return {}
        # Cross-modal global search (review-F6): group the top-k by dressme_category so
        # the RecommendationAgent / LLM can present them per category.
        categories = {match.category for match in matches}
        return {
            category: [match.to_dict() for match in matches if match.category == category]
            for category in categories
        }
    except Exception:
        logger.warning("Contextual RAG: catalog retrieval failed; returning no catalog",
                       exc_info=True)
        return {}

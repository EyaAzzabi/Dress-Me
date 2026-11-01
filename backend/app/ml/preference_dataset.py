"""preference_dataset — utilities to build training data for the PreferenceRewardModel.

Loads RecommendationFeedback from the DB, joins with Outfit embeddings from the
vector store, and produces (preferred, rejected) pairs for RLHF training.

All functions degrade gracefully (return [] / empty list) when the DB or vector
store is unavailable.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_outfit_embeddings(outfit, vector_store) -> "list[np.ndarray]":
    """Fetch embeddings for every item in an outfit from the vector store.

    Parameters
    ----------
    outfit : Outfit ORM object (must have .item_ids attribute).
    vector_store : module that exposes fetch_embeddings(list[str]) -> dict.
        May be None — returns [] in that case.

    Returns
    -------
    list of np.ndarray shape (512,), one per item found in the vector store.
    Returns [] on any error or if vector_store is None.
    """
    try:
        if vector_store is None:
            return []
        item_ids_str = [str(iid) for iid in outfit.item_ids]
        result_dict = vector_store.fetch_embeddings(item_ids_str)
        embeddings = []
        for iid in item_ids_str:
            if iid in result_dict:
                embeddings.append(np.array(result_dict[iid]))
        return embeddings
    except Exception:
        return []


def build_preference_pairs(
    db: "Session",
    user_id: str,
    vector_store,
) -> "list[tuple[list[np.ndarray], list[np.ndarray]]]":
    """Build (preferred, rejected) embedding pairs from a user's feedback history.

    Queries all RecommendationFeedback rows for the user, separates liked outfits
    (rating in ['like', 'worn']) from disliked ones (rating == 'dislike'), and
    creates a cross-product of (liked_i, disliked_j) pairs.

    Pairs where either outfit has no embeddings are silently skipped.

    Parameters
    ----------
    db : SQLAlchemy Session.
    user_id : str — UUID of the user.
    vector_store : module or object with fetch_embeddings.

    Returns
    -------
    list of (preferred_embs, rejected_embs) tuples.  Returns [] on any error.
    """
    try:
        from app.models.recommendation_feedback import RecommendationFeedback  # noqa: PLC0415

        owner_uuid = uuid.UUID(user_id)
        rows = (
            db.query(RecommendationFeedback)
            .filter(RecommendationFeedback.owner_id == owner_uuid)
            .all()
        )

        liked_outfits: list = []
        disliked_outfits: list = []

        for row in rows:
            outfit = row.outfit
            if outfit is None:
                continue
            rating = row.rating
            if rating in ("like", "worn"):
                liked_outfits.append(outfit)
            elif rating == "dislike":
                disliked_outfits.append(outfit)

        pairs: list[tuple[list[np.ndarray], list[np.ndarray]]] = []
        for liked in liked_outfits:
            pref_embs = get_outfit_embeddings(liked, vector_store)
            if not pref_embs:
                continue
            for disliked in disliked_outfits:
                rej_embs = get_outfit_embeddings(disliked, vector_store)
                if not rej_embs:
                    continue
                pairs.append((pref_embs, rej_embs))

        return pairs
    except Exception:
        return []

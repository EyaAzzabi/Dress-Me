"""preference_dataset — build RLHF training pairs from RLHFFeedback rows.

Replaces the old RecommendationFeedback-based implementation.
New primary function: build_preference_pairs(db, user_id, min_pairs, time_window_days, ...)
Backward-compat wrapper preserves old 3-arg call: build_preference_pairs(db, user_id, vector_store).

Key invariants (FIX-1, FIX-4):
  - NEVER zero-pad missing embeddings.
  - Outfits with embedding coverage < 70% are EXCLUDED entirely.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# New primary implementation
# ---------------------------------------------------------------------------

def build_preference_pairs(
    db: "Session",
    user_id: str,
    vector_store=None,  # positional arg kept for backward compat (old callers pass vs as 3rd arg)
    *,
    min_pairs: int = 100,
    time_window_days: int = 90,
    embedding_coverage_threshold: float = 0.7,
) -> "tuple[list[tuple[str, str, float]], dict]":
    """Build (outfit_a_id, outfit_b_id, weight) pairs for RLHF reward training.

    Parameters
    ----------
    db : SQLAlchemy Session.
    user_id : str — UUID of the user.
    vector_store : optional; if provided (legacy call) the function delegates to the
        legacy wrapper instead of this new implementation.
    min_pairs : minimum pairs required for training readiness.
    time_window_days : look back this many calendar days.
    embedding_coverage_threshold : outfits below this fraction are excluded (FIX-4).

    Returns
    -------
    (pairs, metadata) — pairs is list of (outfit_a_id, outfit_b_id, weight=float 0..1),
    metadata is a dict with pair_count, feedback_count, filtered_outfits, ready_for_training.
    """
    # Detect legacy call: old signature was build_preference_pairs(db, user_id, vector_store)
    # where vector_store was a positional module reference. In that case fall back to legacy.
    if vector_store is not None:
        return _legacy_build_preference_pairs(db, user_id, vector_store)

    from app.db import vector_store as vs  # noqa: PLC0415
    from app.models.rlhf_feedback import RLHFFeedback  # noqa: PLC0415
    from app.models.outfit import Outfit  # noqa: PLC0415

    try:
        owner_uuid = uuid.UUID(user_id)
    except ValueError:
        logger.error(f"Invalid user_id UUID: {user_id}")
        return [], _meta(0, 0, 0, False)

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=time_window_days)

    try:
        rows = (
            db.query(RLHFFeedback)
            .filter(
                RLHFFeedback.user_id == owner_uuid,
                RLHFFeedback.created_at >= cutoff,
            )
            .order_by(RLHFFeedback.created_at.desc())
            .all()
        )
    except Exception as exc:
        logger.error(f"DB query failed for user {user_id}: {exc}")
        return [], _meta(0, 0, 0, False)

    # --- FIX-5: keep only latest feedback per outfit_id ---
    seen_outfits: set[str] = set()
    latest_rows: list[RLHFFeedback] = []
    for row in rows:
        oid = str(row.outfit_id)
        if oid not in seen_outfits:
            seen_outfits.add(oid)
            latest_rows.append(row)

    feedback_count = len(latest_rows)

    # --- Embedding coverage check (FIX-4): validate per outfit ---
    outfit_ratings: dict[str, int] = {}   # outfit_id str → rating int
    excluded_count = 0

    for row in latest_rows:
        oid = str(row.outfit_id)
        try:
            outfit: Outfit | None = db.query(Outfit).filter(Outfit.id == row.outfit_id).first()
        except Exception as exc:
            logger.warning(f"Cannot fetch outfit {oid}: {exc}")
            excluded_count += 1
            continue

        if outfit is None:
            logger.warning(f"Outfit {oid} not found in DB — skipping")
            excluded_count += 1
            continue

        item_ids_str = [str(iid) for iid in (outfit.item_ids or [])]
        if not item_ids_str:
            logger.warning(f"Outfit {oid} has no items — skipping")
            excluded_count += 1
            continue

        # FIX-1: call fetch_embeddings, skip any missing items (never zero-pad)
        try:
            found = vs.fetch_embeddings(item_ids_str)
        except Exception as exc:
            logger.warning(f"fetch_embeddings failed for outfit {oid}: {exc}")
            excluded_count += 1
            continue

        valid_count = sum(1 for iid in item_ids_str if iid in found)
        coverage = valid_count / len(item_ids_str)

        if coverage < embedding_coverage_threshold:
            logger.warning(
                f"Outfit {oid}: {coverage:.0%} embedding coverage — excluded (FIX-4)"
            )
            excluded_count += 1
            continue

        outfit_ratings[oid] = row.rating

    if excluded_count:
        logger.warning(f"Total excluded outfits due to coverage / DB issues: {excluded_count}")

    # --- Build pairs (a preferred over b) when rating_a > rating_b ---
    outfit_ids = list(outfit_ratings.keys())
    pairs: list[tuple[str, str, float]] = []

    for i in range(len(outfit_ids)):
        for j in range(len(outfit_ids)):
            if i == j:
                continue
            oid_a = outfit_ids[i]
            oid_b = outfit_ids[j]
            rating_a = outfit_ratings[oid_a]
            rating_b = outfit_ratings[oid_b]
            if rating_a > rating_b:
                weight = (rating_a - rating_b) / 4.0
                pairs.append((oid_a, oid_b, weight))

    pair_count = len(pairs)
    ready = pair_count >= min_pairs
    metadata = _meta(pair_count, feedback_count, excluded_count, ready)

    logger.info(
        f"build_preference_pairs: user={user_id[:8]} feedback={feedback_count} "
        f"pairs={pair_count} excluded={excluded_count} ready={ready}"
    )

    return pairs, metadata


def _meta(pair_count: int, feedback_count: int, filtered_outfits: int, ready: bool) -> dict:
    return {
        "pair_count": pair_count,
        "feedback_count": feedback_count,
        "filtered_outfits": filtered_outfits,
        "ready_for_training": ready,
    }


# ---------------------------------------------------------------------------
# Legacy backward-compat wrapper (old signature: db, user_id, vector_store)
# ---------------------------------------------------------------------------

def _legacy_build_preference_pairs(
    db: "Session",
    user_id: str,
    vector_store,
) -> "tuple[list[tuple[str, str, float]], dict]":
    """Thin wrapper that adapts the old API to the new one.

    Old callers passed a vector_store object as the third arg and expected a flat list
    of (preferred_embs, rejected_embs) tuples.  New callers expect (pairs, metadata).

    This adapter returns the new format; if an old caller expected the old format it
    will need updating, but since the old function returned a different type entirely
    (list of embedding tuples vs. list of id triples) this is a deliberate API upgrade.
    Old callers (preference_reward_model.train_from_feedback) have their own signature
    and are unaffected.
    """
    logger.warning(
        "build_preference_pairs called with legacy (db, user_id, vector_store) signature — "
        "please migrate to the new keyword-argument API."
    )
    # Delegate to new implementation without the vector_store arg
    return build_preference_pairs(db, user_id)

"""embedding_fetcher — fetch and pool outfit embeddings for RLHF training.

Key invariants (FIX-1, FIX-4):
  - NEVER insert zero vectors for items missing from fetch_embeddings result.
  - Outfits with < 70% embedding coverage are excluded entirely.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 512
COVERAGE_THRESHOLD = 0.70


def get_outfit_embeddings(
    db: "Session",
    outfit_ids: list[str],
    coverage_threshold: float = COVERAGE_THRESHOLD,
) -> "tuple[dict[str, np.ndarray], dict]":
    """Fetch and mean-pool item embeddings for each outfit.

    For each outfit_id:
      1. Fetch the Outfit ORM object to get item_ids.
      2. Call vector_store.fetch_embeddings(item_ids_str) (FIX-1: skip missing).
      3. Check coverage ≥ coverage_threshold (FIX-4).
      4. Mean-pool valid embeddings into a single (512,) ndarray.

    Parameters
    ----------
    db : SQLAlchemy Session.
    outfit_ids : list of outfit UUIDs as strings.
    coverage_threshold : minimum fraction of items that must have embeddings.

    Returns
    -------
    (embeddings_dict, metadata) where embeddings_dict is {outfit_id: np.ndarray (512,)},
    and metadata is {total_outfits, valid_outfits, failed_lookups: list[str], low_coverage: list[str]}.
    """
    from app.db import vector_store as vs  # noqa: PLC0415
    from app.models.outfit import Outfit  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    result: dict[str, np.ndarray] = {}
    failed_lookups: list[str] = []
    low_coverage: list[str] = []

    for oid in outfit_ids:
        try:
            outfit_uuid = uuid.UUID(oid)
        except ValueError:
            logger.warning(f"Invalid outfit UUID: {oid!r} — skipping")
            failed_lookups.append(oid)
            continue

        try:
            outfit = db.query(Outfit).filter(Outfit.id == outfit_uuid).first()
        except Exception as exc:
            logger.warning(f"DB lookup failed for outfit {oid}: {exc} — skipping")
            failed_lookups.append(oid)
            continue

        if outfit is None:
            logger.warning(f"Outfit {oid} not found in DB — skipping")
            failed_lookups.append(oid)
            continue

        item_ids_str = [str(iid) for iid in (outfit.item_ids or [])]
        if not item_ids_str:
            logger.warning(f"Outfit {oid} has no items — skipping")
            low_coverage.append(oid)
            continue

        # FIX-1: fetch and skip missing — never zero-pad
        try:
            found = vs.fetch_embeddings(item_ids_str)
        except Exception as exc:
            logger.warning(f"fetch_embeddings failed for outfit {oid}: {exc} — skipping")
            failed_lookups.append(oid)
            continue

        valid_embeddings: list[np.ndarray] = []
        for iid in item_ids_str:
            if iid in found:
                vec = np.array(found[iid], dtype=np.float32)
                valid_embeddings.append(vec)
            else:
                # FIX-1: skip — do NOT create a zero vector
                logger.warning(f"Item {iid} (outfit {oid}) has no embedding — skipped")

        coverage = len(valid_embeddings) / len(item_ids_str)

        if coverage < coverage_threshold:
            logger.warning(
                f"Outfit {oid}: {coverage:.0%} embedding coverage — excluded (FIX-4)"
            )
            low_coverage.append(oid)
            continue

        # Mean-pool valid embeddings → (512,) ndarray
        pooled = np.stack(valid_embeddings, axis=0).mean(axis=0)  # (512,)
        result[oid] = pooled.astype(np.float32)

    total = len(outfit_ids)
    valid = len(result)

    logger.info(
        f"get_outfit_embeddings: total={total} valid={valid} "
        f"failed={len(failed_lookups)} low_coverage={len(low_coverage)}"
    )

    metadata = {
        "total_outfits": total,
        "valid_outfits": valid,
        "failed_lookups": failed_lookups,
        "low_coverage": low_coverage,
    }
    return result, metadata


def filter_pairs_by_embeddings(
    pairs: "list[tuple[str, str, float]]",
    embeddings: "dict[str, np.ndarray]",
) -> "tuple[list[tuple[str, np.ndarray, np.ndarray, float]], list[tuple[str, str, float]]]":
    """Filter preference pairs, keeping only those where both outfits have embeddings.

    Parameters
    ----------
    pairs : list of (outfit_a_id, outfit_b_id, weight).
    embeddings : dict of outfit_id → (512,) ndarray.

    Returns
    -------
    (valid, dropped) where:
      valid  — list of (outfit_a_id, emb_a, emb_b, weight)  [embeddings attached]
      dropped — list of the original (a_id, b_id, weight) tuples that were dropped.
    """
    valid: list[tuple[str, np.ndarray, np.ndarray, float]] = []
    dropped: list[tuple[str, str, float]] = []

    for pair in pairs:
        oid_a, oid_b, weight = pair
        if oid_a in embeddings and oid_b in embeddings:
            valid.append((oid_a, embeddings[oid_a], embeddings[oid_b], weight))
        else:
            dropped.append(pair)

    if dropped:
        logger.warning(
            f"filter_pairs_by_embeddings: dropped {len(dropped)} pairs "
            f"(missing embeddings for one or both outfits)"
        )

    logger.info(
        f"filter_pairs_by_embeddings: {len(valid)} valid, {len(dropped)} dropped"
    )
    return valid, dropped

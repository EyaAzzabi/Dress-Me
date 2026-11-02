"""train_rlhf.py — RLHF training pipeline (reward model + PPO policy model).

Usage:
  python train_rlhf.py --user-id <uuid> [--min-pairs 100] [--reward-epochs 20]
                       [--policy-epochs 3] [--dry-run]

Exit codes:
  0 — success or skipped_insufficient_data
  1 — failure (exception / missing dependency)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Make app importable when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("train_rlhf")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train RLHF reward + policy models.")
    p.add_argument("--user-id", required=True, help="UUID of the user to train for.")
    p.add_argument(
        "--min-pairs",
        type=int,
        default=100,
        help="Minimum valid training pairs required (default: 100).",
    )
    p.add_argument(
        "--reward-epochs",
        type=int,
        default=20,
        help="Epochs for reward model training (default: 20).",
    )
    p.add_argument(
        "--policy-epochs",
        type=int,
        default=3,
        help="Epochs for PPO policy training (default: 3).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without saving models.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    user_id: str = args.user_id
    min_pairs: int = args.min_pairs
    reward_epochs: int = args.reward_epochs
    policy_epochs: int = args.policy_epochs
    dry_run: bool = args.dry_run

    summary: dict = {
        "user_id": user_id,
        "dry_run": dry_run,
        "status": "unknown",
    }

    # ------------------------------------------------------------------
    # Step 1: Open DB session
    # ------------------------------------------------------------------
    try:
        from app.db.session import SessionLocal  # noqa: PLC0415
        db = SessionLocal()
    except Exception as exc:
        logger.error(f"Cannot open DB session: {exc}")
        summary["status"] = "skipped_insufficient_data"
        summary["reason"] = f"DB unavailable: {exc}"
        print(json.dumps(summary))
        sys.exit(0)  # not a hard failure — DB simply not reachable

    try:
        _run_pipeline(db, user_id, min_pairs, reward_epochs, policy_epochs, dry_run, summary)
    except Exception as exc:
        logger.exception(f"Unhandled error in training pipeline: {exc}")
        summary["status"] = "failure"
        summary["error"] = str(exc)
        print(json.dumps(summary))
        sys.exit(1)
    finally:
        db.close()


def _run_pipeline(
    db,
    user_id: str,
    min_pairs: int,
    reward_epochs: int,
    policy_epochs: int,
    dry_run: bool,
    summary: dict,
) -> None:
    from app.ml.preference_dataset import build_preference_pairs  # noqa: PLC0415
    from app.ml.embedding_fetcher import (  # noqa: PLC0415
        get_outfit_embeddings,
        filter_pairs_by_embeddings,
    )
    from app.ml import preference_reward_model  # noqa: PLC0415
    from app.ml.rlhf_policy_model import (  # noqa: PLC0415
        RLHFPolicyModel,
        train_policy_ppo,
        save_policy_model,
    )

    # ------------------------------------------------------------------
    # Step 2: Build preference pairs
    # ------------------------------------------------------------------
    logger.info(f"Building preference pairs for user {user_id}...")
    pairs, meta = build_preference_pairs(db, user_id)
    summary["preference_metadata"] = meta

    if not meta.get("ready_for_training", False):
        logger.info(
            f"Insufficient data: {meta.get('pair_count', 0)} pairs "
            f"(need {min_pairs}). Exiting."
        )
        summary["status"] = "skipped_insufficient_data"
        summary["pair_count"] = meta.get("pair_count", 0)
        print(json.dumps(summary))
        sys.exit(0)

    # Extract unique outfit_ids from pairs
    outfit_ids = list({oid for oid_a, oid_b, _ in pairs for oid in (oid_a, oid_b)})

    # ------------------------------------------------------------------
    # Step 3: Fetch outfit embeddings
    # ------------------------------------------------------------------
    logger.info(f"Fetching embeddings for {len(outfit_ids)} outfits...")
    embeddings, emb_meta = get_outfit_embeddings(db, outfit_ids)
    summary["embedding_metadata"] = emb_meta

    # ------------------------------------------------------------------
    # Step 4: Filter pairs by embedding availability
    # ------------------------------------------------------------------
    valid_pairs_with_embs, dropped = filter_pairs_by_embeddings(pairs, embeddings)
    summary["valid_pairs"] = len(valid_pairs_with_embs)
    summary["dropped_pairs"] = len(dropped)

    if len(valid_pairs_with_embs) < min_pairs:
        logger.info(
            f"After embedding filter: {len(valid_pairs_with_embs)} pairs "
            f"< {min_pairs} minimum. Skipping."
        )
        summary["status"] = "skipped_insufficient_data"
        print(json.dumps(summary))
        sys.exit(0)

    # ------------------------------------------------------------------
    # Step 5: Train reward model
    # ------------------------------------------------------------------
    logger.info("Training reward model...")
    reward_model = preference_reward_model.load_or_init(user_id)

    # Build (preferred_embs, rejected_embs) tuples for reward model
    import numpy as np  # noqa: PLC0415
    feedback_pairs_for_reward = [
        ([emb_a], [emb_b])  # each is a list of (512,) arrays
        for _oid_a, emb_a, emb_b, _weight in valid_pairs_with_embs
    ]

    preference_reward_model.train_from_feedback(
        reward_model, feedback_pairs_for_reward, epochs=reward_epochs
    )

    if not dry_run:
        preference_reward_model.save(reward_model, user_id)
        logger.info("Reward model saved.")
    else:
        logger.info("Dry run — reward model NOT saved.")

    summary["reward_model_trained"] = reward_model._trained

    # ------------------------------------------------------------------
    # Step 6: Train PPO policy model
    # ------------------------------------------------------------------
    logger.info("Training PPO policy model...")
    policy_model = RLHFPolicyModel()

    # Convert valid_pairs_with_embs → (emb_a, emb_b, weight) tuples
    policy_pairs = [
        (emb_a, emb_b, weight)
        for _oid_a, emb_a, emb_b, weight in valid_pairs_with_embs
    ]

    ppo_result = train_policy_ppo(
        policy_model,
        reward_model,
        policy_pairs,
        epochs=policy_epochs,
    )
    summary["ppo_result"] = ppo_result

    if not dry_run:
        save_policy_model(policy_model, user_id)
        logger.info("Policy model saved.")
    else:
        logger.info("Dry run — policy model NOT saved.")

    summary["policy_model_trained"] = policy_model._trained

    # ------------------------------------------------------------------
    # Step 7: Print JSON summary and exit 0
    # ------------------------------------------------------------------
    summary["status"] = "success"
    print(json.dumps(summary, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

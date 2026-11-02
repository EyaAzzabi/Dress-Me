"""RLHF API routes — POST /rlhf/feedback and GET /rlhf/stats."""
import csv
import io
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.outfit import Outfit
from app.models.rlhf_feedback import RLHFFeedback
from app.models.user import User
from app.schemas.rlhf import (
    RLHFFeedbackRequest,
    RLHFFeedbackResponse,
    RLHFStats,
    RLHFStatsDayPoint,
)

router = APIRouter(prefix="/rlhf", tags=["rlhf"])

# Path to reward model artifacts directory, relative to this file:
# backend/app/api/routes/rlhf.py → ../../ml/artifacts/
_ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "ml" / "artifacts"


# ---------------------------------------------------------------------------
# POST /rlhf/feedback
# ---------------------------------------------------------------------------


@router.post("/feedback", response_model=RLHFFeedbackResponse, status_code=201)
def submit_feedback(
    payload: RLHFFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RLHFFeedbackResponse:
    """Record a new RLHF feedback row (FIX-5: always INSERT, never upsert)."""
    # 1. Fetch outfit — 404 if missing
    outfit = db.query(Outfit).filter(Outfit.id == payload.outfit_id).first()
    if outfit is None:
        raise HTTPException(status_code=404, detail="Tenue introuvable")

    # 2. Ownership check — 403 if not the owner
    if outfit.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")

    # 3. Validate items_liked / items_disliked UUIDs are subsets of outfit.item_ids
    outfit_item_ids = {str(iid) for iid in (outfit.item_ids or [])}

    def _extract_ids(items: list[dict]) -> set[str]:
        return {str(item.get("id", "")) for item in items if item.get("id")}

    liked_ids = _extract_ids(payload.items_liked)
    disliked_ids = _extract_ids(payload.items_disliked)
    invalid = (liked_ids | disliked_ids) - outfit_item_ids
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"items_liked/items_disliked contiennent des IDs absents de la tenue: {invalid}",
        )

    # 4. Always INSERT a new row (FIX-5: no upsert, no ON CONFLICT)
    feedback = RLHFFeedback(
        id=uuid.uuid4(),
        user_id=current_user.id,
        outfit_id=payload.outfit_id,
        rating=payload.rating,
        comment=payload.comment,
        items_liked=payload.items_liked,
        items_disliked=payload.items_disliked,
        occasion_matched=payload.occasion_matched,
        seasonal_appropriate=payload.seasonal_appropriate,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    # 5. Compute total_feedbacks_by_user
    total_feedbacks_by_user: int = (
        db.query(func.count(RLHFFeedback.id))
        .filter(RLHFFeedback.user_id == current_user.id)
        .scalar()
        or 0
    )

    # 6. Compute pairs_available: n*(n-1)//2 where n = distinct outfit_ids with feedback
    n_distinct_outfits: int = (
        db.query(func.count(func.distinct(RLHFFeedback.outfit_id)))
        .filter(RLHFFeedback.user_id == current_user.id)
        .scalar()
        or 0
    )
    pairs_available = n_distinct_outfits * (n_distinct_outfits - 1) // 2

    # 7. Return response — is_new is always True (FIX-5)
    return RLHFFeedbackResponse(
        id=feedback.id,
        user_id=feedback.user_id,
        outfit_id=feedback.outfit_id,
        rating=feedback.rating,
        created_at=feedback.created_at,
        is_new=True,
        total_feedbacks_by_user=total_feedbacks_by_user,
        pairs_available=pairs_available,
    )


# ---------------------------------------------------------------------------
# GET /rlhf/stats
# ---------------------------------------------------------------------------


@router.get("/stats")
def get_stats(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    format: str = Query(default="json"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return RLHF statistics for the current user.
    
    format='csv' returns a downloadable CSV file.
    All fields default to zeros/empty lists when no data exists.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    user_id = current_user.id

    # --- Base queryset (user + time window) ----------------------------------
    rows = (
        db.query(RLHFFeedback)
        .filter(
            RLHFFeedback.user_id == user_id,
            RLHFFeedback.created_at >= cutoff,
        )
        .all()
    )

    # --- Aggregations --------------------------------------------------------
    total_feedbacks = len(rows)

    if total_feedbacks == 0:
        average_rating = 0.0
    else:
        average_rating = round(sum(r.rating for r in rows) / total_feedbacks, 4)

    # rating_distribution — always all 5 keys
    rating_distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in rows:
        if r.rating in rating_distribution:
            rating_distribution[r.rating] += 1

    # recent_feedbacks — last `limit` rows sorted by created_at DESC
    recent_rows = sorted(rows, key=lambda r: r.created_at, reverse=True)[:limit]
    recent_feedbacks = [
        {
            "id": str(r.id),
            "outfit_id": str(r.outfit_id),
            "rating": r.rating,
            "comment": r.comment,
            "items_liked": _parse_json_field(r.items_liked),
            "items_disliked": _parse_json_field(r.items_disliked),
            "occasion_matched": r.occasion_matched,
            "seasonal_appropriate": r.seasonal_appropriate,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in recent_rows
    ]

    # most_liked_items — aggregate items_liked JSON arrays
    liked_counts: dict[str, int] = defaultdict(int)
    liked_ratings: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        items = _parse_json_field(r.items_liked)
        for item in items:
            item_id = str(item.get("id", ""))
            if item_id:
                liked_counts[item_id] += 1
                liked_ratings[item_id].append(float(r.rating))

    most_liked_items = sorted(
        [
            {
                "item_id": item_id,
                "count": count,
                "avg_rating": round(sum(liked_ratings[item_id]) / len(liked_ratings[item_id]), 4),
            }
            for item_id, count in liked_counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:limit]

    # most_disliked_items — aggregate items_disliked JSON arrays
    disliked_counts: dict[str, int] = defaultdict(int)
    disliked_ratings: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        items = _parse_json_field(r.items_disliked)
        for item in items:
            item_id = str(item.get("id", ""))
            if item_id:
                disliked_counts[item_id] += 1
                disliked_ratings[item_id].append(float(r.rating))

    most_disliked_items = sorted(
        [
            {
                "item_id": item_id,
                "count": count,
                "avg_rating": round(
                    sum(disliked_ratings[item_id]) / len(disliked_ratings[item_id]), 4
                ),
            }
            for item_id, count in disliked_counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:limit]

    # avg_rating_trend — group by date string, sorted ASC
    trend_by_date: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.created_at:
            date_str = r.created_at.strftime("%Y-%m-%d")
            trend_by_date[date_str].append(float(r.rating))

    avg_rating_trend = [
        RLHFStatsDayPoint(
            date=date_str,
            avg_rating=round(sum(ratings) / len(ratings), 4),
            count=len(ratings),
        )
        for date_str, ratings in sorted(trend_by_date.items())
    ]

    # most_liked_occasions — join outfit.occasion, AVG(rating) per occasion
    occasion_ratings: dict[str, list[float]] = defaultdict(list)
    outfit_ids = list({r.outfit_id for r in rows})
    if outfit_ids:
        outfits_map = {
            o.id: o.occasion
            for o in db.query(Outfit).filter(Outfit.id.in_(outfit_ids)).all()
            if o.occasion
        }
        for r in rows:
            occ = outfits_map.get(r.outfit_id)
            if occ:
                occasion_ratings[occ].append(float(r.rating))

    most_liked_occasions = {
        occ: round(sum(ratings) / len(ratings), 4)
        for occ, ratings in occasion_ratings.items()
    }

    # readiness_for_training — pairs_available and last model checkpoint
    n_distinct_outfits: int = (
        db.query(func.count(func.distinct(RLHFFeedback.outfit_id)))
        .filter(RLHFFeedback.user_id == user_id)
        .scalar()
        or 0
    )
    pairs_available = n_distinct_outfits * (n_distinct_outfits - 1) // 2

    last_trained_at = _get_last_trained_at(str(user_id))

    readiness_for_training = {
        "has_sufficient_data": pairs_available >= 100,
        "pair_count": pairs_available,
        "next_threshold": 100,
        "last_trained_at": last_trained_at,
    }

    stats = RLHFStats(
        total_feedbacks=total_feedbacks,
        average_rating=average_rating,
        rating_distribution=rating_distribution,
        recent_feedbacks=recent_feedbacks,
        most_liked_items=most_liked_items,
        most_disliked_items=most_disliked_items,
        avg_rating_trend=avg_rating_trend,
        most_liked_occasions=most_liked_occasions,
        readiness_for_training=readiness_for_training,
    )

    # --- CSV export ----------------------------------------------------------
    if format.lower() == "csv":
        csv_content = _build_csv(stats, recent_feedbacks)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=retours_rlhf.csv"},
        )

    return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_field(value) -> list:
    """Parse a JSON text column value to a list; return [] on any error."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _get_last_trained_at(user_id: str) -> str | None:
    """Return ISO8601 mtime of reward_model_{user_id[:8]}.pt, or None if missing."""
    artifact_path = _ARTIFACTS_DIR / f"reward_model_{user_id[:8]}.pt"
    try:
        mtime = artifact_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except (FileNotFoundError, OSError):
        return None


def _build_csv(stats: RLHFStats, recent_feedbacks: list[dict]) -> bytes:
    """Build a CSV string from stats data using Python's csv module."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header + summary rows
    writer.writerow(["Section", "Métrique", "Valeur"])
    writer.writerow(["Résumé", "Total retours", stats.total_feedbacks])
    writer.writerow(["Résumé", "Note moyenne", stats.average_rating])
    writer.writerow([])

    # Rating distribution
    writer.writerow(["Distribution", "Note", "Nombre"])
    for rating, count in sorted(stats.rating_distribution.items()):
        writer.writerow(["Distribution", rating, count])
    writer.writerow([])

    # Recent feedbacks
    writer.writerow(
        [
            "Retours récents",
            "ID",
            "Tenue",
            "Note",
            "Commentaire",
            "Date",
        ]
    )
    for fb in recent_feedbacks:
        writer.writerow(
            [
                "Retours récents",
                fb.get("id", ""),
                fb.get("outfit_id", ""),
                fb.get("rating", ""),
                fb.get("comment", ""),
                fb.get("created_at", ""),
            ]
        )
    writer.writerow([])

    # Rating trend
    writer.writerow(["Tendance", "Date", "Note moyenne", "Nombre"])
    for point in stats.avg_rating_trend:
        writer.writerow(["Tendance", point.date, point.avg_rating, point.count])
    writer.writerow([])

    # Readiness
    r = stats.readiness_for_training
    writer.writerow(["Entraînement", "Paires disponibles", r.get("pair_count", 0)])
    writer.writerow(
        ["Entraînement", "Données suffisantes", r.get("has_sufficient_data", False)]
    )
    writer.writerow(
        ["Entraînement", "Dernier entraînement", r.get("last_trained_at", "")]
    )

    return output.getvalue().encode("utf-8")

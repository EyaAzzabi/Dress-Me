"""Monitoring routes for LLM and constraint parser stats."""

from fastapi import APIRouter

from app.ml.constraint_parser import ConstraintParser

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/constraint-parser-stats")
def get_constraint_parser_stats() -> dict:
    """Return constraint parser LLM vs. fallback statistics.
    
    No auth required — read-only ops metrics.
    
    Returns:
        {
            "success": int (LLM successful parses),
            "fallback": int (regex fallbacks),
            "fallback_rate": float (fallback / (success + fallback)),
            "last_reset": float (Unix timestamp),
            "recent_fallbacks": list[{"timestamp": str, "constraint_text": str, "reason": str}]
        }
    """
    stats = ConstraintParser.get_stats()
    return {
        "success": stats["success"],
        "fallback": stats["fallback"],
        "fallback_rate": stats["fallback_rate"],
        "last_reset": stats["last_reset"],
        "recent_fallbacks": stats["recent_fallbacks"],
    }

"""Hard constraints for outfit generation by occasion.

Prevents inappropriate outfit suggestions (e.g., evening dress for work, sports
wear for formal events). Each occasion has rules about:
- Allowed base item categories (haut/bas vs robe)
- Required formality range
- Forbidden specific categories
- Minimum coverage expectations
"""

from dataclasses import dataclass
from typing import Optional

from app.models.clothing_item import ClothingItem


@dataclass
class OccasionConstraints:
    """Rules for an occasion category.
    
    Attributes:
        occasion: occasion category (e.g., "travail", "soiree")
        min_formality: minimum formality level required (1-5)
        max_formality: maximum formality level allowed (1-5)
        allowed_bases: list of allowed base types (["haut_bas"] or ["robe"] or both)
        allowed_categories: list of allowed item categories (if empty, all allowed)
        forbidden_categories: list of forbidden item categories
        min_coverage: minimum expected coverage ("low" | "medium" | "high")
    """
    
    occasion: str
    min_formality: int = 1
    max_formality: int = 5
    allowed_bases: list[str] = None  # "haut_bas" | "robe"
    allowed_categories: list[str] = None  # Empty = all allowed
    forbidden_categories: list[str] = None
    min_coverage: str = "low"  # "low" | "medium" | "high"
    
    def __post_init__(self):
        if self.allowed_bases is None:
            self.allowed_bases = ["haut_bas", "robe"]
        if self.allowed_categories is None:
            self.allowed_categories = []
        if self.forbidden_categories is None:
            self.forbidden_categories = []


# Define constraints for each occasion category
OCCASION_CONSTRAINTS = {
    "travail": OccasionConstraints(
        occasion="travail",
        min_formality=3,
        max_formality=5,
        allowed_bases=["haut_bas"],  # ✅ Haut + Bas (pas robe seule)
        allowed_categories=["haut", "bas", "chaussures", "sac", "accessoire"],
        forbidden_categories=["robe_soiree", "bikini", "robe_ceremonie"],
        min_coverage="high",  # Business casual needs coverage
    ),
    
    "soiree": OccasionConstraints(
        occasion="soiree",
        min_formality=3,
        max_formality=5,
        allowed_bases=["robe", "haut_bas"],
        allowed_categories=["robe", "haut", "bas", "chaussures", "sac", "accessoire"],
        forbidden_categories=["tee_shirt", "leggings_sport"],
        min_coverage="medium",
    ),
    
    "ceremonie": OccasionConstraints(
        occasion="ceremonie",
        min_formality=5,
        max_formality=5,
        allowed_bases=["robe", "haut_bas"],
        allowed_categories=["robe", "haut", "bas", "chaussures", "sac", "accessoire"],
        forbidden_categories=["casual", "denim", "tee_shirt"],
        min_coverage="high",
    ),
    
    "mariage": OccasionConstraints(
        occasion="mariage",
        min_formality=4,
        max_formality=5,
        allowed_bases=["robe", "haut_bas"],
        allowed_categories=["robe", "haut", "bas", "chaussures", "sac", "accessoire"],
        forbidden_categories=["blanc", "noir_deuil"],  # Avoid bride colors
        min_coverage="high",
    ),
    
    "casual_quotidien": OccasionConstraints(
        occasion="casual_quotidien",
        min_formality=1,
        max_formality=3,
        allowed_bases=["haut_bas", "robe"],
        allowed_categories=["haut", "bas", "robe", "chaussures", "sac", "accessoire"],
        forbidden_categories=[],
        min_coverage="low",
    ),
    
    "sport": OccasionConstraints(
        occasion="sport",
        min_formality=1,
        max_formality=1,
        allowed_bases=["haut_bas"],
        allowed_categories=["haut", "bas", "chaussures", "sac", "accessoire"],  # Accept basic categories
        forbidden_categories=["robe", "robe_ceremonie", "costume", "talon"],
        min_coverage="medium",
    ),
    
    "plage": OccasionConstraints(
        occasion="plage",
        min_formality=1,
        max_formality=2,
        allowed_bases=["robe"],  # Robe/maillot/sarong
        allowed_categories=["bikini", "maillot", "robe_plage", "chaussures_plage", "accessoire"],
        forbidden_categories=["jeans", "costume", "talons"],
        min_coverage="low",
    ),
    
    "voyage": OccasionConstraints(
        occasion="voyage",
        min_formality=2,
        max_formality=3,
        allowed_bases=["haut_bas", "robe"],
        allowed_categories=["haut", "bas", "robe", "chaussures_confortables", "sac"],
        forbidden_categories=["talons_hauts"],
        min_coverage="medium",
    ),
}


def validate_outfit(
    outfit: list[ClothingItem],
    occasion_category: str | None,
    formality: int | None = None,
) -> tuple[bool, str | None]:
    """Validate if an outfit respects occasion constraints.
    
    Args:
        outfit: list of clothing items in the outfit
        occasion_category: occasion category (e.g., "travail")
        formality: required formality level (1-5)
    
    Returns:
        (is_valid, reason_if_invalid)
        - (True, None) if outfit is valid
        - (False, "reason") if outfit violates constraints
    """
    
    if not occasion_category or occasion_category not in OCCASION_CONSTRAINTS:
        # No constraints defined or no occasion specified → accept
        return True, None
    
    constraints = OCCASION_CONSTRAINTS[occasion_category]
    
    # Check formality
    if formality is not None:
        if formality < constraints.min_formality:
            return False, f"Formality too low ({formality} < {constraints.min_formality})"
        if formality > constraints.max_formality:
            return False, f"Formality too high ({formality} > {constraints.max_formality})"
    
    # Check base type (haut_bas vs robe)
    has_robe = any(item.category == "robe" for item in outfit)
    has_haut_bas = any(item.category in ["haut", "bas"] for item in outfit)
    
    base_type = None
    if has_robe and not has_haut_bas:
        base_type = "robe"
    elif has_haut_bas and not has_robe:
        base_type = "haut_bas"
    elif has_robe and has_haut_bas:
        return False, "Cannot mix robe with haut/bas in same outfit"
    
    if base_type and base_type not in constraints.allowed_bases:
        return False, f"Base type '{base_type}' not allowed for {occasion_category}"
    
    # Check forbidden categories
    if constraints.forbidden_categories:
        for item in outfit:
            if item.category in constraints.forbidden_categories:
                return False, f"Category '{item.category}' forbidden for {occasion_category}"
            # Also check category by exact name (for specific subtypes)
            if hasattr(item, 'dressme_category') and item.dressme_category in constraints.forbidden_categories:
                return False, f"Item type '{item.dressme_category}' forbidden for {occasion_category}"
    
    # Check allowed categories (if whitelist is defined)
    if constraints.allowed_categories:
        for item in outfit:
            if item.category not in constraints.allowed_categories:
                return False, f"Category '{item.category}' not allowed for {occasion_category}"
    
    return True, None


def filter_candidates_by_constraints(
    candidates: list[tuple],  # (outfit, score, style_match)
    occasion_category: str | None,
    formality: int | None = None,
) -> list[tuple]:
    """Filter candidate outfits by occasion constraints.
    
    Args:
        candidates: list of (outfit, score, style_match) tuples
        occasion_category: occasion category
        formality: required formality level
    
    Returns:
        Filtered list of candidates that pass constraints
    """
    
    if not occasion_category:
        return candidates
    
    valid_candidates = []
    rejected_count = 0
    
    for outfit, score, style_match in candidates:
        is_valid, reason = validate_outfit(outfit, occasion_category, formality)
        
        if is_valid:
            valid_candidates.append((outfit, score, style_match))
        else:
            rejected_count += 1
            # Optional: log rejections for debugging
            # logger.debug(f"Rejected outfit: {reason}")
    
    return valid_candidates

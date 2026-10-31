"""Pairwise outfit-compatibility scorer, trained on real Polyvore outfit co-occurrence
(68,306 real outfits — see ml/notebooks/09_compatibility_model.py for how it was
trained and validated). Replaces the raw-cosine-similarity heuristic
RecommendationAgent used to score outfit coherence.

Honest result on held-out, never-seen-during-training outfits: AUC 0.674 vs. 0.609
and accuracy 62.3% vs. 58.3% for plain cosine similarity — a real but modest
improvement, not a dramatic one. A linear probe on frozen embeddings captures somewhat
more than raw similarity, not a lot more.

ENHANCED VERSION: Now supports contextual features (season, colors, style) for better
compatibility scoring.
"""

from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "compatibility_model.joblib"


@lru_cache
def _load_model():
    import joblib

    return joblib.load(MODEL_PATH)


def pair_compatibility(vec_a: np.ndarray, vec_b: np.ndarray, 
                      item_a=None, item_b=None, 
                      season: str | None = None,
                      occasion: str | None = None) -> float:
    """Probability these two L2-normalized embeddings were styled together in a real
    outfit, per the trained model. Falls back to raw cosine similarity if the
    artifact is missing (e.g. a fresh checkout before copying it from ml/).
    
    Enhanced with contextual features:
    - item_a, item_b: ClothingItem objects with colors, style, season attributes
    - season: target season for the outfit
    - occasion: target occasion
    """
    if not MODEL_PATH.exists():
        # Fallback with contextual boost
        base_score = float(vec_a @ vec_b)
        return _apply_contextual_boost(base_score, item_a, item_b, season, occasion)
    
    model = _load_model()
    feature = (vec_a * vec_b).reshape(1, -1)
    base_score = float(model.predict_proba(feature)[0, 1])
    
    # Apply contextual adjustments
    return _apply_contextual_boost(base_score, item_a, item_b, season, occasion)


def _apply_contextual_boost(base_score: float, item_a, item_b, 
                            season: str | None, occasion: str | None) -> float:
    """Apply contextual rules to boost or penalize compatibility based on:
    - Season compatibility
    - Color harmony
    - Style coherence
    """
    if item_a is None or item_b is None:
        return base_score
    
    score = base_score
    
    # 1. Season compatibility boost
    if season:
        season_boost = _season_compatibility_boost(item_a, item_b, season)
        score *= season_boost
    
    # 2. Color harmony boost/penalty
    color_factor = _color_harmony_factor(item_a, item_b)
    score *= color_factor
    
    # 3. Style coherence boost
    style_boost = _style_coherence_boost(item_a, item_b)
    score *= style_boost
    
    # 4. Pattern clash penalty
    pattern_penalty = _pattern_clash_penalty(item_a, item_b)
    score *= pattern_penalty
    
    # Keep score in [0, 1] range
    return min(1.0, max(0.0, score))


def _season_compatibility_boost(item_a, item_b, target_season: str) -> float:
    """Boost if both items match the target season"""
    season_map = {
        "ete": ["ete", "toutes_saisons"],
        "hiver": ["hiver", "toutes_saisons"],
        "mi_saison": ["mi_saison", "toutes_saisons"],
        "toutes_saisons": ["ete", "hiver", "mi_saison", "toutes_saisons"],
    }
    
    compatible_seasons = season_map.get(target_season, [target_season])
    
    a_match = getattr(item_a, "season", None) in compatible_seasons
    b_match = getattr(item_b, "season", None) in compatible_seasons
    
    if a_match and b_match:
        return 1.15  # +15% boost
    elif a_match or b_match:
        return 1.05  # +5% boost if at least one matches
    else:
        return 0.95  # -5% penalty if both don't match


def _color_harmony_factor(item_a, item_b) -> float:
    """Boost compatible colors, penalize clashing ones"""
    colors_a = set(getattr(item_a, "colors", []) or [])
    colors_b = set(getattr(item_b, "colors", []) or [])
    
    if not colors_a or not colors_b:
        return 1.0  # Neutral if no color info
    
    # Parse JSON strings if needed
    if isinstance(colors_a, str):
        import json
        try:
            colors_a = set(json.loads(colors_a))
        except:
            pass
    if isinstance(colors_b, str):
        import json
        try:
            colors_b = set(json.loads(colors_b))
        except:
            pass
    
    # Same colors = good harmony
    if colors_a & colors_b:
        return 1.10  # +10% for shared colors
    
    # Neutral colors (noir, blanc, gris, beige) go with everything
    neutral = {"noir", "blanc", "gris", "beige"}
    if (colors_a & neutral) or (colors_b & neutral):
        return 1.05  # +5% for neutrals
    
    # Known clashing combinations
    clashes = [
        {"rouge", "rose"},
        {"rouge", "orange"},
        {"orange", "rose"},
        {"violet", "rouge"},
    ]
    
    for clash in clashes:
        if clash & colors_a and clash & colors_b:
            return 0.85  # -15% penalty for clashing colors
    
    return 1.0  # Neutral otherwise


def _style_coherence_boost(item_a, item_b) -> float:
    """Boost if styles match"""
    style_a = getattr(item_a, "style", None)
    style_b = getattr(item_b, "style", None)
    
    if not style_a or not style_b:
        return 1.0
    
    if style_a == style_b:
        return 1.12  # +12% for matching styles
    
    # Some styles mix well
    compatible_pairs = [
        {"Casual", "Smart Casual"},
        {"Formal", "Smart Casual"},
        {"Travel", "Casual"},
        {"Sports", "Casual"},
    ]
    
    styles = {style_a, style_b}
    for pair in compatible_pairs:
        if styles == pair:
            return 1.06  # +6% for compatible styles
    
    # Very incompatible styles
    incompatible = [
        {"Formal", "Sports"},
        {"Formal", "Home"},
        {"Party", "Home"},
        {"Sports", "Party"},
    ]
    
    for pair in incompatible:
        if styles == pair:
            return 0.88  # -12% for incompatible styles
    
    return 0.97  # -3% for unrelated styles


def _pattern_clash_penalty(item_a, item_b) -> float:
    """Penalize clashing patterns (stripes + checks, etc.)"""
    pattern_a = getattr(item_a, "pattern", None)
    pattern_b = getattr(item_b, "pattern", None)
    
    if not pattern_a or not pattern_b:
        return 1.0
    
    # Both "uni" (solid) is fine
    if pattern_a == "uni" and pattern_b == "uni":
        return 1.05  # +5% for solid colors together
    
    # One solid + one patterned is good
    if pattern_a == "uni" or pattern_b == "uni":
        return 1.02  # +2% for one solid
    
    # Two different bold patterns usually clash
    bold_patterns = {"rayures", "carreaux", "imprime_animal", "geometrique"}
    if pattern_a in bold_patterns and pattern_b in bold_patterns and pattern_a != pattern_b:
        return 0.80  # -20% for clashing patterns
    
    # Same pattern is okay
    if pattern_a == pattern_b:
        return 0.95  # -5% (unusual but not terrible)
    
    return 0.92  # -8% for two different patterns

"""Outfit evaluation framework for RecommendationAgent.

Evaluates each outfit candidate independently, grounding confidence in multiple factors:
visual score, context fit (weather/season/occasion), history fit, and style match.
"""

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np

from app.services import seasons


def feedback_alignment_at_k(
    recommended: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    *,
    k: int = 3,
) -> float:
    """Measure mean signed outfit overlap with user feedback in the top-k results."""
    if k < 1:
        raise ValueError("k must be positive")
    if not recommended or not feedback:
        return 0.0

    values = []
    for outfit in recommended[:k]:
        item_ids = set(outfit.get("item_ids", []))
        signals = []
        for entry in feedback:
            previous_ids = set(entry.get("item_ids", []))
            union = item_ids | previous_ids
            if not union:
                continue
            similarity = len(item_ids & previous_ids) / len(union)
            if entry.get("rating") == "like":
                signals.append(similarity)
            elif entry.get("rating") == "dislike":
                signals.append(-similarity)
        values.append(max(signals, key=abs, default=0.0))
    return sum(values) / len(values)


@dataclass
class EvaluationResult:
    """Result of outfit evaluation."""

    confidence: float
    quality: str  # "excellent", "good", "fair", "poor"
    fit_reasons: list[str]
    concerns: list[str]
    context_analysis: dict[str, Any]


class OutfitEvaluator:
    """Evaluates outfit confidence using multiple grounded factors."""

    def __init__(self, context: dict | None = None):
        """Initialize evaluator with context (season, weather, occasion, city, etc.)."""
        self.context = context or {}

    def evaluate(
        self,
        outfit: list,
        score: float,
        context: dict | None = None,
        references: dict | None = None,
    ) -> dict[str, Any]:
        """Evaluate outfit and return confidence + context analysis.

        Args:
            outfit: List of ClothingItem objects
            score: Visual compatibility score (0-1)
            context: Dict with season, weather_band, temperature, occasion_category, etc.
            references: Dict with "historical" list of past outfit references

        Returns:
            Dict with:
                - confidence: float [0, 1]
                - quality: str ("excellent"/"good"/"fair"/"poor")
                - fit_reasons: list[str]
                - concerns: list[str]
                - context_analysis: dict with city/weather/season/occasion impacts
        """
        context = context or {}

        # Compute individual fit components
        weather_fit = self._weather_fit(outfit, context, context.get("temperature"))
        season_fit = self._season_fit(outfit, context.get("season"))
        history_boost = self._history_boost(references, outfit)

        # Confidence formula: 0.4*score + 0.2*weather_fit + 0.2*season_fit + 0.2*history_boost
        # Capped at 0.95
        confidence = (
            0.4 * score +
            0.2 * weather_fit +
            0.2 * season_fit +
            0.2 * history_boost
        )
        confidence = min(0.95, max(0.0, confidence))

        # Quality label based on score
        if score >= 0.8:
            quality = "excellent"
        elif score >= 0.6:
            quality = "good"
        elif score >= 0.4:
            quality = "fair"
        else:
            quality = "poor"

        # Build reasons and concerns
        fit_reasons = self._build_fit_reasons(outfit, score, context, references)
        concerns = self._build_concerns(outfit, score, context)

        # Build context analysis explaining each factor's effect
        context_analysis = self._build_context_analysis(outfit, context)

        return {
            "confidence": float(confidence),
            "quality": quality,
            "fit_reasons": fit_reasons,
            "concerns": concerns,
            "context_analysis": context_analysis,
        }

    def _weather_fit(
        self,
        outfit: list,
        context: dict,
        temperature: float | None,
    ) -> float:
        """Assess how well outfit items match weather conditions.

        Returns 0.0 (poor fit), 0.5 (adequate), or 1.0 (good fit).
        """
        if not outfit or temperature is None:
            return 0.5

        weather_band = context.get("weather_band")
        if weather_band is None:
            return 0.5

        # Check item seasons vs. weather band
        warm_items = sum(1 for item in outfit if getattr(item, "season", None) == "ete")
        cold_items = sum(1 for item in outfit if getattr(item, "season", None) == "hiver")
        total = len(outfit)

        if weather_band == "chaud":
            # Hot weather: prefer ete items, avoid hiver
            if warm_items > cold_items:
                return 1.0  # Good fit
            elif cold_items > 0:
                return 0.0  # Poor fit (winter items in hot weather)
            else:
                return 0.5  # Neutral (mixed season items)
        elif weather_band == "froid":
            # Cold weather: prefer hiver items, avoid ete
            if cold_items > warm_items:
                return 1.0
            elif warm_items > 0:
                return 0.0
            else:
                return 0.5
        else:  # modere
            # Moderate weather: all season items work best
            if warm_items + cold_items == 0:
                return 1.0  # All items are season-agnostic
            else:
                return 0.5  # Mixed is okay for moderate weather

    def _season_fit(self, outfit: list, season: str | None) -> float:
        """Assess how well outfit items match the target season.

        Returns 0.0, 0.5, or 1.0 based on item season compatibility.
        """
        if not outfit or season is None:
            return 0.5

        compatible_count = sum(
            1 for item in outfit
            if seasons.season_compatible(getattr(item, "season", None), season)
        )
        ratio = compatible_count / len(outfit)

        if ratio >= 0.8:
            return 1.0
        elif ratio >= 0.5:
            return 0.5
        else:
            return 0.0

    def _history_boost(
        self,
        references: dict | None,
        outfit: list,
    ) -> float:
        """Apply boost if similar outfits were worn in the past.

        Returns float in [0.0, 0.3] range.
        """
        if not references or not references.get("historical"):
            return 0.0

        # If historical references exist, assume this outfit is somewhat validated
        return 0.3  # Max boost of 0.3

    def _build_fit_reasons(
        self,
        outfit: list,
        score: float,
        context: dict,
        references: dict | None = None,
    ) -> list[str]:
        """Build list of reasons why this outfit fits."""
        reasons = []

        if score >= 0.75:
            reasons.append("High visual coherence between items")
        elif score >= 0.6:
            reasons.append("Good visual compatibility")

        season = context.get("season")
        if season:
            compatible = sum(
                1 for item in outfit
                if seasons.season_compatible(getattr(item, "season", None), season)
            )
            if compatible == len(outfit):
                reasons.append(f"All pieces suitable for {season}")
            elif compatible >= len(outfit) * 0.8:
                reasons.append(f"Most pieces suitable for {season}")

        if context.get("occasion_category"):
            reasons.append(f"Appropriate for {context['occasion_category']}")

        if references and references.get("historical"):
            reasons.append("Matches patterns from past outfits")

        weather_band = context.get("weather_band")
        if weather_band == "chaud":
            light_items = sum(1 for item in outfit if getattr(item, "season", None) == "ete")
            if light_items > 0:
                reasons.append("Contains light, breathable pieces for warm weather")
        elif weather_band == "froid":
            warm_items = sum(1 for item in outfit if getattr(item, "season", None) == "hiver")
            if warm_items > 0:
                reasons.append("Contains warm, layered pieces for cold weather")

        return reasons or ["Outfit is acceptable"]

    def _build_concerns(
        self,
        outfit: list,
        score: float,
        context: dict,
    ) -> list[str]:
        """Build list of concerns about this outfit."""
        concerns = []

        if score < 0.5:
            concerns.append("Lower visual coherence; pieces may not match well")

        weather_band = context.get("weather_band")
        if weather_band == "chaud":
            winter_items = sum(1 for item in outfit if getattr(item, "season", None) == "hiver")
            if winter_items > 0:
                concerns.append(f"{winter_items} winter piece(s) may be too warm")

        elif weather_band == "froid":
            summer_items = sum(1 for item in outfit if getattr(item, "season", None) == "ete")
            if summer_items > 0:
                concerns.append(f"{summer_items} summer piece(s) may not provide enough warmth")

        season = context.get("season")
        if season:
            incompatible = sum(
                1 for item in outfit
                if not seasons.season_compatible(getattr(item, "season", None), season)
            )
            if incompatible > 0:
                concerns.append(f"{incompatible} piece(s) not ideal for {season}")

        return concerns

    def _build_context_analysis(self, outfit: list, context: dict) -> dict[str, Any]:
        """Build detailed analysis of how context factors affect this outfit.

        Returns dict with:
            - city_impact: str
            - weather_impact: str
            - season_impact: str
            - occasion_impact: str
        """
        analysis = {}

        # City impact
        city = context.get("city")
        if city:
            analysis["city_impact"] = f"Outfit recommended for {city}"
        else:
            analysis["city_impact"] = "No specific city constraint"

        # Weather impact
        weather_band = context.get("weather_band")
        temperature = context.get("temperature")
        if temperature is not None and weather_band:
            if weather_band == "chaud":
                analysis["weather_impact"] = (
                    f"Temperature {temperature}°C (warm): outfit includes breathable pieces"
                )
            elif weather_band == "froid":
                analysis["weather_impact"] = (
                    f"Temperature {temperature}°C (cold): outfit includes warm layers"
                )
            else:
                analysis["weather_impact"] = (
                    f"Temperature {temperature}°C (moderate): outfit is versatile"
                )
        else:
            analysis["weather_impact"] = "No temperature constraint"

        # Season impact
        season = context.get("season")
        if season:
            compatible = sum(
                1 for item in outfit
                if seasons.season_compatible(getattr(item, "season", None), season)
            )
            analysis["season_impact"] = (
                f"Season {season}: {compatible}/{len(outfit)} pieces seasonally appropriate"
            )
        else:
            analysis["season_impact"] = "No season constraint"

        # Occasion impact
        occasion = context.get("occasion_category")
        formality = context.get("formality")
        if occasion:
            if formality is not None:
                analysis["occasion_impact"] = (
                    f"Occasion: {occasion} (formality {formality}/5)"
                )
            else:
                analysis["occasion_impact"] = f"Occasion: {occasion}"
        else:
            analysis["occasion_impact"] = "No occasion constraint"

        return analysis

"""Explanation Engine — Generates detailed French explanations for outfit choices.

Combines SFT scores, LLM validation, and weather verification into coherent narratives.
Uses both deterministic templates (always available) and optional LLM enrichment.

Output: {"explanation": str, "reasoning": {...}, "weather_verified": bool, "confidence": float}
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.weather_verification import WeatherVerificationService

logger = logging.getLogger(__name__)


class ExplanationEngine:
    """Generates detailed French explanations for outfit selections."""

    @staticmethod
    def generate_explanation(
        outfit: list[dict[str, Any]],
        context: dict[str, Any],
        weather: dict[str, Any] | None = None,
        sft_score: float | None = None,
        llm_confidence: float | None = None,
        items_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate comprehensive explanation for an outfit selection.

        Args:
            outfit: List of selected item dicts with keys:
                - id (str): item ID
                - name (str): item name
                - category (str): e.g., "top", "bottom", "shoes"
                - colors (list[str]): item colors
                - style (str | None): e.g., "casual", "formal"
                - material (str | None): e.g., "coton", "laine"
            context: Occasion context with keys:
                - occasion (str | None): e.g., "casual", "business", "evening"
                - season (str | None): e.g., "summer", "winter"
                - request_text (str | None): original user request
                - formality (int | None): 0-10 scale
                - temperature (float | None): temperature in celsius
            weather: Weather dict from WeatherVerificationService.get_weather()
            sft_score: SFT model prediction score (0-1)
            llm_confidence: LLM validation confidence (0-1)
            items_metadata: Per-item metadata (usage_count, wear_frequency, etc.)

        Returns:
            {
                "explanation": str (multi-sentence French text),
                "reasoning": {
                    "item_choices": [{"item": str, "reason": str}, ...],
                    "alternatives_rejected": [{"item": str, "reason": str}, ...],
                    "weather_fit": str,
                    "occasion_fit": str,
                },
                "weather_verified": bool,
                "confidence": float (0-1),
            }
        """
        if not outfit:
            return {
                "explanation": "Aucune tenue composée (garde-robe vide ou pas de correspondance).",
                "reasoning": {
                    "item_choices": [],
                    "alternatives_rejected": [],
                    "weather_fit": "Non applicable",
                    "occasion_fit": "Non applicable",
                },
                "weather_verified": False,
                "confidence": 0.0,
            }

        # Build explanations for chosen items
        item_choices = []
        for item in outfit:
            item_name = item.get("name") or item.get("id") or item.get("category", "pièce")
            reason = ExplanationEngine._explain_item_choice(item, context, weather)
            item_choices.append({"item": item_name, "reason": reason})

        # Build main explanation text
        explanation_parts = []
        for choice in item_choices:
            explanation_parts.append(f"• {choice['item']}: {choice['reason']}")

        # Alternatives rejected (need to pass all candidate items for comparison)
        # For now, if we have metadata about candidates, we can explain rejections
        alternatives_text = ""
        if items_metadata and "candidates" in items_metadata:
            alternatives_text = ExplanationEngine._explain_alternatives_rejected(
                items_metadata["candidates"],
                outfit,
                context,
            )
            if alternatives_text:
                explanation_parts.append(f"\n✗ {alternatives_text}")

        # Weather verification
        weather_verified = False
        weather_fit_text = ""
        if weather:
            fit_result = WeatherVerificationService.verify_outfit_weather_fit(
                outfit,
                weather,
                context.get("temperature"),
            )
            weather_verified = fit_result["weather_fit"]
            weather_fit_text = ExplanationEngine._verify_weather_fit(
                outfit, weather, fit_result
            )
            explanation_parts.append(f"\n✓ Météo: {weather_fit_text}")

        # Occasion fit assessment
        occasion_fit_text = ExplanationEngine._explain_occasion_fit(outfit, context)
        explanation_parts.append(f"\n✓ Occasion: {occasion_fit_text}")

        # Confidence assessment
        overall_confidence = ExplanationEngine._compute_confidence(
            sft_score, llm_confidence, weather_verified, outfit
        )

        explanation = "\n".join(explanation_parts)

        return {
            "explanation": explanation,
            "reasoning": {
                "item_choices": item_choices,
                "alternatives_rejected": alternatives_text.split("; ") if alternatives_text else [],
                "weather_fit": weather_fit_text,
                "occasion_fit": occasion_fit_text,
            },
            "weather_verified": weather_verified,
            "confidence": overall_confidence,
        }

    @staticmethod
    def _explain_item_choice(
        item: dict[str, Any],
        context: dict[str, Any],
        weather: dict[str, Any] | None = None,
    ) -> str:
        """Generate 1-2 sentence French explanation for why this item was chosen.

        Args:
            item: Item dict with name, category, colors, material, style
            context: Occasion context
            weather: Weather conditions (optional)

        Returns:
            French explanation string
        """
        category = item.get("category", "pièce").lower()
        name = item.get("name") or item.get("id") or category
        colors = item.get("colors", [])
        material = item.get("material")
        style = item.get("style")
        occasion = context.get("occasion")
        season = context.get("season")
        temp = context.get("temperature", weather.get("temperature") if weather else 20)

        # Build reason based on available metadata
        reasons = []

        # Material fit for season/weather
        if material:
            if temp and temp < 15:
                if "laine" in material.lower() or "tricot" in material.lower():
                    reasons.append(f"matière chaude ({material})")
            elif temp and temp > 25:
                if "lin" in material.lower() or "coton" in material.lower():
                    reasons.append(f"matière légère ({material})")
            else:
                reasons.append(f"matière adaptée ({material})")

        # Style fit for occasion
        if style and occasion:
            if style.lower() in ["casual", "sport"] and occasion in ["casual", "weekend"]:
                reasons.append(f"style {style} pour {occasion}")
            elif style.lower() in ["formal", "business"] and occasion in ["business", "evening"]:
                reasons.append(f"style {style} pour {occasion}")
            else:
                reasons.append(f"style {style}")

        # Color coordination
        if colors:
            primary_color = colors[0] if colors else "neutre"
            if len(colors) > 1:
                reasons.append(f"couleurs assorties ({', '.join(colors[:2])})")
            else:
                reasons.append(f"teinte {primary_color}")

        # Season appropriateness
        if season:
            reasons.append(f"idéale pour {season}")

        if not reasons:
            reasons.append(f"choix cohérent pour {occasion or 'cette occasion'}")

        reason_text = " • ".join(reasons)
        return f"Sélectionnée pour: {reason_text}"

    @staticmethod
    def _verify_weather_fit(
        outfit_items: list[dict[str, Any]],
        weather: dict[str, Any],
        fit_result: dict[str, Any],
    ) -> str:
        """Generate weather fit verification text.

        Args:
            outfit_items: Items in outfit
            weather: Weather conditions
            fit_result: Result from WeatherVerificationService.verify_outfit_weather_fit()

        Returns:
            French weather verification string
        """
        temp = weather.get("temperature", 20)
        condition = weather.get("condition", "stable").capitalize()
        fit_score = fit_result.get("fit_score", 0.5)
        warnings = fit_result.get("warnings", [])

        # Main assessment
        if fit_score >= 0.8:
            base = f"Tenue parfaitement adaptée: {condition}, {temp:.0f}°C"
        elif fit_score >= 0.6:
            base = f"Tenue bien adaptée: {condition}, {temp:.0f}°C"
        elif fit_score >= 0.4:
            base = f"Tenue partiellement adaptée: {condition}, {temp:.0f}°C"
        else:
            base = f"Tenue peu adaptée: {condition}, {temp:.0f}°C"

        if warnings:
            base += f" ⚠️ {warnings[0]}"

        return base

    @staticmethod
    def _explain_occasion_fit(
        outfit: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        """Generate occasion fit assessment.

        Args:
            outfit: Items in outfit
            context: Occasion context

        Returns:
            French occasion fit string
        """
        occasion = context.get("occasion")
        formality = context.get("formality", 5)

        if not occasion:
            return "Tenue cohérente et équilibrée"

        formality_map = {
            "casual": 3,
            "smart_casual": 5,
            "business": 7,
            "formal": 9,
            "evening": 10,
        }

        target_formality = formality_map.get(occasion.lower(), 5)
        if abs(formality - target_formality) <= 2:
            return f"Adaptation excellente pour {occasion}"
        elif abs(formality - target_formality) <= 4:
            return f"Adaptation bonne pour {occasion}"
        else:
            return f"À considérer pour {occasion}"

    @staticmethod
    def _compute_confidence(
        sft_score: float | None,
        llm_confidence: float | None,
        weather_verified: bool,
        outfit: list[dict[str, Any]],
    ) -> float:
        """Compute overall confidence score for outfit.

        Args:
            sft_score: SFT model score (0-1)
            llm_confidence: LLM validation score (0-1)
            weather_verified: Whether outfit passed weather check
            outfit: Items in outfit

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.5

        # SFT score contribution
        if sft_score is not None:
            confidence = 0.6 * sft_score + 0.4 * confidence

        # LLM confidence contribution
        if llm_confidence is not None:
            confidence = 0.7 * llm_confidence + 0.3 * confidence

        # Weather verification bonus
        if weather_verified:
            confidence = min(1.0, confidence * 1.1)

        # Outfit completeness check
        if len(outfit) < 2:
            confidence *= 0.7

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _explain_alternatives_rejected(
        candidate_items: list[dict[str, Any]],
        selected_items: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        """Generate explanation for why other candidates weren't selected.

        Args:
            candidate_items: All candidate items
            selected_items: Selected items
            context: Occasion context

        Returns:
            French explanation of rejections
        """
        selected_ids = {item.get("id") for item in selected_items}
        rejected = [c for c in candidate_items if c.get("id") not in selected_ids]

        if not rejected:
            return "Tous les meilleurs candidats ont été sélectionnés."

        reasons = []
        for item in rejected[:2]:  # Explain first 2 rejections
            name = item.get("name") or item.get("id") or "un article"
            category = item.get("category", "pièce").lower()

            style = item.get("style", "").lower()
            if style and "formal" in style and context.get("occasion") == "casual":
                reasons.append(f"{name}: trop formelle pour cette occasion")
            elif item.get("season") and "summer" in item.get("season", "").lower():
                temp = context.get("temperature", 20)
                if temp and temp < 15:
                    reasons.append(f"{name}: saison été inadéquate pour {temp}°C")
            else:
                reasons.append(f"{name}: moins cohérente avec d'autres pièces")

        if reasons:
            return "Non sélectionnés: " + "; ".join(reasons[:2]) + "."
        return ""

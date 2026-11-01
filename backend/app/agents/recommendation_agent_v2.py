"""RecommendationAgentV2 — SFT + LLM + Weather Verification Pipeline.

New orchestration layer combining:
1. Real weather fetching + verification
2. SFT model for outfit composition scoring
3. LLM validation and reasoning
4. Detailed French explanations

Replaces LangGraph for v2 path while maintaining backwards compatibility.
Pipeline: weather → filter → SFT → LLM → explain → combine scores.

Gracefully degrades when torch/LLM unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.db import vector_store
from app.ml.explanation_engine import ExplanationEngine
from app.ml.recommendation_llm import RecommendationToolSandbox, run_agent as llm_run_agent
from app.services.weather_verification import WeatherVerificationService

logger = logging.getLogger(__name__)

# Optional imports
try:
    import torch

    _TORCH_AVAILABLE = True
except Exception:
    _TORCH_AVAILABLE = False


class RecommendationAgentV2(BaseAgent):
    """Outfit recommendation using SFT + LLM + weather verification pipeline."""

    name = "recommendation_agent_v2"

    # Weighting for combined score
    _ALPHA = 0.4  # SFT weight
    _BETA = 0.3  # LLM weight
    _GAMMA = 0.3  # Compatibility weight

    def run(
        self,
        *,
        wardrobe_items: list,
        occasion: str | None = None,
        season: str | None = None,
        temperature: float | None = None,
        weather: str | None = None,
        city: str | None = None,
        llm_agent: Any = None,
        db: Any = None,
        top_k: int = 3,
        request_text: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Main entry point for outfit recommendation.

        Maintains v1 signature for backwards compatibility.

        Args:
            wardrobe_items: List of item objects with id, category, colors, etc.
            occasion: Occasion name (e.g., "casual", "business", "evening")
            season: Season name (e.g., "summer", "winter")
            temperature: Temperature in celsius
            weather: Weather condition string (e.g., "sunny", "rainy")
            city: City name for weather lookup
            llm_agent: Optional LLM agent for validation
            db: Optional database connection
            top_k: Number of outfits to return
            request_text: User's original request
            **kwargs: Additional arguments (forwarded for compatibility)

        Returns:
            {
                "outfits": [
                    {
                        "item_ids": list[str],
                        "explanation": str,
                        "scores": {
                            "sft": float,
                            "llm": float,
                            "combined": float,
                        },
                        "weather_fit": bool,
                        "confidence": float,
                        ... (other v1 fields for compatibility)
                    }
                ]
            }
        """
        # Extract user_id from wardrobe items
        user_id = self._extract_user_id(wardrobe_items, db)

        # Guard: empty wardrobe
        if not wardrobe_items:
            return {"outfits": []}

        try:
            # Pipeline steps
            # 1. Fetch real weather
            weather_data = self._fetch_weather(city, temperature, weather)

            # 2. Filter candidates by season + weather constraints
            filtered_items = self._filter_candidates(wardrobe_items, season, weather_data)

            if not filtered_items:
                # Fallback: use all items if filtering yields nothing
                filtered_items = wardrobe_items

            # 3. Load SFT model (if available)
            sft_model = self._load_sft_model(user_id)

            # 4. Score items with SFT
            sft_scores = self._score_with_sft(
                sft_model,
                filtered_items,
                occasion,
                season,
                temperature,
                weather_data,
            )

            # 5. Compose outfits (deterministic greedy for now)
            outfit_candidates = self._compose_outfit_candidates(
                filtered_items, sft_scores, top_k
            )

            # 6. Score with LLM validation (optional)
            llm_scores = {}
            if llm_agent:
                llm_scores = self._score_with_llm(
                    outfit_candidates,
                    llm_agent,
                    wardrobe_items,
                    context={
                        "occasion": occasion,
                        "season": season,
                        "temperature": temperature,
                    },
                    weather_data=weather_data,
                )

            # 7. Generate explanations
            outfits = []
            for outfit_idx, outfit_items in enumerate(outfit_candidates):
                self._current_outfit_idx = outfit_idx  # Track for LLM lookup
                outfit_dict = self._build_outfit_dict(
                    outfit_items,
                    sft_scores,
                    llm_scores,
                    weather_data,
                    occasion,
                    season,
                    temperature,
                    request_text,
                )
                outfits.append(outfit_dict)

            return {"outfits": outfits}

        except Exception as e:
            logger.exception(f"Error in RecommendationAgentV2: {e}")
            # Fallback: return deterministic outfit
            return self._fallback_outfit(wardrobe_items, top_k)

    def _extract_user_id(self, wardrobe_items: list, db: Any = None) -> str:
        """Extract user_id from wardrobe items or database."""
        if wardrobe_items:
            first = wardrobe_items[0]
            user_id = getattr(first, "owner_id", None)
            if user_id:
                return str(user_id)[:8]
        return ""

    def _fetch_weather(
        self,
        city: str | None,
        temperature: float | None,
        weather: str | None,
    ) -> dict[str, Any]:
        """Fetch weather from API or use provided values.

        Args:
            city: City name for API lookup
            temperature: Direct temperature override
            weather: Direct weather condition override

        Returns:
            Weather dict from WeatherVerificationService
        """
        try:
            if city:
                weather_data = WeatherVerificationService.get_weather(city)
            else:
                # Create a synthetic weather dict from provided values
                weather_data = {
                    "temperature": temperature or 20.0,
                    "condition": (weather or "sunny").lower(),
                    "humidity": 50,
                    "wind_speed": 0.0,
                    "pressure": 1013,
                    "uv_index": None,
                    "confidence": 0.7 if temperature and weather else 0.5,
                    "cached": False,
                    "error": None,
                }
            return weather_data
        except Exception as e:
            logger.warning(f"Error fetching weather: {e}")
            return {
                "temperature": temperature or 20.0,
                "condition": (weather or "sunny").lower(),
                "humidity": 50,
                "wind_speed": 0.0,
                "pressure": 1013,
                "uv_index": None,
                "confidence": 0.3,
                "cached": False,
                "error": str(e),
            }

    def _filter_candidates(
        self,
        items: list,
        season: str | None,
        weather_data: dict[str, Any],
    ) -> list:
        """Filter items by season and weather constraints.

        Args:
            items: Wardrobe items
            season: Current season
            weather_data: Weather conditions

        Returns:
            Filtered items list. Falls back to all items only if filtering is too strict
            AND no extreme weather mismatches were detected.
        """
        filtered = []
        extreme_mismatch_count = 0

        for item in items:
            # Check season match (only filter if item has explicit season different from "all")
            if season:
                item_season = getattr(item, "season", None)
                if item_season and item_season.lower() != "all":
                    if season.lower() not in str(item_season).lower():
                        continue  # Skip items from wrong season

            # Check temperature/material appropriateness
            temp = weather_data.get("temperature", 20)
            material = getattr(item, "material", None)
            if material:
                material_lower = str(material).lower()
                # Only filter extreme mismatches
                if temp < 5 and "lin" in material_lower:
                    extreme_mismatch_count += 1
                    continue  # Linen way too cold
                if temp > 30 and "laine" in material_lower:
                    extreme_mismatch_count += 1
                    continue  # Wool way too hot

            filtered.append(item)

        # Only fallback to all items if we filtered out very few items
        # or if no extreme mismatches were detected
        if not filtered:
            if extreme_mismatch_count > 0:
                # We removed items due to extreme weather, don't fallback completely
                # Instead, be more lenient: allow some borderline cases
                filtered = []
                for item in items:
                    temp = weather_data.get("temperature", 20)
                    material = getattr(item, "material", None)
                    if material:
                        material_lower = str(material).lower()
                        # Only skip the most extreme cases
                        if temp < 0 and "lin" in material_lower:
                            continue
                        if temp > 35 and "laine" in material_lower:
                            continue
                    filtered.append(item)
            
            if not filtered:
                # Last resort: use all items
                filtered = items

        return filtered

    def _load_sft_model(self, user_id: str) -> Any:
        """Load SFT model for user.

        Args:
            user_id: User ID (first 8 chars)

        Returns:
            Loaded model or None if unavailable
        """
        if not _TORCH_AVAILABLE:
            return None

        try:
            from app.ml.outfit_composition_sft_model import load_or_init

            model = load_or_init(user_id if user_id else None)
            return model
        except Exception as e:
            logger.warning(f"Could not load SFT model: {e}")
            return None

    def _score_with_sft(
        self,
        model: Any,
        items: list,
        occasion: str | None,
        season: str | None,
        temperature: float | None,
        weather_data: dict[str, Any],
    ) -> dict[str, float]:
        """Score items using SFT model.

        Args:
            model: Loaded SFT model or None
            items: Candidate items
            occasion: Occasion string
            season: Season string
            temperature: Temperature
            weather_data: Weather conditions

        Returns:
            Dict mapping item id → sft score (0-1)
        """
        scores = {}

        if not model or not _TORCH_AVAILABLE:
            # Fallback: heuristic scoring
            for item in items:
                item_id = str(getattr(item, "id", ""))
                scores[item_id] = 0.7  # Neutral score
            return scores

        try:
            # Fetch embeddings for items
            item_ids = [str(getattr(item, "id", "")) for item in items]
            embeddings_dict = vector_store.fetch_embeddings(item_ids)

            embeddings = []
            valid_items = []
            for item in items:
                item_id = str(getattr(item, "id", ""))
                emb = embeddings_dict.get(item_id)
                if emb is not None:
                    embeddings.append(np.array(emb, dtype=np.float32))
                    valid_items.append(item)

            if not embeddings:
                # No embeddings available, return neutral scores
                for item in items:
                    item_id = str(getattr(item, "id", ""))
                    scores[item_id] = 0.7
                return scores

            # Stack embeddings and call model.predict()
            embeddings_batch = np.stack(embeddings)  # (n_items, 512)

            result = model.predict(
                embeddings_batch,
                item_ids=[str(getattr(item, "id", "")) for item in valid_items],
                season=season or "spring",
                weather=weather_data.get("condition", "sunny"),
                occasion=occasion or "casual",
                formality=None,
                threshold=0.5,
            )


            # Extract scores from result
            if result and "scores" in result:
                predicted_ids = result.get("item_ids", [])
                predicted_scores = result.get("scores", [])
                for idx, item_id in enumerate(predicted_ids):
                    if idx < len(predicted_scores):
                        scores[item_id] = float(predicted_scores[idx])

            # Fill in missing scores with neutral value
            for item in items:
                item_id = str(getattr(item, "id", ""))
                if item_id not in scores:
                    scores[item_id] = 0.7

            return scores

        except Exception as e:
            logger.warning(f"Error scoring with SFT: {e}")
            # Fallback: heuristic scoring
            for item in items:
                item_id = str(getattr(item, "id", ""))
                scores[item_id] = 0.7
            return scores

    def _score_with_llm(
        self,
        outfit_candidates: list[list],
        llm_agent: Any,
        wardrobe_items: list,
        context: dict[str, Any],
        weather_data: dict[str, Any] | None = None,
    ) -> dict[int, float]:
        """Score outfits using LLM validation.

        Args:
            outfit_candidates: List of outfits (each outfit is list of items)
            llm_agent: LLM agent to use
            wardrobe_items: All wardrobe items (for sandbox context)
            context: Context dict with occasion, season, etc.
            weather_data: Weather conditions (optional)

        Returns:
            Dict mapping outfit index → llm confidence score
        """
        scores = {}

        if not llm_agent:
            return scores

        try:
            # Convert wardrobe items to dict format for sandbox
            wardrobe_dicts = []
            for item in wardrobe_items:
                wardrobe_dicts.append({
                    "id": str(getattr(item, "id", "")),
                    "name": getattr(item, "name", ""),
                    "category": getattr(item, "category", ""),
                    "colors": getattr(item, "colors", []) or [],
                    "material": getattr(item, "material", ""),
                    "style": getattr(item, "style", ""),
                    "season": getattr(item, "season", ""),
                })

            for outfit_idx, outfit_items in enumerate(outfit_candidates):
                # Build task for LLM
                item_dicts = []
                for item in outfit_items:
                    item_dicts.append({
                        "id": str(getattr(item, "id", "")),
                        "name": getattr(item, "name", ""),
                        "category": getattr(item, "category", ""),
                        "colors": getattr(item, "colors", []) or [],
                    })

                task = {
                    "type": "validate_outfit",
                    "outfit_items": item_dicts,
                    "occasion": context.get("occasion", "casual"),
                    "season": context.get("season", "spring"),
                }

                # Create sandbox for LLM
                sandbox = RecommendationToolSandbox(
                    wardrobe_items=wardrobe_dicts,
                    weather_data=weather_data or {},
                    occasion=context.get("occasion"),
                    season=context.get("season"),
                )

                # Call LLM using correct API
                try:
                    result = llm_run_agent(task, sandbox, user_id=None)
                    if result and isinstance(result, dict):
                        # Extract confidence from LLM result
                        # Parse from explanation or use default
                        confidence = self._extract_llm_confidence(result.get("explanation", ""))
                        scores[outfit_idx] = float(confidence)
                    else:
                        scores[outfit_idx] = 0.7
                except Exception as e:
                    logger.debug(f"LLM validation error for outfit {outfit_idx}: {e}")
                    scores[outfit_idx] = 0.7

            return scores

        except Exception as e:
            logger.warning(f"Error scoring with LLM: {e}")
            return {}

    def _extract_llm_confidence(self, explanation: str) -> float:
        """Extract confidence score from LLM explanation.

        Args:
            explanation: LLM explanation text

        Returns:
            Confidence score (0-1)
        """
        import re

        # Look for confidence mention in explanation
        match = re.search(r'confidence["\']?\s*:?\s*([0-9]*\.?[0-9]+)', explanation, re.IGNORECASE)
        if match:
            try:
                conf = float(match.group(1))
                return max(0.0, min(1.0, conf))
            except (ValueError, IndexError):
                pass

        # Default: very coherent explanations get 0.85, others get 0.7
        if len(explanation) > 100 and ("parfait" in explanation.lower() or "excellent" in explanation.lower()):
            return 0.85
        return 0.75

    def _compose_outfit_candidates(
        self,
        items: list,
        sft_scores: dict[str, float],
        top_k: int = 3,
    ) -> list[list]:
        """Compose outfit candidates using greedy selection without duplicates.

        Args:
            items: Candidate items
            sft_scores: Item SFT scores
            top_k: Number of outfits to generate

        Returns:
            List of outfits, each outfit is list of items
        """
        # Group items by category
        by_category = {}
        for item in items:
            category = str(getattr(item, "category", "other")).lower()
            by_category.setdefault(category, []).append(item)

        # Sort each category by SFT score (descending)
        for category in by_category:
            by_category[category].sort(
                key=lambda x: sft_scores.get(str(getattr(x, "id", "")), 0.5),
                reverse=True,
            )

        # Generate top_k outfits without item repetition
        outfits = []
        used_items = set()  # Track items already used

        for _ in range(top_k):
            outfit = []

            # Try to pick best available item from each category
            for category in ["robe", "haut", "bas", "chaussures"]:
                candidates = by_category.get(category, [])
                if not candidates:
                    continue

                # Find first unused item in this category
                for item in candidates:
                    item_id = str(getattr(item, "id", ""))
                    if item_id not in used_items:
                        outfit.append(item)
                        used_items.add(item_id)
                        break

            if outfit:
                outfits.append(outfit)

        # If we don't have enough outfits, generate more allowing repetition
        if len(outfits) < top_k:
            for _ in range(top_k - len(outfits)):
                outfit = []
                for category in ["robe", "haut", "bas", "chaussures"]:
                    candidates = by_category.get(category, [])
                    if candidates:
                        # Just pick the best one
                        outfit.append(candidates[0])
                if outfit:
                    outfits.append(outfit)

        return outfits[:top_k]

    def _build_outfit_dict(
        self,
        outfit_items: list,
        sft_scores: dict[str, float],
        llm_scores: dict,
        weather_data: dict[str, Any],
        occasion: str | None,
        season: str | None,
        temperature: float | None,
        request_text: str | None,
    ) -> dict[str, Any]:
        """Build complete outfit dict with all metadata.

        Args:
            outfit_items: Items in outfit
            sft_scores: SFT scores dict
            llm_scores: LLM scores dict
            weather_data: Weather conditions
            occasion: Occasion string
            season: Season string
            temperature: Temperature
            request_text: User request

        Returns:
            Outfit dict with explanation, scores, etc.
        """
        item_ids = [str(getattr(item, "id", "")) for item in outfit_items]

        # Compute average SFT score
        sft_score = np.mean([sft_scores.get(item_id, 0.7) for item_id in item_ids]) if item_ids else 0.7

        # Get LLM score (llm_scores uses outfit index directly)
        llm_confidence = None
        # Need to track outfit index separately; this is passed as parameter below
        if hasattr(self, '_current_outfit_idx') and self._current_outfit_idx in llm_scores:
            llm_confidence = llm_scores[self._current_outfit_idx]

        # Generate explanation
        context = {
            "occasion": occasion,
            "season": season,
            "temperature": temperature,
            "request_text": request_text,
        }

        # Build item dicts for explanation engine
        outfit_item_dicts = []
        for item in outfit_items:
            item_dict = {
                "id": str(getattr(item, "id", "")),
                "name": getattr(item, "name", ""),
                "category": getattr(item, "category", ""),
                "colors": getattr(item, "colors", []) or [],
                "material": getattr(item, "material", ""),
                "style": getattr(item, "style", ""),
                "season": getattr(item, "season", ""),
            }
            outfit_item_dicts.append(item_dict)

        explanation_result = ExplanationEngine.generate_explanation(
            outfit_item_dicts,
            context,
            weather_data,
            sft_score,
            llm_confidence,
        )

        # Combine scores
        combined_score = self._combine_scores(sft_score, llm_confidence)

        return {
            "item_ids": item_ids,
            "explanation": explanation_result.get("explanation", ""),
            "scores": {
                "sft": float(sft_score),
                "llm": float(llm_confidence) if llm_confidence is not None else None,
                "combined": float(combined_score),
            },
            "weather_fit": explanation_result.get("weather_verified", False),
            "confidence": explanation_result.get("confidence", 0.7),
            "reasoning": explanation_result.get("reasoning", {}),
            # Backwards compatibility fields
            "relevance_score": float(combined_score),
            "critic_score": float(llm_confidence) if llm_confidence is not None else float(combined_score),
            "dl_score": float(sft_score),
            "react_trace": [],
        }

    def _combine_scores(
        self,
        sft_score: float,
        llm_confidence: float | None,
        compatibility_score: float = 0.7,
    ) -> float:
        """Combine SFT + LLM + compatibility scores.

        Args:
            sft_score: SFT model score (0-1)
            llm_confidence: LLM confidence (0-1) or None
            compatibility_score: Base compatibility (0-1)

        Returns:
            Combined score (0-1)
        """
        sft_score = max(0.0, min(1.0, sft_score))
        compatibility_score = max(0.0, min(1.0, compatibility_score))

        if llm_confidence is not None:
            llm_confidence = max(0.0, min(1.0, llm_confidence))
            combined = (
                self._ALPHA * sft_score
                + self._BETA * llm_confidence
                + self._GAMMA * compatibility_score
            )
        else:
            # Normalize weights when LLM unavailable
            alpha = self._ALPHA / (self._ALPHA + self._GAMMA)
            gamma = self._GAMMA / (self._ALPHA + self._GAMMA)
            combined = alpha * sft_score + gamma * compatibility_score

        return max(0.0, min(1.0, combined))

    def _fallback_outfit(self, wardrobe_items: list, top_k: int) -> dict[str, Any]:
        """Generate deterministic fallback outfit when pipeline fails.

        Args:
            wardrobe_items: Available items
            top_k: Number to return

        Returns:
            Outfit dict structure
        """
        # Group by category
        by_category = {}
        for item in wardrobe_items:
            category = str(getattr(item, "category", "")).lower()
            by_category.setdefault(category, []).append(item)

        outfits = []
        for _ in range(top_k):
            outfit = []
            for category in ["robe", "haut", "bas", "chaussures"]:
                candidates = by_category.get(category, [])
                if candidates:
                    outfit.append(candidates[0])

            if outfit:
                outfits.append({
                    "item_ids": [str(getattr(item, "id", "")) for item in outfit],
                    "explanation": "Tenue par défaut (pipeline indisponible)",
                    "scores": {"sft": 0.5, "llm": None, "combined": 0.5},
                    "weather_fit": False,
                    "confidence": 0.3,
                    "reasoning": {},
                    "relevance_score": 0.5,
                    "critic_score": 0.5,
                    "dl_score": 0.5,
                    "react_trace": [],
                })

        return {"outfits": outfits}

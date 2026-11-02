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
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from itertools import product
from typing import Any

import numpy as np

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.db import vector_store
from app.ml import compatibility_model
from app.ml.constraint_parser import ConstraintParser
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

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._ALPHA = settings.recommendation_sft_weight
        self._BETA = settings.recommendation_llm_weight
        self._GAMMA = settings.recommendation_compatibility_weight
        self._NEUTRAL_SCORE = settings.recommendation_neutral_score
        self._constraint_parser = ConstraintParser()
        self._CATEGORIES_ORDER = [
            self._canonical_category(category)
            for category in settings.recommendation_categories_order.split(",")
        ]

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
            constraints = self._constraint_parser.parse(request_text, use_llm=False)
            season = season or constraints.get("season")
            if not occasion and constraints.get("occasions"):
                occasion = constraints["occasions"][0]
            formality = kwargs.get("formality")
            if formality is None:
                formality = self._formality_value(constraints.get("formality"))

            # Pipeline steps
            # 1. Fetch real weather
            weather_data = self._fetch_weather(city, temperature, weather)

            # 2. Filter candidates by season + weather constraints
            filtered_items = self._filter_candidates(wardrobe_items, season, weather_data)
            if not filtered_items:
                return {"outfits": []}

            compatibility_embeddings = self._fetch_compatibility_embeddings(filtered_items)

            # 3. Load models (SFT + optional RLHF policy) via FIX-3 fallback chain
            models = self._load_models(user_id)

            # 4. Score items (uses RLHF policy → SFT → 0.7 neutral, FIX-3)
            sft_scores = self._score_items(
                models,
                filtered_items,
                occasion,
                season,
                temperature,
                weather_data,
                formality=formality,
                embeddings=compatibility_embeddings,
            )
            sft_scores = self._apply_personalization(
                sft_scores, filtered_items, {**kwargs, "constraints": constraints, "formality": formality}
            )

            # 5. Compose complete outfits and rank them by item and style compatibility.
            outfit_candidates = self._compose_outfit_candidates(
                filtered_items,
                sft_scores,
                top_k,
                season=season,
                occasion=occasion,
                compatibility_embeddings=compatibility_embeddings,
            )
            if not outfit_candidates:
                return {"outfits": []}

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
                outfit_dict = self._build_outfit_dict(
                    outfit_items,
                    sft_scores,
                    llm_scores,
                    weather_data,
                    occasion,
                    season,
                    temperature,
                    request_text,
                    outfit_idx=outfit_idx,
                    compatibility_score=self._score_outfit_compatibility(
                        outfit_items,
                        season,
                        occasion,
                        compatibility_embeddings=compatibility_embeddings,
                    ),
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

    @staticmethod
    def _fetch_compatibility_embeddings(items: list) -> dict[str, Any]:
        item_ids = [str(getattr(item, "id", "")) for item in items]
        try:
            embeddings = vector_store.fetch_embeddings(item_ids)
            return {str(item_id): embedding for item_id, embedding in embeddings.items()}
        except Exception:
            logger.warning("Could not load outfit compatibility embeddings", exc_info=True)
            return {}

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
                    "temperature": temperature if temperature is not None else 20.0,
                    "condition": (weather or "sunny").lower(),
                    "humidity": 50,
                    "wind_speed": 0.0,
                    "pressure": 1013,
                    "uv_index": None,
                    "confidence": 0.7 if temperature is not None and weather else 0.5,
                    "cached": False,
                    "error": None,
                }
            return weather_data
        except Exception as e:
            logger.warning(f"Error fetching weather: {e}")
            return {
                "temperature": temperature if temperature is not None else 20.0,
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
        temp = weather_data.get("temperature")
        temp = 20.0 if temp is None else float(temp)
        season_key = self._normalize_season(season)
        weather_filtered = []
        season_filtered = []

        for item in items:
            material = self._normalize_text(getattr(item, "material", "") or "")
            if (temp < 5 and "lin" in material) or (temp > 30 and "laine" in material):
                continue
            weather_filtered.append(item)

            item_seasons = getattr(item, "season", None)
            normalized_item_seasons = {
                self._normalize_season(value)
                for value in re.split(r"[,;/|]", str(item_seasons or ""))
                if value.strip()
            }
            if (
                not season_key
                or not normalized_item_seasons
                or "all" in normalized_item_seasons
                or season_key in normalized_item_seasons
            ):
                season_filtered.append(item)

        if season_filtered:
            return season_filtered
        if weather_filtered and season_key:
            logger.info("No wardrobe items match season %s; relaxing season filter", season)
            return weather_filtered
        return weather_filtered

    @staticmethod
    def _normalize_text(value: Any) -> str:
        normalized = unicodedata.normalize("NFKD", str(value).strip().lower())
        return "".join(char for char in normalized if not unicodedata.combining(char))

    @classmethod
    def _normalize_season(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = cls._normalize_text(value).replace("-", "_").replace(" ", "_")
        if not normalized:
            return None
        aliases = {
            "ete": "summer",
            "summer": "summer",
            "hiver": "winter",
            "winter": "winter",
            "automne": "autumn",
            "fall": "autumn",
            "autumn": "autumn",
            "printemps": "spring",
            "spring": "spring",
            "mi_saison": "mid_season",
            "mid_season": "mid_season",
            "toutes_saisons": "all",
            "all_seasons": "all",
            "all": "all",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _formality_value(value: Any) -> int | None:
        if isinstance(value, (int, float)):
            return max(0, min(10, int(value)))
        normalized = RecommendationAgentV2._normalize_text(value or "")
        return {
            "casual": 2,
            "decontracte": 2,
            "smart_casual": 5,
            "formal": 8,
            "habille": 8,
        }.get(normalized)

    @classmethod
    def _canonical_color(cls, value: Any) -> str:
        color = cls._normalize_text(value)
        return {
            "white": "blanc",
            "black": "noir",
            "blue": "bleu",
            "green": "vert",
            "red": "rouge",
            "yellow": "jaune",
            "grey": "gris",
            "gray": "gris",
            "pink": "rose",
            "brown": "marron",
            "purple": "violet",
        }.get(color, color)

    @classmethod
    def _canonical_category(cls, value: Any) -> str:
        category = cls._normalize_text(value).replace("-", "_").replace(" ", "_")
        aliases = {
            "dress": "dress",
            "robe": "dress",
            "one_piece": "dress",
            "jumpsuit": "dress",
            "combinaison": "dress",
            "top": "top",
            "haut": "top",
            "shirt": "top",
            "chemise": "top",
            "blouse": "top",
            "t_shirt": "top",
            "tshirt": "top",
            "tee": "top",
            "sweater": "top",
            "pullover": "top",
            "knitwear": "top",
            "cardigan": "top",
            "jacket": "top",
            "veste": "top",
            "coat": "top",
            "outerwear": "top",
            "bottom": "bottom",
            "bas": "bottom",
            "trousers": "bottom",
            "pants": "bottom",
            "jean": "bottom",
            "jeans": "bottom",
            "pantalon": "bottom",
            "skirt": "bottom",
            "jupe": "bottom",
            "short": "bottom",
            "shorts": "bottom",
            "legging": "bottom",
            "leggings": "bottom",
            "shoes": "shoes",
            "shoe": "shoes",
            "chaussure": "shoes",
            "chaussures": "shoes",
            "footwear": "shoes",
            "sneaker": "shoes",
            "sneakers": "shoes",
            "basket": "shoes",
            "baskets": "shoes",
            "boot": "shoes",
            "boots": "shoes",
            "sandals": "shoes",
            "sandales": "shoes",
        }
        return aliases.get(category, category)

    def _apply_personalization(
        self, scores: dict[str, float], items: list, context: dict[str, Any]
    ) -> dict[str, float]:
        favorite_styles = {
            self._normalize_text(style)
            for style in (context.get("favorite_styles") or [])
            if style
        }
        usage = {
            str(item_id): value
            for item_id, value in (context.get("usage") or {}).items()
        }
        feedback = context.get("feedback_preferences") or []
        constraints = context.get("constraints") or {}
        requested_styles = {
            self._normalize_text(value) for value in (constraints.get("styles") or [])
        }
        requested_colors = {
            self._canonical_color(value) for value in (constraints.get("colors") or [])
        }
        feedback_by_item: dict[str, float] = {}
        for entry in feedback:
            rating = entry.get("rating")
            adjustment = 0.08 if rating == "like" else -0.08 if rating == "dislike" else 0.0
            for item_id in entry.get("item_ids", []):
                key = str(item_id)
                feedback_by_item[key] = max(
                    -0.16, min(0.16, feedback_by_item.get(key, 0.0) + adjustment)
                )

        adjusted = {}
        cutoff = date.today() - timedelta(days=7)
        for item in items:
            item_id = str(getattr(item, "id", ""))
            score = scores.get(item_id, self._NEUTRAL_SCORE)
            style = self._normalize_text(getattr(item, "style", "") or "")
            if style and style in favorite_styles:
                score += 0.08
            if style and style in requested_styles:
                score += 0.08
            item_colors = getattr(item, "colors", None) or []
            if isinstance(item_colors, str):
                item_colors = [item_colors]
            if isinstance(item_colors, (list, tuple, set)) and requested_colors:
                if requested_colors.intersection(
                    self._canonical_color(color) for color in item_colors
                ):
                    score += 0.1

            formality = context.get("formality")
            if isinstance(formality, (int, float)) and style:
                formal_style = style in {"formal", "business", "elegant", "habille"}
                casual_style = style in {"casual", "sport", "sports", "home", "relax"}
                if formality >= 7:
                    score += 0.08 if formal_style else -0.06 if casual_style else 0.0
                elif formality <= 3:
                    score += 0.06 if casual_style else -0.04 if formal_style else 0.0

            history = usage.get(item_id, {})
            last_worn = history.get("last_worn") if isinstance(history, dict) else None
            if isinstance(last_worn, datetime):
                last_worn = last_worn.date()
            elif isinstance(last_worn, str):
                try:
                    last_worn = date.fromisoformat(last_worn[:10])
                except ValueError:
                    last_worn = None
            if isinstance(last_worn, date) and last_worn >= cutoff:
                score -= 0.08
            score += feedback_by_item.get(item_id, 0.0)
            adjusted[item_id] = float(max(0.0, min(1.0, score)))
        return adjusted

    def _load_models(self, user_id: str) -> dict[str, Any]:
        """Load SFT model and optionally RLHF policy model (FIX-3 fallback chain).

        Fallback chain: RLHF policy → SFT → neutral 0.7.
        If USE_RLHF_MODEL=true but artifact is missing, logs warning and falls back to SFT.
        If SFT also fails, callers fall back to neutral 0.7 scores.

        Args:
            user_id: User ID (first 8 chars)

        Returns:
            dict with keys: 'sft_model', 'policy_model', 'use_rlhf'
        """
        sft_model = None
        policy_model = None
        use_rlhf = False

        # Load SFT model
        if _TORCH_AVAILABLE:
            try:
                from app.ml.outfit_composition_sft_model import load_or_init

                sft_model = load_or_init(user_id if user_id else None)
            except Exception as e:
                logger.warning(f"Could not load SFT model: {e}")

        # Optionally load RLHF policy model (FIX-3)
        if os.environ.get("USE_RLHF_MODEL", "false").lower() == "true":
            try:
                from app.ml import rlhf_policy_model

                loaded = rlhf_policy_model.load_policy_model(user_id)
                if loaded is not None:
                    policy_model = loaded
                    use_rlhf = True
                else:
                    logger.warning(
                        "USE_RLHF_MODEL=true but no checkpoint found, falling back to SFT"
                    )
            except Exception as e:
                logger.warning(
                    f"USE_RLHF_MODEL=true but failed to load policy model: {e}, falling back to SFT"
                )

        return {"sft_model": sft_model, "policy_model": policy_model, "use_rlhf": use_rlhf}

    # Keep old name as alias for backwards compatibility
    def _load_sft_model(self, user_id: str) -> Any:
        """Legacy alias — calls _load_models and returns sft_model for compatibility."""
        return self._load_models(user_id)["sft_model"]

    def _score_items(
        self,
        models: dict[str, Any],
        items: list,
        occasion: str | None,
        season: str | None,
        temperature: float | None,
        weather_data: dict[str, Any],
        *,
        formality: int | None = None,
        embeddings: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        """Score items using RLHF policy model or SFT model (FIX-3 fallback chain).

        If models['use_rlhf'] is True and policy_model is available:
          - Fetch embeddings via vector_store (FIX-1: skip missing, never zero vectors)
          - Mean-pool per-item embeddings into (512,) outfit-level embedding
          - Call policy_model.forward(emb_tensor) → scalar score
          - Assign same score to all items in outfit; missing items get neutral 0.7

        If not use_rlhf: use SFT model path (existing behavior).
        If neither available: return neutral 0.7 dict.

        Args:
            models: dict from _load_models()
            items: Candidate items
            occasion: Occasion string
            season: Season string
            temperature: Temperature
            weather_data: Weather conditions

        Returns:
            Dict mapping item id → score (0-1)
        """
        scores = {}

        use_rlhf: bool = models.get("use_rlhf", False)
        policy_model = models.get("policy_model")
        sft_model = models.get("sft_model")

        # --- RLHF policy path (FIX-1, FIX-3) ---
        if use_rlhf and policy_model is not None and _TORCH_AVAILABLE:
            try:
                item_ids = [str(getattr(item, "id", "")) for item in items]
                embeddings_dict = (
                    embeddings if embeddings is not None
                    else vector_store.fetch_embeddings(item_ids)
                )

                valid_embeddings: list[np.ndarray] = []
                for item_id in item_ids:
                    emb = embeddings_dict.get(item_id)
                    if emb is None:
                        logger.warning(
                            f"_score_items: no embedding for item {item_id} — skipping (FIX-1)"
                        )
                    else:
                        valid_embeddings.append(np.array(emb, dtype=np.float32))

                if valid_embeddings:
                    # Mean-pool valid embeddings → (512,) outfit-level embedding
                    outfit_embedding = np.mean(np.stack(valid_embeddings), axis=0)  # (512,)
                    emb_tensor = torch.tensor(outfit_embedding, dtype=torch.float32).unsqueeze(0)  # (1, 512)
                    with torch.no_grad():
                        raw_score = policy_model.forward(emb_tensor)
                        outfit_score = float(torch.sigmoid(raw_score).squeeze().item())
                else:
                    logger.warning(f"_score_items: no valid embeddings for any item — using neutral {self._NEUTRAL_SCORE}")
                    outfit_score = self._NEUTRAL_SCORE

                # Assign outfit-level score to all items; items with no embedding also get it
                for item in items:
                    item_id = str(getattr(item, "id", ""))
                    scores[item_id] = outfit_score

                return scores

            except Exception as e:
                logger.warning(f"Error scoring with RLHF policy model: {e} — falling back to SFT")
                # Fall through to SFT path

        # --- SFT path (existing behavior, unchanged) ---
        return self._score_with_sft(
            sft_model,
            items,
            occasion,
            season,
            temperature,
            weather_data,
            formality=formality,
            embeddings=embeddings,
        )

    def _score_with_sft(
        self,
        model: Any,
        items: list,
        occasion: str | None,
        season: str | None,
        temperature: float | None,
        weather_data: dict[str, Any],
        *,
        formality: int | None = None,
        embeddings: dict[str, Any] | None = None,
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
                scores[item_id] = self._NEUTRAL_SCORE  # Neutral score
            return scores

        try:
            # Fetch embeddings for items
            item_ids = [str(getattr(item, "id", "")) for item in items]
            embeddings_dict = (
                embeddings if embeddings is not None
                else vector_store.fetch_embeddings(item_ids)
            )

            embedding_vectors = []
            valid_items = []
            for item in items:
                item_id = str(getattr(item, "id", ""))
                emb = embeddings_dict.get(item_id)
                if emb is not None:
                    embedding_vectors.append(np.array(emb, dtype=np.float32))
                    valid_items.append(item)

            if not embedding_vectors:
                # No embeddings available, return neutral scores
                for item in items:
                    item_id = str(getattr(item, "id", ""))
                    scores[item_id] = self._NEUTRAL_SCORE
                return scores

            # Pass embeddings as a list (not pre-stacked): the SFT model's
            # predict() wraps non-list args in [...] before np.stack + unsqueeze(0),
            # so a pre-stacked array would become 4-D and break the model's forward
            # (batch_size, num_items, _ = shape unpacks 3, not 4).

            result = model.predict(
                embedding_vectors,
                item_ids=[str(getattr(item, "id", "")) for item in valid_items],
                season=season or "spring",
                weather=weather_data.get("condition", "sunny"),
                occasion=occasion or "casual",
                formality=formality,
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
                    scores[item_id] = self._NEUTRAL_SCORE

            return scores

        except Exception as e:
            logger.warning(f"Error scoring with SFT: {e}")
            # Fallback: heuristic scoring
            for item in items:
                item_id = str(getattr(item, "id", ""))
                scores[item_id] = self._NEUTRAL_SCORE
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
                        scores[outfit_idx] = self._NEUTRAL_SCORE
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
        *,
        season: str | None = None,
        occasion: str | None = None,
        compatibility_embeddings: dict[str, Any] | None = None,
    ) -> list[list]:
        """Compose and rank complete outfit candidates without duplicate item sets.

        Args:
            items: Candidate items
            sft_scores: Item SFT scores
            top_k: Number of outfits to generate

        Returns:
            List of outfits, each outfit is list of items
        """
        if top_k <= 0:
            return []

        by_category: dict[str, list] = {}
        for item in items:
            category = self._canonical_category(getattr(item, "category", "other"))
            by_category.setdefault(category, []).append(item)

        for category in ("dress", "top", "bottom", "shoes"):
            if category not in by_category:
                continue
            by_category[category].sort(
                key=lambda x: sft_scores.get(str(getattr(x, "id", "")), 0.5),
                reverse=True,
            )

        candidate_limit = min(20, max(10, top_k * 3))
        dresses = by_category.get("dress", [])[:candidate_limit]
        tops = by_category.get("top", [])[:candidate_limit]
        bottoms = by_category.get("bottom", [])[:candidate_limit]
        shoes = by_category.get("shoes", [])[:candidate_limit] or [None]

        candidates: list[tuple[float, list]] = []
        for dress, shoe in product(dresses, shoes):
            outfit = [dress] + ([shoe] if shoe is not None else [])
            candidates.append((
                self._outfit_candidate_score(
                    outfit, sft_scores, season, occasion, compatibility_embeddings
                ),
                outfit,
            ))

        if tops and bottoms:
            for top, bottom, shoe in product(tops, bottoms, shoes):
                outfit = [top, bottom] + ([shoe] if shoe is not None else [])
                candidates.append((
                    self._outfit_candidate_score(
                        outfit, sft_scores, season, occasion, compatibility_embeddings
                    ),
                    outfit,
                ))

        candidates.sort(
            key=lambda candidate: (
                -candidate[0],
                tuple(sorted(str(getattr(item, "id", "")) for item in candidate[1])),
            )
        )
        outfits = []
        seen_item_sets = set()
        for _, outfit in candidates:
            item_set = frozenset(str(getattr(item, "id", "")) for item in outfit)
            if item_set in seen_item_sets:
                continue
            seen_item_sets.add(item_set)
            outfits.append(outfit)
            if len(outfits) >= max(0, top_k):
                break
        return outfits

    def _outfit_candidate_score(
        self,
        outfit: list,
        item_scores: dict[str, float],
        season: str | None = None,
        occasion: str | None = None,
        compatibility_embeddings: dict[str, Any] | None = None,
    ) -> float:
        if not outfit:
            return 0.0
        item_score = float(np.mean([
            item_scores.get(str(getattr(item, "id", "")), self._NEUTRAL_SCORE)
            for item in outfit
        ]))
        compatibility = self._score_outfit_compatibility(
            outfit, season, occasion, compatibility_embeddings=compatibility_embeddings
        )
        return item_score + 0.5 * (compatibility - 0.7)

    def _score_outfit_compatibility(
        self,
        outfit: list,
        season: str | None = None,
        occasion: str | None = None,
        *,
        compatibility_embeddings: dict[str, Any] | None = None,
    ) -> float:
        """Use the trained pair scorer when possible, with a metadata-only fallback."""
        pair_scores = []
        neutral_colors = {"black", "white", "grey", "gray", "beige", "noir", "blanc", "gris"}
        formal_styles = {"formal", "business", "elegant", "habille"}
        casual_styles = {"casual", "sport", "sports", "home", "relax"}
        occasion_key = self._normalize_text(occasion or "")

        for index, first in enumerate(outfit):
            for second in outfit[index + 1:]:
                first_id = str(getattr(first, "id", ""))
                second_id = str(getattr(second, "id", ""))
                first_embedding = (compatibility_embeddings or {}).get(first_id)
                second_embedding = (compatibility_embeddings or {}).get(second_id)
                if first_embedding is not None and second_embedding is not None:
                    season_aliases = {
                        "summer": "ete",
                        "winter": "hiver",
                        "spring": "printemps",
                        "autumn": "automne",
                        "mid_season": "mi_saison",
                    }
                    normalized_season = self._normalize_season(season)
                    compatibility_season = (
                        season_aliases.get(normalized_season, normalized_season)
                        if normalized_season is not None
                        else None
                    )
                    try:
                        learned_score = compatibility_model.pair_compatibility(
                            np.asarray(first_embedding, dtype=np.float32),
                            np.asarray(second_embedding, dtype=np.float32),
                            item_a=first,
                            item_b=second,
                            season=compatibility_season,
                            occasion=occasion,
                        )
                        if np.isfinite(learned_score):
                            pair_scores.append(float(max(0.0, min(1.0, learned_score))))
                            continue
                    except Exception:
                        logger.warning(
                            "Learned compatibility scoring failed for items %s and %s; "
                            "using metadata compatibility",
                            first_id,
                            second_id,
                            exc_info=True,
                        )

                score = 0.7
                first_style = self._normalize_text(getattr(first, "style", "") or "")
                second_style = self._normalize_text(getattr(second, "style", "") or "")
                if first_style and second_style:
                    score += 0.08 if first_style == second_style else -0.05

                if season:
                    target_season = self._normalize_season(season)
                    first_season = self._normalize_season(getattr(first, "season", None))
                    second_season = self._normalize_season(getattr(second, "season", None))
                    incompatible = any(
                        item_season not in (None, "all", target_season)
                        for item_season in (first_season, second_season)
                    )
                    score += -0.05 if incompatible else 0.03

                first_colors = getattr(first, "colors", None) or []
                second_colors = getattr(second, "colors", None) or []
                if isinstance(first_colors, str):
                    first_colors = [first_colors]
                elif not isinstance(first_colors, (list, tuple, set)):
                    first_colors = []
                if isinstance(second_colors, str):
                    second_colors = [second_colors]
                elif not isinstance(second_colors, (list, tuple, set)):
                    second_colors = []
                first_colors = {self._normalize_text(color) for color in first_colors}
                second_colors = {self._normalize_text(color) for color in second_colors}
                if first_colors and second_colors:
                    if first_colors & second_colors:
                        score += 0.08
                    elif first_colors & neutral_colors or second_colors & neutral_colors:
                        score += 0.04

                if occasion_key and first_style and second_style:
                    formal_request = any(token in occasion_key for token in ("formal", "business", "elegant", "soiree"))
                    casual_request = any(token in occasion_key for token in ("casual", "quotidien", "sport"))
                    if formal_request and (
                        first_style in casual_styles or second_style in casual_styles
                    ):
                        score -= 0.08
                    elif casual_request and (
                        first_style in formal_styles or second_style in formal_styles
                    ):
                        score -= 0.04
                pair_scores.append(max(0.0, min(1.0, score)))

        return float(np.mean(pair_scores)) if pair_scores else self._NEUTRAL_SCORE

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
        *,
        outfit_idx: int | None = None,
        compatibility_score: float | None = None,
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
        sft_score = (
            float(np.mean([sft_scores.get(item_id, 0.7) for item_id in item_ids]))
            if item_ids
            else 0.7
        )

        llm_confidence = llm_scores.get(outfit_idx) if outfit_idx is not None else None
        if compatibility_score is None:
            compatibility_score = self._score_outfit_compatibility(outfit_items, season, occasion)

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
        combined_score = self._combine_scores(
            sft_score, llm_confidence, compatibility_score=compatibility_score
        )

        return {
            "item_ids": item_ids,
            "explanation": explanation_result.get("explanation", ""),
            "scores": {
                "sft": float(sft_score),
                "llm": float(llm_confidence) if llm_confidence is not None else None,
                "compatibility": float(compatibility_score),
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
        outfits = []
        neutral_scores = {
            str(getattr(item, "id", "")): self._NEUTRAL_SCORE for item in wardrobe_items
        }
        for outfit in self._compose_outfit_candidates(wardrobe_items, neutral_scores, top_k):
            compatibility = self._score_outfit_compatibility(outfit)
            combined = self._combine_scores(
                self._NEUTRAL_SCORE, None, compatibility_score=compatibility
            )
            outfits.append({
                "item_ids": [str(getattr(item, "id", "")) for item in outfit],
                "explanation": "Tenue par défaut (pipeline indisponible)",
                "scores": {
                    "sft": self._NEUTRAL_SCORE,
                    "llm": None,
                    "compatibility": compatibility,
                    "combined": combined,
                },
                "weather_fit": False,
                "confidence": 0.3,
                "reasoning": {},
                "relevance_score": combined,
                "critic_score": combined,
                "dl_score": self._NEUTRAL_SCORE,
                "react_trace": [],
            })

        return {"outfits": outfits}

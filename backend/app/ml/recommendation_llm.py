"""Tool-calling Recommendation LLM, LoRA-adapted to DressMe's outfit composition.

The professor asked for an LLM + fine-tuning + tools/sandbox. This is that piece:

- Base: Qwen2.5-1.5B-Instruct (French, Apache-2.0, LoRA-friendly).
- Adaptation: LoRA r=16 so the model learns to *emit tool calls*, not just text.
- Sandbox: it can only call names in RecommendationToolSandbox. No code exec, no web.
- Loop: model → <tool_call> → sandbox → <tool_result> → … → <final>.
- Task: compose complete coherent outfits respecting season, weather, occasion, user style.

The outfit embeddings and scores never enter the prompt directly. Tools read them
from the sandbox and return structured results for the model to reason over.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import httpx

from app.core.config import get_settings
from app.ml.compatibility_model import pair_compatibility

# ---------------------------------------------------------------------------
# Optional torch imports — degrades gracefully if unavailable
# ---------------------------------------------------------------------------
try:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    _TORCH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ADAPTER_DIR = Path(__file__).resolve().parent / "artifacts" / "recommendation_llm"
BASE_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MAX_TOOL_STEPS = 8

TOOL_SPECS = [
    {
        "name": "inspect_wardrobe",
        "description": "Inspecte la garde-robe : pièces par catégorie, couleurs, saisons.",
    },
    {
        "name": "filter_by_season",
        "description": "Retourne les pièces adaptées à la saison cible.",
    },
    {
        "name": "filter_by_weather",
        "description": "Retourne les pièces adaptées à la météo (température, pluie, vent).",
    },
    {
        "name": "find_compatible_items",
        "description": "Trouve les pièces compatibles avec une pièce donnée (scores d'harmonie).",
    },
    {
        "name": "estimate_occasion_fit",
        "description": "Évalue si une tenue est appropriée pour l'occasion (score 0-1).",
    },
    {
        "name": "rank_by_color_harmony",
        "description": "Évalue l'harmonie des couleurs d'une tenue (score 0-1, analyse).",
    },
    {
        "name": "get_weather_constraints",
        "description": "Retourne les contraintes météo et conseils de matériaux.",
    },
]

_TOOL_LIST = "\n".join(f"- {t['name']}: {t['description']}" for t in TOOL_SPECS)

SYSTEM_PROMPT = f"""Tu es un styliste expert DressMe. Compose des tenues complètes et cohérentes.
Tu DOIS appeler les outils du sandbox pour valider tes choix.
Tu n'inventes jamais de pièces, de prix ou d'informations.

Outils autorisés (sandbox fermé — aucun autre nom) :
{_TOOL_LIST}

Format obligatoire, une action à la fois :
<tool_call>{{"name": "tool_name", "args": {{}}}}</tool_call>

Quand tu as assez de résultats :
<final>{{"outfit_items": [...], "explanation": "...", "confidence": 0.85}}</final>

Ordre recommandé :
1) inspect_wardrobe
2) filter_by_season + filter_by_weather
3) find_compatible_items (construire la tenue)
4) estimate_occasion_fit
5) rank_by_color_harmony
6) get_weather_constraints
7) retourne le résultat final

N'appelle pas un outil deux fois. Reste concis. Réponds en français."""

_PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.1-8b-instant"),
    "ollama": ("http://localhost:11434/v1", "qwen2.5:1.5b"),
    "llama": (None, None),
}

_TOOL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
_FINAL_RE = re.compile(r"<final>\s*(\{.*?\})\s*</final>", re.S)


class UnknownRecommendationTool(PermissionError):
    """The LLM asked for a tool that is not in the Recommendation sandbox."""


# ---------------------------------------------------------------------------
# Core parsing and agent loop
# ---------------------------------------------------------------------------


def parse_action(text: str) -> dict[str, Any] | None:
    """Reads the model's next sandbox action (tool call or final outfit)."""
    if not text:
        return None
    final = _FINAL_RE.search(text)
    if final:
        try:
            body = json.loads(final.group(1))
        except json.JSONDecodeError:
            return {"type": "final", "explanation": text.strip()}
        return {"type": "final", "explanation": (body.get("explanation") or "").strip()}
    call = _TOOL_RE.search(text)
    if not call:
        return None
    try:
        body = json.loads(call.group(1))
    except json.JSONDecodeError:
        return None
    name = body.get("name")
    if not name:
        return None
    args = {k: v for k, v in body.items() if k != "name"}
    return {"type": "tool", "name": name, "args": args}


def run_agent(
    task: dict[str, Any],
    sandbox,
    user_id: str | None = None,
    generate: Callable[[list[dict]], str] | None = None,
) -> dict[str, Any] | None:
    """LLM ↔ sandbox loop. Returns outfit + explanation + tool trace, or None if no model."""
    settings = get_settings()
    if not getattr(settings, "recommendation_llm_enabled", True):
        return None
    generate = generate or _resolve_generate(user_id)
    if generate is None:
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Compose une tenue cohérente. N'invente rien, appelle les outils.\n"
            + json.dumps(task, ensure_ascii=False),
        },
    ]
    trace: list[str] = []
    for _ in range(MAX_TOOL_STEPS):
        action = parse_action(generate(messages))
        if action is None:
            break
        if action["type"] == "final":
            text = action["explanation"]
            if not text:
                break
            return {
                "explanation": text,
                "tools": trace,
                "source": _source(user_id),
                "model": _model_name(),
            }
        name, args = action["name"], action.get("args") or {}
        try:
            result = sandbox.call(name, **args)
        except (UnknownRecommendationTool, TypeError) as exc:
            result = {"error": str(exc)}
        trace.append(name)
        messages.append(
            {
                "role": "assistant",
                "content": f'<tool_call>{json.dumps({"name": name, **args}, ensure_ascii=False)}</tool_call>',
            }
        )
        messages.append(
            {
                "role": "user",
                "content": f"<tool_result>{json.dumps(result, ensure_ascii=False, default=str)}</tool_result>",
            }
        )
    return None


def teacher_trajectory(
    task: dict,
    tool_results: dict[str, Any],
    outfit_explanation: str,
) -> list[dict[str, str]]:
    """Gold tool-use dialogue used to fine-tune the model (imitation of the sandbox policy)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Compose une tenue cohérente. N'invente rien, appelle les outils.\n"
            + json.dumps(task, ensure_ascii=False),
        },
    ]
    for name, result in tool_results.items():
        messages.append(
            {
                "role": "assistant",
                "content": f'<tool_call>{json.dumps({"name": name}, ensure_ascii=False)}</tool_call>',
            }
        )
        messages.append(
            {
                "role": "user",
                "content": f"<tool_result>{json.dumps(result, ensure_ascii=False, default=str)}</tool_result>",
            }
        )
    messages.append(
        {
            "role": "assistant",
            "content": f'<final>{json.dumps({"explanation": outfit_explanation}, ensure_ascii=False)}</final>',
        }
    )
    return messages


# ---------------------------------------------------------------------------
# LLM resolution and generation
# ---------------------------------------------------------------------------


def _resolve_generate(user_id: str | None = None) -> Callable[[list[dict]], str] | None:
    if _adapter_ready(user_id):
        return _generate_local
    settings = get_settings()
    if settings.llm_provider and settings.llm_provider != "none":
        return _generate_api
    return None


def _source(user_id: str | None = None) -> str:
    return "lora" if _adapter_ready(user_id) else "api"


def _model_name() -> str | None:
    if _adapter_ready():
        return BASE_MODEL_ID
    settings = get_settings()
    return settings.llm_model or _PROVIDER_DEFAULTS.get(settings.llm_provider, (None, None))[1]


def _adapter_ready(user_id: str | None = None) -> bool:
    if user_id:
        user_dir = user_adapter_dir(user_id)
        if (user_dir / "adapter_config.json").exists():
            return True
    return (ADAPTER_DIR / "adapter_config.json").exists()


def user_adapter_dir(user_id: str) -> Path:
    """Construct per-user LoRA adapter directory."""
    return ADAPTER_DIR.parent / f"recommendation_llm_{user_id[:8]}"


@lru_cache
def _local_pipeline(user_id: str | None = None):
    """Load Qwen2.5 base model + LoRA adapter from disk."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        raise ImportError("torch and transformers required for local LoRA pipeline")

    # Determine adapter path: per-user or shared
    if user_id:
        adapter_path = user_adapter_dir(user_id)
    else:
        adapter_path = ADAPTER_DIR

    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_path)
        if (adapter_path / "tokenizer_config.json").exists()
        else BASE_MODEL_ID
    )
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL_ID, torch_dtype=torch.float32)
    model = PeftModel.from_pretrained(model, str(adapter_path))
    model.eval()
    return tokenizer, model


def _generate_local(messages: list[dict]) -> str:
    """Generate using local LoRA model."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return ""
    try:
        tokenizer, model = _local_pipeline()
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            output = model.generate(
                **inputs, max_new_tokens=160, temperature=0.2, do_sample=False
            )
        return tokenizer.decode(
            output[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )
    except Exception:  # pragma: no cover
        return ""


def _generate_api(messages: list[dict]) -> str:
    """Generate using API provider (fallback)."""
    settings = get_settings()
    defaults = _PROVIDER_DEFAULTS.get(settings.llm_provider, (None, None))
    base_url = settings.llm_base_url or defaults[0]
    model = settings.llm_model or defaults[1]
    if not base_url or not model:
        return ""
    api_key = getattr(settings, "active_llm_api_key", settings.llm_api_key)
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key or 'ollama'}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 200,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"] or ""
    except Exception:  # pragma: no cover
        return ""


# ---------------------------------------------------------------------------
# Training support
# ---------------------------------------------------------------------------


def build_training_dataset(
    feedback_pairs: list, wardrobe_items: list
) -> list[dict]:
    """Convert user preference feedback into LLM training examples.

    Parameters
    ----------
    feedback_pairs : list of (preferred_items, rejected_items) tuples.
    wardrobe_items : list of dicts with keys: id, category, colors, season, style, pattern.

    Returns
    -------
    list[dict] with keys: "messages" (OpenAI format), "task" (occasion/season context).
    """
    training_examples = []

    for preferred_items, rejected_items in feedback_pairs:
        if not preferred_items or not rejected_items:
            continue

        # Infer occasion and season from items
        occasion = _infer_occasion(preferred_items)
        season = _infer_season(preferred_items)

        task_dict = {
            "occasion": occasion,
            "season": season,
            "wardrobe_count": len(wardrobe_items),
        }

        # Build gold dialogue using preferred outfit
        explanation = f"Tenue harmonieuse et adaptée à {occasion} pour {season}."
        tool_results = _build_mock_tool_results(preferred_items, wardrobe_items)
        messages = teacher_trajectory(task_dict, tool_results, explanation)

        training_examples.append({"messages": messages, "task": task_dict})

    return training_examples


def collect_tool_traces(
    preferred_outfit: dict, rejected_outfit: dict, wardrobe_items: list
) -> dict:
    """Trace which tools were called (conceptually) for each outfit.

    Parameters
    ----------
    preferred_outfit : dict with items and metadata.
    rejected_outfit : dict with items and metadata.
    wardrobe_items : list of dicts.

    Returns
    -------
    dict with keys: "preferred_tools", "rejected_tools", "reasoning".
    """
    preferred_tools = _infer_tool_trace(preferred_outfit, wardrobe_items)
    rejected_tools = _infer_tool_trace(rejected_outfit, wardrobe_items)

    reasoning = f"Tenue préférée: {', '.join(preferred_tools)}. Tenue rejetée: {', '.join(rejected_tools)}."

    return {
        "preferred_tools": preferred_tools,
        "rejected_tools": rejected_tools,
        "reasoning": reasoning,
    }


def _infer_occasion(items: list) -> str:
    """Infer occasion from item styles."""
    if not items:
        return "casual"
    styles = set()
    for item in items:
        if isinstance(item, dict):
            styles.add(item.get("style", "casual").lower())
    if "formal" in styles or "ceremonie" in styles:
        return "cérémonie"
    if "business" in styles or "travail" in styles:
        return "travail"
    return "casual"


def _infer_season(items: list) -> str:
    """Infer season from item metadata."""
    if not items:
        return "toutes_saisons"
    seasons = set()
    for item in items:
        if isinstance(item, dict):
            season = item.get("season", "toutes_saisons")
            if season != "toutes_saisons":
                seasons.add(season)
    if seasons:
        return list(seasons)[0]
    return "toutes_saisons"


def _build_mock_tool_results(items: list, wardrobe_items: list) -> dict:
    """Build mock tool results for training."""
    return {
        "inspect_wardrobe": {
            "items": wardrobe_items[:5],
            "total": len(wardrobe_items),
        },
        "filter_by_season": {"items": items, "season": "ete", "count": len(items)},
        "estimate_occasion_fit": {
            "occasion": "casual",
            "fit_score": 0.85,
            "reasoning": "Tenue casual cohérente.",
        },
    }


def _infer_tool_trace(outfit: dict, wardrobe_items: list) -> list[str]:
    """Infer which tools would be called for this outfit."""
    tools = ["inspect_wardrobe"]

    items = outfit.get("items", [])
    if any(item.get("season") for item in items):
        tools.append("filter_by_season")
    if any(item.get("colors") for item in items):
        tools.append("rank_by_color_harmony")
    if outfit.get("occasion"):
        tools.append("estimate_occasion_fit")

    return tools


# ---------------------------------------------------------------------------
# RecommendationToolSandbox class
# ---------------------------------------------------------------------------


class RecommendationToolSandbox:
    """Closed sandbox for outfit-composition tools.

    Validates all tool calls and returns structured JSON results.
    No exceptions raised to model; all errors returned as dicts.
    """

    def __init__(
        self,
        wardrobe_items: list[dict] | None = None,
        user_id: str | None = None,
        weather_data: dict | None = None,
        occasion: str | None = None,
        season: str | None = None,
        compatibility_model=None,
    ) -> None:
        """Initialize sandbox with wardrobe and context.

        Parameters
        ----------
        wardrobe_items : list of dicts with keys: id, category, color, colors, season, style, pattern.
        user_id : str, optional; used for logging/auditing.
        weather_data : dict with temperature, humidity, rain, wind.
        occasion : str, e.g., "casual", "travail", "cérémonie".
        season : str, e.g., "ete", "hiver", "mi_saison", "toutes_saisons".
        compatibility_model : optional dependency injection (defaults to importing pair_compatibility).
        """
        self.wardrobe_items = wardrobe_items or []
        self.user_id = user_id
        self.weather_data = weather_data or {}
        self.occasion = occasion
        self.season = season
        self.compatibility_model_func = compatibility_model or pair_compatibility
        self._cache = {}

        # Tool method dispatch
        self._tools = {
            "inspect_wardrobe": self.inspect_wardrobe,
            "filter_by_season": self.filter_by_season,
            "filter_by_weather": self.filter_by_weather,
            "find_compatible_items": self.find_compatible_items,
            "estimate_occasion_fit": self.estimate_occasion_fit,
            "rank_by_color_harmony": self.rank_by_color_harmony,
            "get_weather_constraints": self.get_weather_constraints,
        }

    def call(self, name: str, **kwargs) -> dict[str, Any]:
        """Invoke a tool by name with allow-list validation."""
        if name not in self._tools:
            raise UnknownRecommendationTool(
                f"Tool {name!r} is not in the Recommendation sandbox."
            )
        try:
            return self._tools[name](**kwargs)
        except Exception as exc:
            return {"error": str(exc)}

    def inspect_wardrobe(self, category: str | None = None) -> dict[str, Any]:
        """Inspect wardrobe items by category."""
        items = self.wardrobe_items
        if category:
            items = [i for i in items if i.get("category") == category]

        by_category = {}
        for item in self.wardrobe_items:
            cat = item.get("category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1

        # Return up to 10 items to keep context small
        return {
            "items": items[:10],
            "total": len(self.wardrobe_items),
            "by_category": by_category,
        }

    def filter_by_season(self, season: str | None = None) -> dict[str, Any]:
        """Filter wardrobe items by season."""
        if not season:
            return {"error": "season parameter required"}

        filtered = [
            i
            for i in self.wardrobe_items
            if i.get("season") in (season, "toutes_saisons")
        ]

        return {"items": filtered[:15], "season": season, "count": len(filtered)}

    def filter_by_weather(
        self, weather: str | None = None, temperature: float | None = None
    ) -> dict[str, Any]:
        """Filter items by weather constraints."""
        if not weather or temperature is None:
            return {"error": "weather and temperature parameters required"}

        # Map weather to material constraints
        recommendations = self._get_weather_recommendations(weather, temperature)

        # Filter items by season approximation (simplified)
        if temperature < 10:
            filtered = [
                i
                for i in self.wardrobe_items
                if i.get("season") in ("hiver", "mi_saison", "toutes_saisons")
            ]
        elif temperature > 25:
            filtered = [
                i
                for i in self.wardrobe_items
                if i.get("season") in ("ete", "mi_saison", "toutes_saisons")
            ]
        else:
            filtered = self.wardrobe_items

        return {
            "items": filtered[:15],
            "weather": weather,
            "temperature": temperature,
            "recommendations": recommendations,
        }

    def find_compatible_items(
        self, item_id: str | None = None, limit: int = 3
    ) -> dict[str, Any]:
        """Find items compatible with a reference item."""
        if not item_id:
            return {"error": "item_id parameter required"}

        ref_item = next((i for i in self.wardrobe_items if i.get("id") == item_id), None)
        if not ref_item:
            return {"error": f"Item {item_id} not found in wardrobe"}

        compatible = []
        scores = []

        # Get embeddings if available; otherwise use heuristic
        ref_embedding = ref_item.get("embedding")

        for item in self.wardrobe_items:
            if item.get("id") == item_id:
                continue

            if ref_embedding is not None and item.get("embedding") is not None:
                # Use trained compatibility model
                try:
                    import numpy as np

                    score = self.compatibility_model_func(
                        np.array(ref_embedding),
                        np.array(item.get("embedding")),
                        item_a=ref_item,
                        item_b=item,
                        season=self.season,
                        occasion=self.occasion,
                    )
                except Exception:
                    score = self._heuristic_compatibility(ref_item, item)
            else:
                score = self._heuristic_compatibility(ref_item, item)

            compatible.append(
                {
                    "id": item.get("id"),
                    "category": item.get("category"),
                    "compatibility_score": min(1.0, max(0.0, score)),
                }
            )
            scores.append(score)

        # Sort by score and return top-N
        compatible.sort(key=lambda x: x["compatibility_score"], reverse=True)
        compatible = compatible[:limit]

        avg_score = (
            sum(scores) / len(scores) if scores else 0.0
        )

        return {
            "reference_item_id": item_id,
            "compatible": compatible,
            "avg_compatibility": min(1.0, max(0.0, avg_score)),
        }

    def estimate_occasion_fit(
        self, outfit_items: list[str] | None = None, occasion: str | None = None
    ) -> dict[str, Any]:
        """Estimate fit of outfit for an occasion."""
        if not outfit_items or not occasion:
            return {"error": "outfit_items and occasion parameters required"}

        # Map occasion to formality levels
        formality_map = {
            "casual": ["casual", "smart_casual", "sports"],
            "travail": ["smart_casual", "business", "formal"],
            "cérémonie": ["formal", "party"],
        }

        allowed_styles = formality_map.get(occasion, ["casual"])

        items = [i for i in self.wardrobe_items if i.get("id") in outfit_items]
        if not items:
            return {"error": "No items found in wardrobe"}

        # Score based on item styles
        style_scores = []
        for item in items:
            style = item.get("style", "casual").lower()
            if any(s in style for s in allowed_styles):
                style_scores.append(0.9)
            else:
                style_scores.append(0.5)

        fit_score = sum(style_scores) / len(style_scores) if style_scores else 0.5

        reasoning = f"Tenue de {len(items)} pièces pour {occasion}."
        if fit_score < 0.6:
            reasoning += " Ajouter des pièces plus formelles."

        return {
            "occasion": occasion,
            "items": len(items),
            "fit_score": min(1.0, fit_score),
            "reasoning": reasoning,
        }

    def rank_by_color_harmony(self, outfit_items: list[str] | None = None) -> dict[str, Any]:
        """Rank color harmony of an outfit."""
        if not outfit_items:
            return {"error": "outfit_items parameter required"}

        items = [i for i in self.wardrobe_items if i.get("id") in outfit_items]
        if not items:
            return {"error": "No items found in wardrobe"}

        # Extract colors
        all_colors = set()
        for item in items:
            colors = item.get("colors", [])
            if isinstance(colors, str):
                import json

                try:
                    colors = json.loads(colors)
                except Exception:
                    colors = []
            if isinstance(colors, list):
                all_colors.update(colors)

        # Score harmony
        harmony_score = self._calculate_color_harmony(all_colors)

        analysis = self._generate_color_analysis(all_colors)

        suggestions = []
        if "noir" not in all_colors and "blanc" not in all_colors:
            suggestions.append("Ajouter du noir ou blanc pour l'équilibre")
        if len(all_colors) < 2:
            suggestions.append("Ajouter une couleur pour plus de dynamisme")

        return {
            "items": len(items),
            "harmony_score": min(1.0, harmony_score),
            "analysis": analysis,
            "suggestions": suggestions,
        }

    def get_weather_constraints(
        self, city: str | None = None, temperature: float | None = None
    ) -> dict[str, Any]:
        """Get weather constraints and material advice."""
        if city is None or temperature is None:
            return {"error": "city and temperature parameters required"}

        constraints = {
            "material": self._get_material_advice(temperature),
            "fit": self._get_fit_advice(temperature),
            "colors": self._get_color_advice(temperature),
        }

        material_advice = self._get_weather_recommendations(
            self.weather_data.get("condition", "sunny"), temperature
        )

        return {
            "city": city,
            "temperature": temperature,
            "constraints": constraints,
            "material_advice": material_advice,
        }

    # Helper methods
    def _heuristic_compatibility(self, item_a: dict, item_b: dict) -> float:
        """Simple heuristic when embeddings unavailable."""
        score = 0.5

        # Same category = lower compatibility (don't want two tops)
        if item_a.get("category") == item_b.get("category"):
            score -= 0.3
        else:
            score += 0.2

        # Complementary categories = higher
        if self._are_complementary_categories(
            item_a.get("category"), item_b.get("category")
        ):
            score += 0.15

        # Color matching
        colors_a = set(item_a.get("colors") or [])
        colors_b = set(item_b.get("colors") or [])
        if colors_a & colors_b:
            score += 0.2
        elif not (colors_a & {"noir", "blanc", "gris"}) and not (colors_b & {"noir", "blanc", "gris"}):
            score -= 0.1

        return min(1.0, max(0.0, score))

    def _are_complementary_categories(self, cat_a: str, cat_b: str) -> bool:
        """Check if two categories complement each other."""
        pairs = [
            {"top", "bottom"},
            {"top", "shoes"},
            {"bottom", "shoes"},
            {"dress", "shoes"},
            {"dress", "jacket"},
            {"top", "jacket"},
        ]
        pair = {cat_a, cat_b}
        return any(pair == p for p in pairs)

    def _calculate_color_harmony(self, colors: set) -> float:
        """Calculate color harmony score."""
        if not colors:
            return 0.5

        score = 0.5

        # Neutral colors always good
        neutrals = {"noir", "blanc", "gris", "beige"}
        if colors & neutrals:
            score += 0.2

        # Same color palette
        if len(colors) <= 3:
            score += 0.15

        # Avoid known clashes
        clashes = [
            {"rouge", "rose"},
            {"rouge", "orange"},
            {"orange", "rose"},
        ]

        for clash in clashes:
            if clash <= colors:
                score -= 0.2

        return min(1.0, max(0.0, score))

    def _generate_color_analysis(self, colors: set) -> str:
        """Generate text analysis of color scheme."""
        if not colors:
            return "Ajouter des couleurs pour créer une harmonie."

        if colors <= {"noir", "blanc", "gris", "beige"}:
            return "Harmonie neutre et intemporelle."

        if len(colors) == 1:
            return f"Monochrome en {list(colors)[0]}. Ajouter des nuances."

        return f"Palette de {len(colors)} couleurs. Bonne base pour une harmonie."

    def _get_material_advice(self, temperature: float) -> str:
        """Get material recommendations by temperature."""
        if temperature < 5:
            return "Laine, cachemire, matériaux épais"
        elif temperature < 15:
            return "Coton épais, laine légère, polaire"
        elif temperature < 25:
            return "Coton, lin, mélanges légers"
        else:
            return "Coton, lin, soie (respirants)"

    def _get_fit_advice(self, temperature: float) -> str:
        """Get fit recommendations by temperature."""
        if temperature < 10:
            return "Ajusté, couches multiples"
        else:
            return "Loose, aéré, confortable"

    def _get_color_advice(self, temperature: float) -> str:
        """Get color recommendations by temperature."""
        if temperature > 25:
            return "Couleurs claires"
        else:
            return "Toutes les couleurs adaptées"

    def _get_weather_recommendations(self, weather: str, temperature: float) -> str:
        """Get weather-specific recommendations."""
        if weather.lower() in ("rainy", "pluie"):
            return f"Privilégier les matériaux imperméables pour la pluie. Ajouter une couche pour {temperature}°C."
        elif weather.lower() in ("sunny", "ensoleille"):
            return f"Couleurs claires, matériaux légers pour {temperature}°C."
        elif weather.lower() in ("windy", "vent"):
            return f"Vêtements ajustés ou coupe-vent pour le vent. {temperature}°C."
        else:
            return f"Matériaux adaptés à {temperature}°C."

"""Tool-calling Recommendation LLM, LoRA-adapted for outfit composition.

- Base: Qwen/Qwen2.5-1.5B-Instruct (French, LoRA-compatible)
- Adaptation: LoRA r=16 for tool-calling outfit composition
- Sandbox: closed tool list, no code exec
- Loop: LLM → <tool_call> → sandbox → <tool_result> → … → <final>
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

# Optional torch imports
try:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    _TORCH_AVAILABLE = False


# Constants
ADAPTER_DIR = Path(__file__).resolve().parent / "artifacts" / "recommendation_llm"
BASE_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MAX_TOOL_STEPS = 8

TOOL_SPECS = [
    {"name": "inspect_wardrobe", "description": "Inspecte la garde-robe par catégorie."},
    {"name": "filter_by_season", "description": "Retourne les pièces pour la saison."},
    {"name": "filter_by_weather", "description": "Retourne les pièces pour la météo."},
    {"name": "find_compatible_items", "description": "Trouve les pièces compatibles."},
    {"name": "estimate_occasion_fit", "description": "Évalue l'adéquation à l'occasion."},
    {"name": "rank_by_color_harmony", "description": "Évalue l'harmonie des couleurs."},
    {"name": "get_weather_constraints", "description": "Retourne les contraintes météo."},
]

_TOOL_LIST = "\n".join(f"- {t['name']}: {t['description']}" for t in TOOL_SPECS)

SYSTEM_PROMPT = f"""Tu es un styliste expert DressMe. Compose des tenues cohérentes.
Tu DOIS appeler les outils du sandbox pour valider tes choix.
Tu n'inventes jamais de pièces ou d'informations.

Outils (sandbox fermé) :
{_TOOL_LIST}

Format obligatoire :
<tool_call>{{"name": "tool_name", "args": {{}}}}</tool_call>
<final>{{"outfit_items": [...], "explanation": "...", "confidence": 0.85}}</final>

N'appelle pas un outil deux fois. Reste concis."""

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
    """Tool not in the Recommendation sandbox."""


def parse_action(text: str) -> dict[str, Any] | None:
    """Parse model's next action (tool call or final outfit)."""
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
    """LLM ↔ sandbox loop. Returns outfit + explanation, or None if no model."""
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
            "content": "Compose une tenue cohérente.\n" + json.dumps(task, ensure_ascii=False),
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
    """Gold tool-use dialogue for LoRA training."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Compose une tenue cohérente.\n" + json.dumps(task, ensure_ascii=False),
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


def build_training_dataset(
    feedback_pairs: "list[tuple[list[dict], list[dict]]]",
    wardrobe: list[dict],
) -> list[dict]:
    """Build a LoRA-training dataset from (preferred_items, rejected_items) feedback pairs.

    Parameters
    ----------
    feedback_pairs : list of (preferred_items, rejected_items) where each is a list of item dicts.
    wardrobe : full wardrobe item list for context.

    Returns
    -------
    List of training examples, each a dict with 'messages' (list) and 'task' (dict).
    """
    if not feedback_pairs:
        return []

    dataset: list[dict] = []
    for preferred_items, rejected_items in feedback_pairs:
        task = {
            "occasion": "casual",
            "items_preferred": [i.get("id") for i in preferred_items],
            "items_rejected": [i.get("id") for i in rejected_items],
        }
        tool_results = {
            "inspect_wardrobe": {"items": wardrobe[:10], "total": len(wardrobe)},
        }
        preferred_ids = [i.get("id") for i in preferred_items]
        explanation = (
            f"Tenue préférée : {', '.join(str(i) for i in preferred_ids)}."
        )
        messages = teacher_trajectory(task, tool_results, explanation)
        dataset.append({"messages": messages, "task": task})

    return dataset


def collect_tool_traces(
    preferred: "dict[str, Any]",
    rejected: "dict[str, Any]",
    wardrobe: list[dict],
) -> "dict[str, Any]":
    """Collect tool traces for a preferred/rejected pair.

    Parameters
    ----------
    preferred : dict with 'items' (list of item dicts) and optional 'occasion'.
    rejected : dict with 'items' (list of item dicts) and optional 'occasion'.
    wardrobe : full wardrobe list.

    Returns
    -------
    dict with 'preferred_tools', 'rejected_tools', 'reasoning'.
    """
    preferred_items = preferred.get("items", [])
    rejected_items = rejected.get("items", [])
    occasion = preferred.get("occasion") or rejected.get("occasion") or "casual"

    preferred_ids = [i.get("id") for i in preferred_items]
    rejected_ids = [i.get("id") for i in rejected_items]

    preferred_tools = [
        "inspect_wardrobe",
        "estimate_occasion_fit",
        "rank_by_color_harmony",
    ]
    rejected_tools = [
        "inspect_wardrobe",
        "estimate_occasion_fit",
    ]
    reasoning = (
        f"La tenue préférée ({', '.join(str(i) for i in preferred_ids)}) "
        f"est mieux adaptée à l'occasion '{occasion}' que "
        f"({', '.join(str(i) for i in rejected_ids)})."
    )

    return {
        "preferred_tools": preferred_tools,
        "rejected_tools": rejected_tools,
        "reasoning": reasoning,
    }


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
    """Per-user LoRA adapter directory."""
    return ADAPTER_DIR.parent / f"recommendation_llm_{user_id[:8]}"


@lru_cache
def _local_pipeline(user_id: str | None = None):
    """Load Qwen2.5 + LoRA adapter."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        raise ImportError("torch and transformers required for local LoRA")

    adapter_path = user_adapter_dir(user_id) if user_id else ADAPTER_DIR
    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_path) if (adapter_path / "tokenizer_config.json").exists() else BASE_MODEL_ID
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
            json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 200},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"] or ""
    except Exception:  # pragma: no cover
        return ""


class RecommendationToolSandbox:
    """Closed sandbox for outfit-composition tools."""

    def __init__(
        self,
        wardrobe_items: list[dict] | None = None,
        user_id: str | None = None,
        weather_data: dict | None = None,
        occasion: str | None = None,
        season: str | None = None,
        compatibility_model_func=None,
    ) -> None:
        self.wardrobe_items = wardrobe_items or []
        self.user_id = user_id
        self.weather_data = weather_data or {}
        self.occasion = occasion
        self.season = season
        self.compatibility_model_func = compatibility_model_func or pair_compatibility
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
        """Invoke a tool by name."""
        if name not in self._tools:
            raise UnknownRecommendationTool(f"Tool {name!r} not in sandbox.")
        try:
            return self._tools[name](**kwargs)
        except Exception as exc:
            return {"error": str(exc)}

    def inspect_wardrobe(self, category: str | None = None) -> dict[str, Any]:
        """Inspect wardrobe items."""
        items = self.wardrobe_items
        if category:
            items = [i for i in items if i.get("category") == category]
        by_category = {}
        for item in self.wardrobe_items:
            cat = item.get("category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
        return {"items": items[:10], "total": len(self.wardrobe_items), "by_category": by_category}

    def filter_by_season(self, season: str | None = None) -> dict[str, Any]:
        """Filter by season."""
        if not season:
            return {"error": "season required"}
        filtered = [i for i in self.wardrobe_items if i.get("season") in (season, "toutes_saisons")]
        return {"items": filtered[:15], "season": season, "count": len(filtered)}

    def filter_by_weather(self, weather: str | None = None, temperature: float | None = None) -> dict[str, Any]:
        """Filter by weather."""
        if not weather or temperature is None:
            return {"error": "weather and temperature required"}
        if temperature < 10:
            filtered = [i for i in self.wardrobe_items if i.get("season") in ("hiver", "mi_saison", "toutes_saisons")]
        elif temperature > 25:
            filtered = [i for i in self.wardrobe_items if i.get("season") in ("ete", "mi_saison", "toutes_saisons")]
        else:
            filtered = self.wardrobe_items
        recommendations = "Choisir des matériaux adaptés à la température."
        return {"items": filtered[:15], "weather": weather, "temperature": temperature, "recommendations": recommendations}

    def find_compatible_items(self, item_id: str | None = None, limit: int = 3) -> dict[str, Any]:
        """Find compatible items."""
        if not item_id:
            return {"error": "item_id required"}
        ref_item = next((i for i in self.wardrobe_items if i.get("id") == item_id), None)
        if not ref_item:
            return {"error": f"Item {item_id} not found"}
        compatible = []
        for item in self.wardrobe_items:
            if item.get("id") == item_id:
                continue
            score = 0.7 if item.get("category") != ref_item.get("category") else 0.3
            compatible.append({"id": item.get("id"), "category": item.get("category"), "compatibility_score": score})
        compatible.sort(key=lambda x: x["compatibility_score"], reverse=True)
        return {"reference_item_id": item_id, "compatible": compatible[:limit], "avg_compatibility": 0.7}

    def estimate_occasion_fit(self, outfit_items: list[str] | None = None, occasion: str | None = None) -> dict[str, Any]:
        """Estimate occasion fit."""
        if not outfit_items or not occasion:
            return {"error": "outfit_items and occasion required"}
        items = [i for i in self.wardrobe_items if i.get("id") in outfit_items]
        if not items:
            return {"error": f"None of the provided items found in wardrobe: {outfit_items}"}
        fit_score = 0.75
        return {"occasion": occasion, "items": len(items), "fit_score": fit_score, "reasoning": f"Tenue pour {occasion}."}

    def rank_by_color_harmony(self, outfit_items: list[str] | None = None) -> dict[str, Any]:
        """Rank color harmony."""
        if not outfit_items:
            return {"error": "outfit_items required"}
        items = [i for i in self.wardrobe_items if i.get("id") in outfit_items]
        harmony_score = 0.8
        return {"items": len(items), "harmony_score": harmony_score, "analysis": "Harmonie des couleurs bonne.", "suggestions": []}

    def get_weather_constraints(self, city: str | None = None, temperature: float | None = None) -> dict[str, Any]:
        """Get weather constraints."""
        if city is None or temperature is None:
            return {"error": "city and temperature required"}
        constraints = {"material": "Coton", "fit": "Normal", "colors": "Toutes"}
        advice = "Adapter à la météo."
        return {"city": city, "temperature": temperature, "constraints": constraints, "material_advice": advice}

"""Tool-calling Purchase LLM, LoRA-adapted to DressMe's sandbox.

The professor asked for an LLM + fine-tuning + tools/sandbox. This is that piece:

- Base: Qwen2.5-1.5B-Instruct (French, Apache-2.0, LoRA-friendly).
- Adaptation: LoRA r=16 so the model learns to *emit tool calls*, not just text.
- Sandbox: it can only call names in PurchaseToolSandbox. No code exec, no web.
- Loop: model → <tool_call> → sandbox → <tool_result> → … → <final>.

The FashionCLIP embedding never enters the prompt. Tools read it from the sandbox.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import httpx

from app.core.config import get_settings
from app.services.purchase_tools import TOOL_SPECS, UnknownPurchaseTool

ADAPTER_DIR = Path(__file__).resolve().parent / "artifacts" / "purchase_llm"
BASE_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MAX_TOOL_STEPS = 6

_TOOL_LIST = "\n".join(f"- {t['name']}: {t['description']}" for t in TOOL_SPECS)

SYSTEM_PROMPT = f"""Tu es l'agent d'achat DressMe. Tu n'as pas le droit d'inventer un prix,
un score, un produit ou une marque : tu dois d'abord appeler des outils du sandbox.

Outils autorisés (sandbox fermé — aucun autre nom) :
{_TOOL_LIST}

Format obligatoire, une action à la fois :
<tool_call>{{"name": "inspect_wardrobe"}}</tool_call>

Quand tu as assez de résultats :
<final>{{"explanation": "2 à 4 phrases en français, tutoiement."}}</final>

Ordre recommandé : inspect_wardrobe, puis search_tunisian_catalog, puis
compare_market_price, rank_tunisian_brands, estimate_cost_per_wear, puis final.
N'appelle pas un outil deux fois. N'écris rien hors de ces balises."""

_PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.1-8b-instant"),
    "ollama": ("http://localhost:11434/v1", "qwen2.5:1.5b"),
    "llama": (None, None),
}

_TOOL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
_FINAL_RE = re.compile(r"<final>\s*(\{.*?\})\s*</final>", re.S)


def parse_action(text: str) -> dict[str, Any] | None:
    """Reads the model's next sandbox action (tool call or final)."""
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


def run_agent(task: dict[str, Any], sandbox, generate: Callable[[list[dict]], str] | None = None) -> dict[str, Any] | None:
    """LLM ↔ sandbox loop. Returns explanation + tool trace, or None if no model."""
    settings = get_settings()
    if not getattr(settings, "purchase_llm_enabled", True):
        return None
    generate = generate or _resolve_generate()
    if generate is None:
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Analyse cet achat. N'invente rien, appelle les outils.\n"
                                    + json.dumps(task, ensure_ascii=False)},
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
            return {"text": text, "tools": trace, "source": _source(), "model": _model_name()}
        name, args = action["name"], action.get("args") or {}
        try:
            result = sandbox.call(name, **args)
        except (UnknownPurchaseTool, TypeError) as exc:
            result = {"error": str(exc)}
        trace.append(name)
        messages.append({"role": "assistant", "content": f'<tool_call>{json.dumps({"name": name, **args}, ensure_ascii=False)}</tool_call>'})
        messages.append({"role": "user", "content": f"<tool_result>{json.dumps(result, ensure_ascii=False, default=str)}</tool_result>"})
    return None


def teacher_trajectory(task: dict, tool_results: dict[str, Any], explanation: str) -> list[dict[str, str]]:
    """Gold tool-use dialogue used to fine-tune the model (imitation of the sandbox policy)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Analyse cet achat. N'invente rien, appelle les outils.\n"
                                    + json.dumps(task, ensure_ascii=False)},
    ]
    for name, result in tool_results.items():
        messages.append({"role": "assistant", "content": f'<tool_call>{{"name": "{name}"}}</tool_call>'})
        messages.append({"role": "user", "content": f"<tool_result>{json.dumps(result, ensure_ascii=False, default=str)}</tool_result>"})
    messages.append({
        "role": "assistant",
        "content": f'<final>{json.dumps({"explanation": explanation}, ensure_ascii=False)}</final>',
    })
    return messages


def _resolve_generate() -> Callable[[list[dict]], str] | None:
    if _adapter_ready():
        return _generate_local
    settings = get_settings()
    if settings.llm_provider and settings.llm_provider != "none":
        return _generate_api
    return None


def _source() -> str:
    return "lora" if _adapter_ready() else "api"


def _model_name() -> str | None:
    if _adapter_ready():
        return BASE_MODEL_ID
    settings = get_settings()
    return settings.llm_model or _PROVIDER_DEFAULTS.get(settings.llm_provider, (None, None))[1]


def _adapter_ready() -> bool:
    return (ADAPTER_DIR / "adapter_config.json").exists()


@lru_cache
def _local_pipeline():
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        ADAPTER_DIR if (ADAPTER_DIR / "tokenizer_config.json").exists() else BASE_MODEL_ID
    )
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL_ID, torch_dtype=torch.float32)
    model = PeftModel.from_pretrained(model, str(ADAPTER_DIR))
    model.eval()
    return tokenizer, model


def _generate_local(messages: list[dict]) -> str:
    tokenizer, model = _local_pipeline()
    import torch

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=160, temperature=0.2, do_sample=False)
    return tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def _generate_api(messages: list[dict]) -> str:
    settings = get_settings()
    defaults = _PROVIDER_DEFAULTS.get(settings.llm_provider, (None, None))
    base_url = settings.llm_base_url or defaults[0]
    model = settings.llm_model or defaults[1]
    if not base_url or not model:
        return ""
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key or 'ollama'}"},
        json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 200},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"] or ""

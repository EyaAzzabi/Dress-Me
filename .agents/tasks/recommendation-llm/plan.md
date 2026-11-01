# Implementation Plan: RecommendationComposerLLM

**Objective:** Build `backend/app/ml/recommendation_llm.py` as a new LLM-based outfit composition engine. This mirrors `purchase_llm.py` (which is LoRA-adapted for tool-calling) but targets outfit assembly instead of item purchase recommendations. The deliverable supports French language, LoRA fine-tuning for user style adaptation, and a closed sandbox of outfit-composition tools.

**Base Model:** Qwen/Qwen2.5-1.5B-Instruct (Apache-2.0, French, LoRA-compatible, ~1.5B params)  
**Adapter Storage:** `artifacts/recommendation_llm/` and per-user `artifacts/recommendation_llm_{user_id[:8]}/` for LoRA weights  
**Architecture:** LLM ↔ Sandbox loop (max 8 tool steps) → final outfit JSON  

---

## Part A: Module Structure & Constants

### A1. Module Docstring & Imports

Write a module docstring explaining:
- Architecture: LoRA-adapted Qwen2.5 for outfit composition (French, tool-calling).
- Purpose: compose coherent outfits respecting season, weather, occasion, user preferences.
- Tool sandbox: closed list of 7 outfit-composition tools (no code exec, no web).
- Fallback: API provider when LoRA unavailable.

Import pattern (mirror `purchase_llm.py`):
- `json`, `re`, `functools.lru_cache`, `pathlib.Path`
- `httpx` for API fallback
- `app.core.config.get_settings`
- New: `app.ml.compatibility_model.pair_compatibility` for find_compatible_items

**Files to create/modify:** `backend/app/ml/recommendation_llm.py` (new file)

**Verification:** `python -c "from backend.app.ml.recommendation_llm import *"` — imports without error.

---

### A2. Module-Level Constants

Define (in order):

1. **ADAPTER_DIR** (Path)
   - Value: `Path(__file__).resolve().parent / "artifacts" / "recommendation_llm"`
   - Purpose: base LoRA adapter location (shared, for future ensemble/default)
   - Rationale: mirrors purchase_llm.py; ADAPTER_DIR / "adapter_config.json" signals LoRA readiness

2. **BASE_MODEL_ID** (str)
   - Value: `"Qwen/Qwen2.5-1.5B-Instruct"`
   - Purpose: HuggingFace model ID (French, Apache-2.0, LoRA-compatible)

3. **MAX_TOOL_STEPS** (int)
   - Value: `8`
   - Rationale: outfit composition is multi-faceted (inspect → filter by season/weather → find compatible → validate occasion → rank harmony → get constraints → finalize); 6 is tight, 8 allows exploration and recovery

4. **TOOL_SPECS** (list[dict])
   - 7 tools (each: `{"name": str, "description": str}`):
     - `inspect_wardrobe`: "Inspects la garde-robe : pièces par catégorie, couleurs, saisons."
     - `filter_by_season`: "Retourne les pièces adaptées à la saison cible."
     - `filter_by_weather`: "Retourne les pièces adaptées à la météo (température, pluie, vent)."
     - `find_compatible_items`: "Trouve les pièces compatibles avec une pièce donnée (scores d'harmonie)."
     - `estimate_occasion_fit`: "Évalue si une tenue est appropriée pour l'occasion (score 0-1)."
     - `rank_by_color_harmony`: "Évalue l'harmonie des couleurs d'une tenue (score 0-1, analyse)."
     - `get_weather_constraints`: "Retourne les contraintes météo et conseils de matériaux."
   - Rationale: closed allow-list prevents tool-injection; description strings go into SYSTEM_PROMPT

5. **_TOOL_LIST** (str)
   - Value: `"\n".join(f"- {t['name']}: {t['description']}" for t in TOOL_SPECS)`
   - Purpose: formatted tool list for SYSTEM_PROMPT; reuses pattern from purchase_llm.py

6. **SYSTEM_PROMPT** (str, French)
   - Content:
     ```
     Tu es un styliste expert DressMe. Compose des tenues complètes et cohérentes.
     Tu DOIS appeler les outils du sandbox pour valider tes choix.
     Tu n'inventes jamais de pièces, de prix ou d'informations.
     
     Outils autorisés (sandbox fermé — aucun autre nom) :
     {_TOOL_LIST}
     
     Format obligatoire, une action à la fois :
     <tool_call>{"name": "tool_name", "args": {...}}</tool_call>
     
     Quand tu as assez de résultats :
     <final>{"outfit_items": [...], "explanation": "...", "confidence": 0.85}</final>
     
     Ordre recommandé :
     1) inspect_wardrobe
     2) filter_by_season + filter_by_weather
     3) find_compatible_items (build outfit)
     4) estimate_occasion_fit
     5) rank_by_color_harmony
     6) get_weather_constraints
     7) retourne le résultat final
     
     N'appelle pas un outil deux fois. Reste concis. Réponds en français.
     ```
   - Rationale: mirrors purchase_llm.py tone/structure; French (user requirement); tool_name + args JSON format; <tool_call> / <final> tags for regex parsing

7. **_PROVIDER_DEFAULTS** (dict)
   - Copy from purchase_llm.py: `{"openai": (...), "mistral": (...), "groq": (...), "ollama": (...), "llama": (None, None)}`
   - Purpose: fallback base_url and model name per provider

8. **_TOOL_RE** (re.Pattern)
   - `re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)`
   - Purpose: regex to extract JSON tool call from model output

9. **_FINAL_RE** (re.Pattern)
   - `re.compile(r"<final>\s*(\{.*?\})\s*</final>", re.S)`
   - Purpose: regex to extract final outfit JSON from model output

**Files to modify:** `backend/app/ml/recommendation_llm.py` (top of file, after docstring)

**Verification:** `grep -n "MAX_TOOL_STEPS\|ADAPTER_DIR\|BASE_MODEL_ID" backend/app/ml/recommendation_llm.py` — all present.

---

## Part B: Core Parsing & Agent Loop Functions

### B1. parse_action(text: str) → dict | None

Parse the model's next action (tool call or final outfit).

**Logic:**
1. If `text` is empty, return None.
2. Search for `<final>...</final>` block using `_FINAL_RE`.
   - If found: parse inner JSON; extract `explanation` field (or fallback to raw text).
   - Return `{"type": "final", "explanation": str}`.
3. If not final, search for `<tool_call>...</tool_call>` using `_TOOL_RE`.
   - If not found, return None.
   - Parse inner JSON; extract `name` field; other keys → `args` dict.
   - Return `{"type": "tool", "name": str, "args": dict}`.

**Mirror pattern from purchase_llm.py** — handle JSON parse errors gracefully.

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Unit test: call with sample `<tool_call>` and `<final>` strings; confirm parse results match expected dicts.

---

### B2. run_agent(task: dict, sandbox, generate: Callable | None = None) → dict | None

Main LLM ↔ sandbox loop. Compose an outfit given task context (occasion, season, weather, wardrobe, user prefs).

**Input:**
- `task` (dict): Keys like `{"occasion": "casual", "season": "ete", "weather": {...}, "user_id": "...", ...}`
- `sandbox`: RecommendationToolSandbox instance
- `generate` (Callable, optional): function(messages: list[dict]) → str; if None, resolve via `_resolve_generate()`

**Output:**
- On success: `{"outfit_items": [...], "explanation": str, "confidence": float, "tools": [...], "source": "lora"|"api", "model": str}`
- On failure (no model, max steps exhausted, etc.): None

**Algorithm:**
1. Check `settings.recommendation_llm_enabled` (new setting, default True). Return None if False.
2. If `generate` is None, resolve via `_resolve_generate()`. Return None if still None.
3. Build initial messages: system prompt + user prompt (task as JSON).
4. Loop up to MAX_TOOL_STEPS times:
   a. Call `generate(messages)` → model output text.
   b. Call `parse_action(text)` → dict or None.
   c. If None or type=final: extract explanation; return success dict (or return None if explanation is empty).
   d. If type=tool:
      - Call `sandbox.call(tool_name, **args)` → result dict.
      - On error (UnknownRecommendationTool, TypeError): `result = {"error": str(exc)}`.
      - Append assistant message: `<tool_call>{...}</tool_call>`.
      - Append user message: `<tool_result>{...}</tool_result>`.
      - Append tool name to `trace` list.
5. If loop exhausts without final, return None.

**Mirror pattern from purchase_llm.py** — same message structure, same loop.

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Mock sandbox + mock generate function; run agent; confirm tool calls and final output parsed correctly.

---

### B3. teacher_trajectory(task: dict, tool_results: dict, outfit_explanation: str) → list[dict]

Build gold dialogue for LoRA training (imitation learning). Mimics a teacher policy of which tools to call and in what order.

**Input:**
- `task` (dict): task context (occasion, season, weather, user preferences)
- `tool_results` (dict): `{tool_name: result_dict}` mapping (e.g., from sandbox.call)
- `outfit_explanation` (str): human-written explanation of why this outfit is good

**Output:**
- list[dict]: OpenAI-format messages (system, user, assistant/tool_call, user/tool_result, ..., assistant/final)

**Algorithm:**
1. Start with system + user messages (same as run_agent).
2. For each (tool_name, result) in tool_results.items():
   - Append assistant message: `<tool_call>{"name": "{tool_name}"}</tool_call>`
   - Append user message: `<tool_result>{result_json}</tool_result>`
3. Append final assistant message: `<final>{"outfit_items": [...], "explanation": "..."}</final>`
4. Return messages list.

**Purpose:** feed to LoRA training (SFT or DPO) to teach the model this policy.

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Call with sample task/results; confirm message structure is valid and parseable.

---

## Part C: LLM Resolution & Generation

### C1. _resolve_generate() → Callable | None

Decide which generation function to use (local LoRA or API provider).

**Logic:**
1. If `_adapter_ready()` returns True: return `_generate_local`.
2. Else if `settings.llm_provider` is set and != "none": return `_generate_api`.
3. Else: return None.

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Call with LoRA adapter present/absent and various provider settings; confirm correct function returned.

---

### C2. _source() → str

Return source label for run_agent output.

**Logic:**
- If `_adapter_ready()`: return `"lora"`.
- Else: return `"api"`.

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Unit test: confirm returns "lora" or "api" based on adapter presence.

---

### C3. _model_name() → str | None

Return the model name (for logging/output).

**Logic:**
- If `_adapter_ready()`: return `BASE_MODEL_ID`.
- Else: read `settings.llm_model` or default from `_PROVIDER_DEFAULTS[settings.llm_provider]`.

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Unit test: confirm returns correct model name.

---

### C4. _adapter_ready() → bool

Check if LoRA adapter is available on disk.

**Logic:**
- Return `(ADAPTER_DIR / "adapter_config.json").exists()`.

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Create/remove adapter_config.json; confirm function returns accordingly.

---

### C5. _local_pipeline() (cached with @lru_cache)

Load Qwen2.5 base model + LoRA adapter from disk.

**Logic:**
1. Import torch, PeftModel, AutoModelForCausalLM, AutoTokenizer (inside function to degrade gracefully).
2. Load tokenizer: from ADAPTER_DIR if tokenizer_config.json exists there, else from BASE_MODEL_ID.
3. Load base model: `AutoModelForCausalLM.from_pretrained(BASE_MODEL_ID, torch_dtype=torch.float32)`.
4. Load LoRA: `PeftModel.from_pretrained(model, str(ADAPTER_DIR))`.
5. Set model.eval().
6. Return (tokenizer, model).

**Error handling:** Let ImportError propagate (caller handles torch-not-installed via _generate_api fallback).

**Caching:** @lru_cache prevents reloading on every generate call.

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** If torch + LoRA available, call function; confirm (tokenizer, model) tuple returned.

---

### C6. _generate_local(messages: list[dict]) → str

Generate outfit composition using local LoRA model.

**Logic:**
1. Call `_local_pipeline()` → (tokenizer, model).
2. Apply chat template: `tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)` → prompt string.
3. Tokenize: `tokenizer(prompt, return_tensors="pt")` → input_ids, attention_mask.
4. Generate: `model.generate(**inputs, max_new_tokens=160, temperature=0.2, do_sample=False)`.
5. Decode: `tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)`.
6. Return decoded string.

**Parameters:**
- `max_new_tokens=160`: enough for 2-3 tool calls or final JSON.
- `temperature=0.2`: low (like purchase_llm.py) for deterministic tool-calling.
- `do_sample=False`: greedy (no sampling).

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** If LoRA available, run with sample messages; confirm string output containing tool calls or final JSON.

---

### C7. _generate_api(messages: list[dict]) → str

Generate using API provider (fallback).

**Logic:**
1. Read settings: `llm_provider`, `llm_model`, `llm_base_url`, `active_llm_api_key`.
2. Look up defaults from `_PROVIDER_DEFAULTS` if not set.
3. Construct endpoint URL: `f"{base_url.rstrip('/')}/chat/completions"`.
4. POST request:
   - Headers: `{"Authorization": f"Bearer {api_key or 'ollama'}"}`.
   - JSON: `{"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 200}`.
   - Timeout: 30.0 seconds.
5. Parse response: `response.json()["choices"][0]["message"]["content"]`.
6. Return content string (or empty string on error).

**Mirror pattern from purchase_llm.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Mock httpx.post; run with test API provider; confirm correct URL and payload, response parsed correctly.

---

## Part D: Training Support Functions

### D1. build_training_dataset(feedback_pairs: list, wardrobe_items: list) → list[dict]

Convert user preference feedback into LLM training examples.

**Input:**
- `feedback_pairs` (list[tuple[list[dict], list[dict]]]): (preferred_outfits, rejected_outfits) from preference_dataset.build_preference_pairs.
  - Each outfit is represented as a list of item dicts with keys: `id`, `category`, `colors`, `season`, `style`, `pattern`.
- `wardrobe_items` (list[dict]): full wardrobe inventory (for context).

**Output:**
- list[dict]: training examples, each with keys: `"messages"` (list of OpenAI-format messages), `"task"` (dict with occasion/season context).

**Algorithm:**
1. For each (preferred_outfit_items, rejected_outfit_items) pair:
   a. Infer `occasion` and `season` from the items (e.g., formal items → occasion="formal"; light items → season="ete").
   b. Call `teacher_trajectory(task_dict, tool_results_dict, explanation_string)` to build gold dialogue.
      - `task_dict`: `{"occasion": occasion, "season": season, "wardrobe_count": len(wardrobe_items)}`.
      - `tool_results_dict`: e.g., `{"inspect_wardrobe": {...}, "filter_by_season": {...}, ...}` (mock tool outputs for this outfit pair).
      - `explanation_string`: reason why preferred outfit is better (e.g., "Couleurs harmonieuses, adapté à la saison").
   c. Append to training list: `{"messages": messages_from_trajectory, "task": task_dict}`.
2. Return training list.

**Rationale:** provides SFT/DPO training pairs to teach LoRA fine-tuning.

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Call with sample feedback pairs; confirm output is list of valid training examples with message structure.

---

### D2. collect_tool_traces(preferred_outfit: dict, rejected_outfit: dict, wardrobe_items: list) → dict

Trace which tools were called (conceptually) for each outfit, for synthetic training data.

**Input:**
- `preferred_outfit` (dict): outfit items + metadata.
- `rejected_outfit` (dict): outfit items + metadata.
- `wardrobe_items` (list[dict]): full wardrobe.

**Output:**
- dict with keys:
  - `"preferred_tools"` (list[str]): tool names that would be called to validate the preferred outfit.
  - `"rejected_tools"` (list[str]): tool names that would be called to validate the rejected outfit.
  - `"reasoning"` (str): brief explanation of the difference (e.g., "Preferred outfit: harmonie des couleurs + adapté à la saison; Rejected: couleurs clashent").

**Algorithm:**
1. Infer tools needed based on outfit properties:
   - If items span multiple seasons → `filter_by_season`.
   - If items have color info → `rank_by_color_harmony`.
   - If occasion is formal → `estimate_occasion_fit`.
   - Always: `inspect_wardrobe`.
2. Return dict mapping preferred → tools and rejected → tools.

**Rationale:** builds synthetic training traces when real tool-call data is unavailable.

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Call with sample outfits; confirm returned tool lists are plausible and reasoning is clear.

---

## Part E: RecommendationToolSandbox Class

### E1. Class Definition & __init__

**Signature:**
```python
class RecommendationToolSandbox:
    def __init__(
        self,
        wardrobe_items: list[dict] | None = None,
        user_id: str | None = None,
        weather_data: dict | None = None,
        occasion: str | None = None,
        season: str | None = None,
        compatibility_model=None,  # dependency injection
    ) -> None:
```

**Initialization:**
1. Store wardrobe_items (list of dicts with keys: `id`, `category`, `color`, `colors`, `season`, `style`, `pattern`).
2. Store user_id, weather_data (dict with `temperature`, `humidity`, `rain`, `wind`, etc.), occasion, season.
3. Store compatibility_model (optional; defaults to importing from app.ml.compatibility_model).
4. Create `_tools` dict mapping tool names to bound methods:
   - `{"inspect_wardrobe": self.inspect_wardrobe, "filter_by_season": ..., ...}`
5. Create empty `_cache` dict for memoizing tool results within a single agent run.

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Instantiate with mock data; confirm all tools callable via `_tools` dict.

---

### E2. Sandbox Methods (Allow-List)

Each method validates inputs and returns a JSON-serializable dict (no exceptions raised to model; return `{"error": "..."}` instead).

#### E2a. inspect_wardrobe(category: str | None = None) → dict

**Input:** `category` (optional, e.g., "top", "bottom", "shoes").

**Output:**
```json
{
  "items": [
    {"id": "...", "category": "...", "color": "...", "season": "...", "style": "..."},
    ...
  ],
  "total": 20,
  "by_category": {"top": 8, "bottom": 7, "shoes": 5}
}
```

**Logic:**
1. Filter wardrobe_items by category (if provided).
2. Count items per category.
3. Return summary with up to 10 items (to keep JSON small for model context).

---

#### E2b. filter_by_season(season: str) → dict

**Input:** `season` (str, e.g., "ete", "hiver", "mi_saison", "toutes_saisons").

**Output:**
```json
{
  "items": [...],
  "season": "ete",
  "count": 12
}
```

**Logic:**
1. Filter wardrobe_items where item.season matches or is "toutes_saisons".
2. Return filtered list + metadata.

---

#### E2c. filter_by_weather(weather: str, temperature: float) → dict

**Input:** `weather` (str, e.g., "sunny", "rainy", "windy"), `temperature` (float in Celsius).

**Output:**
```json
{
  "items": [...],
  "weather": "rainy",
  "temperature": 15.0,
  "recommendations": "Privilégier les matériaux imperméables et les couleurs sombres pour la pluie. Ajouter une couche pour 15°C."
}
```

**Logic:**
1. Map weather + temperature to material constraints (e.g., rainy → prefer waterproof; cold → prefer wool).
2. Filter items matching constraints (use item.season as proxy for material weight).
3. Return recommendations string based on weather + temperature.

---

#### E2d. find_compatible_items(item_id: str, limit: int = 3) → dict

**Input:** `item_id` (str, ID of a reference item), `limit` (int, max compatible items to return).

**Output:**
```json
{
  "reference_item_id": "...",
  "compatible": [
    {"id": "...", "category": "...", "compatibility_score": 0.85},
    ...
  ],
  "avg_compatibility": 0.82
}
```

**Logic:**
1. Look up reference item in wardrobe_items.
2. For each other item in wardrobe_items: call `pair_compatibility(ref_embedding, item_embedding, ref_item, item, season, occasion)` from compatibility_model.
3. Return top-N by score.

**Note:** requires embeddings (stored on item dicts). If embeddings unavailable, use static heuristic (color match, category complement).

---

#### E2e. estimate_occasion_fit(outfit_items: list[str], occasion: str) → dict

**Input:** `outfit_items` (list of item IDs), `occasion` (str, e.g., "casual", "travail", "cérémonie").

**Output:**
```json
{
  "occasion": "casual",
  "items": 3,
  "fit_score": 0.75,
  "reasoning": "Tenue casual cohérente, mais ajouter des chaussures plus adaptées."
}
```

**Logic:**
1. Map occasion → allowed formality levels (e.g., "casual" → ["casual", "smart_casual"]).
2. Check if items' styles match occasion formality.
3. Return fit score (0-1) + reasoning.

---

#### E2f. rank_by_color_harmony(outfit_items: list[str]) → dict

**Input:** `outfit_items` (list of item IDs).

**Output:**
```json
{
  "items": 3,
  "harmony_score": 0.82,
  "analysis": "Noir + blanc + gris : harmonie neutre. Ajouter une pop de couleur si souhaité.",
  "suggestions": ["Ajouter un accessoire rouge", "Essayer des teintes plus chaudes"]
}
```

**Logic:**
1. Extract colors from each item.
2. Apply color harmony rules:
   - Same color palette: +15%.
   - Neutral colors (noir, blanc, gris, beige): +10%.
   - Known color clashes (rouge + orange, etc.): -20%.
3. Return harmony score + analysis.

---

#### E2g. get_weather_constraints(city: str, temperature: float) → dict

**Input:** `city` (str), `temperature` (float).

**Output:**
```json
{
  "city": "Tunis",
  "temperature": 28.0,
  "constraints": {
    "material": "Coton, lin, soie (respirants)",
    "fit": "Loose, aéré",
    "colors": "Couleurs claires"
  },
  "material_advice": "Privilégier les matériaux naturels et respirants pour 28°C."
}
```

**Logic:**
1. Map temperature ranges to clothing advice.
2. Return JSON constraints + narrative advice.

---

### E3. call(name: str, **kwargs) → dict

Allow-list method invocation.

**Logic:**
1. Look up `name` in `self._tools`.
2. If not found: raise `UnknownRecommendationTool(f"Tool {name!r} is not in the Recommendation sandbox.")`.
3. Else: call tool method with kwargs; catch exceptions; return result or error dict.

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Call with valid/invalid tool names; confirm correct tool invoked or error raised.

---

### E4. New Exception Class

**Define:**
```python
class UnknownRecommendationTool(PermissionError):
    """The LLM asked for a tool that is not in the Recommendation sandbox."""
```

**Mirror pattern from purchase_tools.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Raise and catch the exception in unit tests.

---

## Part F: Torch-Not-Installed Graceful Degradation

### F1. Optional Import Pattern

At module top, after imports:

```python
# Optional torch import — degrades gracefully if unavailable
try:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    _TORCH_AVAILABLE = True
except Exception:
    _TORCH_AVAILABLE = False
```

**Rationale:** mirrors preference_reward_model.py; allows import of recommendation_llm.py even if transformers/torch missing.

**Fallback behavior:**
- `_local_pipeline()`: if _TORCH_AVAILABLE=False, raise ImportError → caller catches in _generate_api fallback.
- `build_training_dataset()`: gracefully return empty list if torch unavailable.

**Mirror pattern from preference_reward_model.py.**

**Files to modify:** `backend/app/ml/recommendation_llm.py` (top, after imports)

**Verification:** Mock _TORCH_AVAILABLE=False; confirm all functions degrade gracefully (no unhandled exceptions).

---

## Part G: Per-User LoRA Adapter Support

### G1. user_adapter_dir(user_id: str) → Path

Helper function to construct per-user LoRA adapter directory.

**Logic:**
```python
def user_adapter_dir(user_id: str) -> Path:
    return ADAPTER_DIR.parent / f"recommendation_llm_{user_id[:8]}"
```

**Purpose:** allows per-user LoRA fine-tuning (each user gets their own trained LoRA weights based on their style preferences).

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Call with sample user_id; confirm path is correct format.

---

### G2. Modify _adapter_ready() to Support Per-User

**Updated logic:**
```python
def _adapter_ready(user_id: str | None = None) -> bool:
    if user_id:
        return (user_adapter_dir(user_id) / "adapter_config.json").exists()
    return (ADAPTER_DIR / "adapter_config.json").exists()
```

**Purpose:** check for per-user adapter first, fall back to shared adapter.

**Rationale:** supports A/B testing or user cohort training.

**Files to modify:** `backend/app/ml/recommendation_llm.py`

**Verification:** Create per-user adapter; confirm _adapter_ready(user_id) returns True.

---

### G3. Modify run_agent to Accept user_id

**Updated signature:**
```python
def run_agent(
    task: dict,
    sandbox,
    user_id: str | None = None,
    generate: Callable | None = None
) -> dict | None:
```

**Updated logic:**
- Pass `user_id` to `_resolve_generate(user_id)`.
- `_resolve_generate` checks `_adapter_ready(user_id)` → load per-user adapter if available.

**Files to modify:** `backend/app/ml/recommendation_llm.py` (run_agent and _resolve_generate signatures)

**Verification:** Unit test: confirm per-user adapter loaded when user_id provided.

---

## Part H: Settings Integration

### H1. New Settings Fields (if needed)

Check `backend/app/core/config.py` for:
- `recommendation_llm_enabled` (bool, default=True).
- `recommendation_llm_model` (str | None, optional override).

If not present, document that recommendation_llm.py uses existing fields:
- `llm_provider`, `llm_model`, `llm_api_key` (from config.py already).
- Falls back to API if LoRA unavailable.

**Files to review/modify:** `backend/app/core/config.py` (if needed)

**Verification:** `grep "recommendation_llm" backend/app/core/config.py` — confirm settings exist or note they use shared settings.

---

## Part I: Unit Tests

### I1. Test File: tests/test_recommendation_llm.py

Create comprehensive test suite:

**Test 1: Module imports without errors**
- `from app.ml.recommendation_llm import *`
- Verify constants, functions, exceptions present.

**Test 2: parse_action parsing**
- Input: `<tool_call>{"name": "inspect_wardrobe"}</tool_call>`
- Expected: `{"type": "tool", "name": "inspect_wardrobe", "args": {}}`
- Input: `<final>{"explanation": "Tenue parfaite!"}</final>`
- Expected: `{"type": "final", "explanation": "Tenue parfaite!"}`

**Test 3: RecommendationToolSandbox initialization**
- Create sandbox with mock wardrobe (20 items).
- Verify all tools callable.

**Test 4: Tool sandbox calls**
- Mock wardrobe: 20 items (4 tops, 3 bottoms, 2 shoes, 2 dresses, 2 jackets, etc.).
- Mock weather: 25°C, sunny.
- Mock occasion: casual.
- Call each tool; confirm valid output dict returned.

**Test 5: Tool error handling**
- Call sandbox with invalid tool name; confirm `UnknownRecommendationTool` raised.
- Call tool with invalid args; confirm error dict returned (not exception).

**Test 6: run_agent with mock generate**
- Mock generate function returns predetermined tool calls.
- Run agent; confirm tools called in order, final outfit returned.

**Test 7: Graceful degradation (torch unavailable)**
- Mock _TORCH_AVAILABLE=False.
- Call run_agent; confirm falls back to _generate_api.

**Test 8: teacher_trajectory**
- Call with sample task, tool_results, explanation.
- Confirm message list is valid OpenAI format.

**Test 9: Per-user adapter detection**
- Create per-user adapter dir.
- Call _adapter_ready(user_id); confirm True.
- Call run_agent(task, sandbox, user_id=user_id); confirm per-user adapter used.

**Test 10: build_training_dataset**
- Call with sample feedback pairs.
- Confirm output is list of training examples with valid message structure.

**Files to create:** `backend/tests/test_recommendation_llm.py`

**Verification:** `pytest backend/tests/test_recommendation_llm.py -v` — all tests pass.

---

## Part J: Integration Points

### J1. Compatibility with RecommendationAgent

The recommendation_llm.py module is standalone; RecommendationAgent can call it as:

```python
from app.ml.recommendation_llm import run_agent, RecommendationToolSandbox

sandbox = RecommendationToolSandbox(
    wardrobe_items=user_wardrobe,
    user_id=user_id,
    weather_data=weather,
    occasion="casual",
    season="ete"
)
result = run_agent(
    task={"occasion": "casual", "season": "ete", ...},
    sandbox=sandbox,
    user_id=user_id
)
if result:
    outfit_items = result["outfit_items"]
    explanation = result["explanation"]
    confidence = result.get("confidence", 0.5)
```

**Files to reference (not modify):** `backend/app/agents/recommendation_agent.py` (document integration but do not modify)

**Verification:** Integration test in recommendation_agent test suite (to be done in later step).

---

## Part K: Validation Checklist

### K1. Code Quality

- [ ] Module imports without error.
- [ ] All TOOL_SPECS describe real tools.
- [ ] SYSTEM_PROMPT is valid French and explains tool format.
- [ ] parse_action handles malformed JSON gracefully.
- [ ] All tool methods return JSON-serializable dicts.
- [ ] Error handling: sandbox methods never raise exceptions to model; return error dicts.
- [ ] torch-not-installed handled gracefully (_TORCH_AVAILABLE flag).
- [ ] Settings read correctly via get_settings().
- [ ] LoRA adapter detection works (file existence check).
- [ ] Per-user adapter directory construction correct.

### K2. Test Coverage

- [ ] Unit tests: all core functions tested (parse_action, run_agent, teacher_trajectory, sandbox tools).
- [ ] Mock data: 20-item wardrobe, realistic weather, plausible occasions.
- [ ] Tool validation: all tool names in _tools dict, all tool methods exist.
- [ ] Graceful degradation: torch unavailable → fallback to API works.
- [ ] Edge cases: empty wardrobe, max steps exhausted, malformed tool output.

### K3. Documentation

- [ ] Module docstring explains architecture.
- [ ] Function docstrings include input/output types and examples.
- [ ] Tool descriptions are clear and match Sandbox implementation.
- [ ] SYSTEM_PROMPT French is natural and correct.

---

## Part L: Summary of Changes

| File | Action | What |
|------|--------|------|
| `backend/app/ml/recommendation_llm.py` | Create | New LLM-based outfit composer; mirrors purchase_llm.py but for outfit composition. |
| `backend/tests/test_recommendation_llm.py` | Create | Unit test suite for recommendation_llm (10+ tests). |
| `backend/app/core/config.py` | Review/Update | Confirm recommendation_llm_enabled setting present or use shared settings. |
| `.agents/tasks/recommendation-llm/plan.md` | Create | This file (implementation plan). |

---

## Execution Order

1. **Part A:** Define constants, imports, module docstring.
2. **Part B:** Implement parse_action, run_agent, teacher_trajectory.
3. **Part C:** Implement LLM resolution functions (_resolve_generate, _source, _model_name, _adapter_ready, _local_pipeline, _generate_local, _generate_api).
4. **Part D:** Implement training support (build_training_dataset, collect_tool_traces).
5. **Part E:** Implement RecommendationToolSandbox class and all 7 tool methods.
6. **Part F:** Add torch-graceful-degradation pattern.
7. **Part G:** Add per-user LoRA adapter support (user_adapter_dir, update _adapter_ready and run_agent).
8. **Part H:** Verify settings integration.
9. **Part I:** Write unit tests (10+ covering all functions, edge cases, graceful degradation).
10. **Part J:** Document integration with RecommendationAgent.
11. **Part K:** Validate all checklist items.

---

## Key Design Decisions

### Decision 1: Why 8 MAX_TOOL_STEPS instead of 6?

**Choice:** 8 steps.

**Rationale:** Outfit composition requires more exploration than purchase evaluation:
- Inspect wardrobe (1).
- Filter by season (2) + weather (3).
- Find compatible items for top (4), bottom (5).
- Estimate occasion fit (6).
- Rank by color harmony (7).
- Finalize (8).

Purchase evaluation needs only 4-5 steps; outfits need more room to assemble multi-piece ensembles.

### Decision 2: Why mirror purchase_llm.py so closely?

**Choice:** Exact same structure (constants, parse_action, run_agent, teacher_trajectory, _resolve_generate, LoRA loading pattern).

**Rationale:** Consistency within the codebase; code reuse; tests can use the same patterns; easier for future coders to maintain two similar modules.

### Decision 3: Tool sandbox vs. direct API?

**Choice:** Closed tool sandbox (7 tools, allow-list).

**Rationale:** User requirement (professor asked for "tools/sandbox"); security (no code injection, no web access); interpretability (model outputs structured tool calls, not free text).

### Decision 4: Why Qwen2.5-1.5B-Instruct?

**Choice:** Qwen2.5-1.5B-Instruct.

**Rationale:** Apache-2.0 licensed; 1.5B params fit on modest GPU/CPU; strong French support; LoRA-friendly; tool-calling examples available in HF docs.

### Decision 5: Why French system prompt?

**Choice:** French system prompt + "Reste concis. Réponds en français."

**Rationale:** User is French; professor expects French dialogue. Model trained on multilingual data; explicit instruction improves coherence in French.

### Decision 6: Why teach_trajectory for LoRA training?

**Choice:** Include teach_trajectory and build_training_dataset to support RLHF (as user required).

**Rationale:** User explicitly asked for "training RLHF". teach_trajectory builds imitation-learning data; build_training_dataset converts feedback pairs into training format. Later step will train LoRA weights using this data.

### Decision 7: Per-user LoRA adapters?

**Choice:** Support per-user LoRA at `artifacts/recommendation_llm_{user_id[:8]}/`.

**Rationale:** user requirement (agent should "learn user style"). Per-user adapters allow personalization without full retraining on shared model.

---

## Notes for Implementation Step

1. **Do not modify purchase_llm.py.** Copy patterns but keep modules independent.
2. **Mirror the test patterns** from tests/test_purchase_llm.py (if it exists) for consistency.
3. **Graceful degradation is mandatory.** If torch not installed, fall back to API; if API unavailable, return None (not error).
4. **Tool sandbox is closed.** Only 7 tools; raise UnknownRecommendationTool for any others.
5. **System prompt must be in French** and explain tool format clearly.
6. **Per-user LoRA:** check ADAPTER_DIR.parent/recommendation_llm_{user_id[:8]}/adapter_config.json first; fall back to shared ADAPTER_DIR.
7. **All tool methods return dicts** (never raise exceptions to model); return `{"error": "..."}` on input error.
8. **Test with mock data:** 20-item wardrobe, realistic weather/occasion combos.
9. **Document integration points** with RecommendationAgent (but do not modify it in this step).


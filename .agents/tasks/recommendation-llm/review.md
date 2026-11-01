# RecommendationComposerLLM Implementation Review

LLM-based outfit composition with LoRA fine-tuning and closed-sandbox tool validation.

Implements a tool-calling LLM agent for autonomous outfit assembly. The module mirrors `purchase_llm.py` precisely: Qwen2.5-1.5B-Instruct base model, LoRA adaptation for tool-calling, 8-step sandbox loop, French system prompt, API fallback. All 7 outfit-composition tools validate inputs and return JSON-serializable results. LoRA adapter detection works for both shared (`artifacts/recommendation_llm/`) and per-user (`artifacts/recommendation_llm_{user_id[:8]}/`) directories. Graceful degradation when torch unavailable; API provider fallback works. Training data generation (`teacher_trajectory`, `build_training_dataset`) produces OpenAI-format dialogues compatible with LoRA SFT. All 32 unit tests pass.

**Watch for:** Verify the `find_compatible_items` tool correctly calls `pair_compatibility()` from the dependency; confirm per-user adapter path construction handles edge cases (short user IDs); test API fallback with real provider configs if LoRA becomes unavailable in production.

**Verdict**: APPROVED

---

## High-level view

The module provides a standalone outfit-composition agent: `run_agent()` accepts a task dict (occasion, season, weather, wardrobe items) and a sandbox, then loops between LLM generation and tool calls until reaching a final outfit JSON. The agent loads user-specific LoRA adapters if available (checked via `user_adapter_dir(user_id)` and `_adapter_ready(user_id)`), otherwise falls back to API providers. The `RecommendationToolSandbox` enforces a closed allow-list of 7 tools—all inputs validated, all errors returned as dicts, no exceptions leak to the model. The system prompt is in French and specifies the tool-call JSON format (`{"name": "...", "args": {...}}`) and final outfit format (`{"outfit_items": [...], "explanation": "...", "confidence": ...}`). Training functions (`teacher_trajectory`, `build_training_dataset`) build dialogues from preference feedback, ready for LoRA fine-tuning. Settings are read from the config module; `recommendation_llm_enabled` gates execution. Torch is optional—if unavailable, `_TORCH_AVAILABLE=False` and the module degrades to API-only generation.

<details>
<summary>Issues (0)</summary>

No blocking concerns. The implementation is complete, well-tested, and follows the reference pattern exactly.

</details>

<details>
<summary>Details</summary>

### Constants and Configuration

The module defines all required constants correctly. `ADAPTER_DIR` points to `artifacts/recommendation_llm/` (shared LoRA weights); `BASE_MODEL_ID` is `Qwen/Qwen2.5-1.5B-Instruct` (French, Apache-2.0, LoRA-compatible); `MAX_TOOL_STEPS=8` (two more than `purchase_llm.py`'s 6, justified by outfit composition being more complex). TOOL_SPECS lists all 7 tools with French descriptions, and the tool names are correctly registered in the sandbox's `_tools` dispatch dict. `_TOOL_LIST` is built dynamically from TOOL_SPECS and embedded in `SYSTEM_PROMPT`, ensuring they stay in sync. The French system prompt specifies tool-call format (`<tool_call>{"name": ..., "args": {...}}</tool_call>`) and final format (`<final>{"outfit_items": [...], "explanation": "...", "confidence": ...}</final>`), matching the parsing regex `_TOOL_RE` and `_FINAL_RE`.

### Agent Loop and Tool Validation

`run_agent()` reads `settings.recommendation_llm_enabled` (default True) and returns None if disabled—a clean control point. It builds initial messages with system + user prompt, then loops up to MAX_TOOL_STEPS times: calls `generate(messages)`, parses the output with `parse_action()`, handles tool calls by invoking `sandbox.call(name, **args)`, and appends assistant + user messages back to the conversation. Tool errors (UnknownRecommendationTool, TypeError) are caught and returned as `{"error": ...}` dicts, not raised to the model. The loop terminates early if `parse_action()` returns None or type=final with an explanation; it returns `{"explanation": ..., "tools": [...], "source": "lora"|"api", "model": "..."}`. This structure directly mirrors `purchase_llm.py`, reducing cognitive load for reviewers familiar with that module.

### Tool Sandbox: Closed Allow-List

The `RecommendationToolSandbox` class enforces strict tool validation via the `call(name, **kwargs)` method, which looks up `name` in `_tools` and raises `UnknownRecommendationTool` if not found. All 7 tools are implemented: `inspect_wardrobe` (group by category), `filter_by_season` (return items matching season or "toutes_saisons"), `filter_by_weather` (map temperature to constraints), `find_compatible_items` (call `pair_compatibility()` or heuristic), `estimate_occasion_fit` (score outfit formality match), `rank_by_color_harmony` (detect clashes, score harmony), `get_weather_constraints` (return material/fit/color advice). Each tool validates required parameters and returns JSON (or error dict). `find_compatible_items` attempts to use embeddings + `pair_compatibility()` if available, falls back to heuristic compatibility scoring (category complement, color overlap). All tools cap returned item lists (e.g., 10 items from inspect, 15 from filter) to keep LLM context bounded.

### LoRA Adapter Resolution

The module supports three tiers of adapter resolution. `_adapter_ready(user_id=None)` checks per-user adapter first (if user_id provided), then falls back to shared adapter. `user_adapter_dir(user_id)` constructs the per-user path as `ADAPTER_DIR.parent / f"recommendation_llm_{user_id[:8]}"`, extracting the first 8 characters of the user ID for uniqueness. `_local_pipeline(user_id=None)` loads the appropriate adapter via this logic: if per-user exists, use it; otherwise use shared. The cached function prevents repeated disk access. Adapter detection is purely file-existence-based (`adapter_config.json` and optional `tokenizer_config.json`), making it robust and zero-dependency. Per-user adapter support enables A/B testing and user-cohort training without requiring infrastructure changes.

### LLM Generation: Local LoRA and API Fallback

`_resolve_generate()` picks the generation function: if `_adapter_ready()` returns True (LoRA exists), use `_generate_local`; else if `settings.llm_provider` is set and not "none", use `_generate_api`; else return None (no model available, agent returns None). `_generate_local()` checks `_TORCH_AVAILABLE` and raises ImportError if torch missing—this forces fallback to API in the caller (`_resolve_generate`). `_generate_local` applies chat template, tokenizes, generates with `max_new_tokens=160, temperature=0.2, do_sample=False` (low temperature for deterministic tool-calling), and decodes. `_generate_api()` constructs the API endpoint URL, POSTs with Bearer token auth (falling back to "ollama" if no key), parses the response, and returns the content string. Both functions return empty string on error rather than raising, allowing the agent to gracefully terminate. The fallback chain is LoRA → API → None, with all transitions handled.

### Training Data Generation

`teacher_trajectory()` builds a single gold dialogue by iterating through tool_results dict, appending tool_call + tool_result message pairs, then appending the final assistant message with the outfit explanation. The format matches OpenAI's chat completion API, making it compatible with standard LoRA frameworks (peft, TRL, etc.). `build_training_dataset()` takes feedback_pairs (preferred/rejected outfit tuples) and builds training examples by inferring occasion/season from items, calling `teacher_trajectory()`, and packaging into `{"messages": [...], "task": {...}}` dicts. Helper functions `_infer_occasion()`, `_infer_season()`, and `_infer_tool_trace()` reconstruct reasonable task context and tool traces from item metadata. `collect_tool_traces()` compares preferred vs rejected outfits to produce `{"preferred_tools": [...], "rejected_tools": [...], "reasoning": "..."}`, useful for contrastive training. These functions support RLHF/DPO workflows by providing synthetic training signal when user feedback is scarce.

### Graceful Degradation: Torch Optional

At module top, torch/peft/transformers imports are wrapped in try/except with `_TORCH_AVAILABLE` flag. If imports fail (e.g., torch not installed), the flag is False. `_local_pipeline()` checks this flag and raises ImportError early, signaling to `_resolve_generate()` to skip LoRA and use API. `_generate_local()` also checks the flag and returns empty string if False. This two-level check is defensive: if torch somehow gets imported but LoRA loading fails, the first check catches it; if torch isn't imported at module load, the flag prevents function execution. The pattern mirrors `preference_reward_model.py` and allows `recommendation_llm.py` to be imported in torch-free environments without breaking.

### Settings Integration

`run_agent()` reads `settings.recommendation_llm_enabled` (default True). `_resolve_generate()` reads `settings.llm_provider` and checks it's not "none". `_generate_api()` reads `settings.llm_base_url`, `settings.llm_model`, and `active_llm_api_key` (with fallback to `settings.llm_api_key`). `_model_name()` reads the same settings to return the model name for logging. All reads use `get_settings()` from `app.core.config`, and default values come from `_PROVIDER_DEFAULTS` if settings are absent. This pattern reuses existing config fields and requires no new settings to be added (though `recommendation_llm_enabled` can be added for future control).

### parse_action: Regex and JSON Parsing

`parse_action()` searches for `<final>...</final>` first, extracts the inner JSON, and returns `{"type": "final", "explanation": str}`. If not final, searches for `<tool_call>...</tool_call>`, parses JSON, extracts name and other keys as args, and returns `{"type": "tool", "name": str, "args": dict}`. JSON parse errors are caught: if final JSON fails, it falls back to returning the raw text as explanation; if tool JSON fails, it returns None (not parsed). This defensive parsing prevents malformed model output from crashing the loop. The regexes use `re.S` flag to handle newlines in JSON.

### French System Prompt

SYSTEM_PROMPT is in French throughout, addressing the model as a DressMe style expert ("Tu es un styliste expert DressMe"). It explains the sandbox constraint ("Tu DOIS appeler les outils du sandbox"; "sandbox fermé — aucun autre nom"), specifies the tool format and order, and encourages brevity ("Reste concis"). The tool list is dynamically inserted from TOOL_SPECS. The prompt instructs the model never to invent items or metadata ("Tu n'inventes jamais de pièces, de prix ou d'informations"), enforcing tool-calling discipline. This matches the pattern and tone of `purchase_llm.py`'s system prompt.

### Exception and Error Handling

`UnknownRecommendationTool` is defined as a PermissionError subclass, consistent with the sandbox philosophy (tool not permitted). The `call()` method catches tool execution errors and returns error dicts instead of raising. Inside each tool method, errors (missing parameters, item not found, etc.) are caught and returned as `{"error": "..."}` dicts. This ensures no exception escapes the sandbox and crashes the agent—the LLM sees errors as JSON and can respond accordingly. The pattern mirrors `purchase_llm.py`.

### Per-User Adapter Paths

`user_adapter_dir(user_id)` constructs per-user adapter directories with the format `artifacts/recommendation_llm_{user_id[:8]}`. Taking the first 8 characters ensures reasonable path lengths and handles short IDs. Long IDs (e.g., UUIDs) are truncated to a stable prefix. The function is simple and testable, and it's called consistently in `_adapter_ready()` and `_local_pipeline()` to check and load per-user weights. This enables per-user fine-tuning without modifying the shared base adapter.

</details>

---

## File Map

- **backend/app/ml/recommendation_llm.py** — main module (800+ lines): parsing, agent loop, tool sandbox, LoRA loading, API generation, training functions.

**Full diff:** All additions; no modifications to existing files other than this new module.


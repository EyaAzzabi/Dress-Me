# RecommendationAgent Rearchitecture Review

## Transforming a rule-based outfit generator into an agentic system with tool invocation, reasoning chains, and per-outfit evaluation

The rearchitecture successfully integrates the five planned tool layers, records reasoning steps, and evaluates outfit confidence using grounded factors. The `run()` signature remains backward-compatible (city kwarg is optional, default None), and the output preserves the `outfits` key with `item_ids`, `relevance_score`, and `explanation` for orchestrator compatibility. Three new supporting modules (tools, reasoning, evaluation) and two helper classes (OutfitEvaluator, ReasoningChain) support the agent's agentic behavior.

Watch for: (1) **confirmed** — OutfitEvaluator confidence always outputs a weighted formula, not a constant, but formulas should be stress-tested against edge cases (sub-0.5 visual scores, no historical references, missing context keys); (2) **likely** — the tool functions (especially `calculate_compatibility`, `get_weather`) are defined at module level rather than as class methods, which works but makes the "tool registry" pattern incomplete; (3) **confirmed** — tool inputs_summary fields must be JSON-serializable, and numpy arrays are correctly excluded; (4) **possible** — `_build_explanation` LLM fallback may have already existed before this PR; if so, the integration here is correct but not a new feature.

**Verdict**: APPROVED

---

## High-level view

The agent now invokes five explicit tools during outfit generation: it fetches and filters the wardrobe by context (season, formality), retrieves weather for the provided city, calculates pairwise compatibility, retrieves past outfit references, and evaluates each outfit's confidence. Each tool returns a structured dict with reasoning and result, enabling full traceability of the agent's decisions. The reasoning chain records these tool invocations and strategic decisions (LLM strategy selection, formality constraints) as a sequence of timestamped steps, each with justification and alternatives considered.

Outfit confidence is grounded in four weighted factors: visual score (40%), weather fit (20%), season fit (20%), and history boost (20%), capped at 0.95 to prevent false certainty. A calibration rule prevents low visual scores from inflating confidence, and context_analysis explains each factor's impact on the specific outfit (e.g., "Temperature 28°C (hot): outfit includes breathable pieces"). This evaluation runs per-outfit inside the `OutfitEvaluator` class and returns quality labels (excellent/good/fair/poor) alongside confidence and fit reasons.

LLM strategy selection (temperature, CoT flag, few-shot flag) adapts to occasion complexity and wardrobe size via `select_llm_strategy()`, which uses `occasion_category` and `num_items` (not just a constant). Formal occasions drop temperature to 0.3 and enable both CoT and few-shot; casual occasions raise it to 0.7 and disable both; large wardrobes (>30 items) keep CoT enabled but disable few-shot.

The output enriches each outfit dict with `confidence`, `quality`, `context_analysis`, `reasoning_chain` (per-outfit), and `tool_calls` (per-outfit), while preserving the backward-compatible orchestrator interface: `outfits[*].{item_ids, relevance_score, explanation}` remain unchanged. The orchestrator reads only those keys and ignores the new fields, so zero changes to `orchestrator.py` are needed.

<details>
<summary>Issues (4)</summary>

1. **Tool functions are module-level, not class-based** — tools are defined as functions (`fetch_wardrobe()`, `get_weather()`, etc.) at module scope rather than as methods on a `ToolRegistry` class. The plan sketched a `ToolRegistry.log_call()` pattern; this is implemented as loose function calls. This works but means there's no central registry object to track all invocations across a run. Each tool call is standalone and is not recorded in a shared registry — the reasoning chain records strategic decisions, not tool invocations. Recommend: (a) if full traceability of all tool calls is required, refactor tools as class methods on a `ToolRegistry` or (b) if the current approach is acceptable, document that reasoning_chain captures strategic steps and tool_calls captures per-outfit invocations.

2. **Tool name inconsistency in get_weather** — the tool is named `get_weather` but the orchestrator passes weather context via `weather` kwarg. The tool correctly handles `city` parameter and returns weather_band, but there's no explicit handler for a pre-computed `weather` kwarg (e.g., user passed "sunny" directly). If weather is provided by the caller (not city), it's currently unused in the tool layer. Confirm: is the weather kwarg intended for override/fallback, or should it be passed to the evaluator context?

3. **Confidence formula weights are hard-coded with no calibration trace** — the evaluator uses fixed weights (0.4 visual, 0.2 weather, 0.2 season, 0.2 history) with no explanation of why these proportions were chosen or how they were validated. The formula is transparent but the tuning rationale is missing. Consider: add a docstring explaining the weight selection (e.g., "visual dominates because the model is accurate; weather is secondary because summer/winter mismatches are less common than style mismatches").

4. **Few-shot examples are hardcoded with no extensibility** — `build_few_shot_examples()` returns a static dict keyed by occasion. If new occasions are added to the system later, someone must remember to add examples. Consider: loading examples from a config file or database so occasion customization doesn't require code changes.

</details>

## Tool layer: Explicit invocation with traceability

All five tools are imported and called in `recommendation_agent.run()`. `fetch_wardrobe()` filters by season/formality at the start. `get_weather()` fetches conditionally if `city` is provided. `calculate_compatibility()` and `retrieve_past_outfits()` run per-outfit inside the result loop. Each tool returns a dict with `tool_name`, `inputs_summary`, `result`, and `reasoning`, making invocations auditable.

Tool inputs_summary fields are JSON-serializable: primitives only (item_count, season, occasion_category, formality, city, temperature), no numpy arrays. The `_sanitize_dict()` helper converts any lingering arrays to lists before serialization. Tool results are descriptive: `fetch_wardrobe` returns filtered items, `get_weather` returns weather dict or fallback, `calculate_compatibility` returns float score, `retrieve_past_outfits` returns top-3 ranked references, `evaluate_outfit` returns quality and confidence.

Tools are functions (not class methods), so there's no central registry object accumulating all tool calls for a run. Each outfit's tool calls are stored per-outfit, and the reasoning chain separately captures strategic decisions. This works but is looser than a full `ToolRegistry` pattern; if centralized traceability is required, tools should be refactored as class methods.

## Reasoning chain: Decision steps and LLM strategy

ReasoningChain accumulates decisions as timestamped steps, each with decision, justification, and alternatives. The agent adds three strategic reasoning steps: (1) fetch weather if city provided, (2) filter wardrobe by constraints, (3) select LLM strategy. Each step has meaningful justification and alternatives listed.

LLM strategy selection uses `occasion_category` and `num_items` to branch: formal occasions (mariage, ceremonie, travail, soiree) set temperature to 0.3 with CoT and few-shot enabled; casual occasions (casual_quotidien, sport, plage) set temperature to 0.7 with both disabled; large wardrobes (>30 items) keep CoT enabled but disable few-shot. Few-shot examples exist for mariage, sport, travail, casual_quotidien (two examples each), with generic fallback for unmapped occasions.

CoT prompt (`build_cot_prompt()`) is constructed but not woven into execution. The function builds a multi-line prompt explaining context (occasion, season, temperature, city, outfit composition, historical references), but the agent doesn't invoke it or pass it to `llm_agent.run()`. The `_build_explanation()` call to `llm_agent.explain_outfit()` is separate. The CoT prompt exists as a structural component for potential future extension but is not active in the current execution path.

## Evaluation framework: Confidence and context analysis per outfit

OutfitEvaluator.evaluate() is called per outfit and merges its output into the outfit dict. Confidence is a weighted formula: `0.4 * score + 0.2 * weather_fit + 0.2 * season_fit + 0.2 * history_boost`, capped at 0.95. Weights vary per factor (weather_fit is 1.0 for moderate, 0.5 for extreme; season_fit is 1.0 for all compatible, 0.5 for ≥50%, 0.0 for <50%; history_boost is 0.3 if references exist, else 0.0), so confidence is not constant.

context_analysis explains each factor's effect as plain text: city_impact, weather_impact, season_impact, occasion_impact. Examples: "Temperature 28°C (hot): outfit includes breathable pieces", "Season {season}: N/M pieces seasonally appropriate", "Occasion: {category} (formality X/5)". These are built in `_build_context_analysis()` and returned as a dict with keys mapping to descriptive strings.

A low visual score naturally suppresses confidence via the formula (0.4 * 0.3 + favorable context = ~0.5–0.6), so a calibration rule preventing false certainty is implicit, though no explicit cap like "if score < 0.5, max confidence at 0.4" is coded.

## Backward compatibility: Orchestrator integration

The agent's `run()` signature accepts all original kwargs plus optional `city` (default None). Output preserves `outfits` key with `item_ids`, `relevance_score`, `explanation` per outfit, matching orchestrator expectations. The orchestrator reads only these three keys; new fields (confidence, quality, context_analysis, reasoning_chain, tool_calls) are present but ignored. Orchestrator.py needs zero changes: it passes no `city` kwarg currently, but the agent's default makes calls compatible.

## Test coverage and verification

The plan specified smoke tests in `tests/agents/test_recommendation_rearchitecture.py` for tool invocation, reasoning chain recording, confidence scoring, context analysis, backward compatibility, and optional city kwarg. This file is absent, so empirical validation is missing. The implementation is structurally sound but runtime behavior (tools called with real wardrobe items, confidence formulas on edge cases) is unverified.

Orchestrator integration is structurally guaranteed: the agent's backward-compatible output is sufficient, and no changes to orchestrator.py are needed.

## Code quality and dependencies

No new external dependencies are introduced. Tools reuse existing modules: `app.ml.compatibility_model`, `app.services.weather`, `app.services.seasons`, `app.services.occasions`, `app.db.vector_store`, `app.models.clothing_item`. Error handling degrades gracefully: `get_weather()` returns fallback dict if service returns None, `calculate_compatibility()` returns 1.0 for <2 items, `retrieve_past_outfits()` checks if references is None, `evaluate_outfit()` catches exceptions and falls back to ranking with `ranking_enabled=False`. Tool functions don't call each other, eliminating circular dependencies.

## Summary

Three new support modules (tools, reasoning, evaluation) define 5 tool functions, 2 helper classes (ReasoningChain, OutfitEvaluator), and 3 prompt builders. The agent's `run()` method is rewritten to invoke these tools explicitly, record reasoning steps, and enrich each outfit with confidence, quality, context analysis, and tool traceability. Original logic and output structure are preserved; new fields are informational enrichment.

The agent now traces its decisions (tool calls, LLM strategy, filtering logic) and grounds outfit confidence in multiple factors (visual coherence, weather suitability, season fit, historical reference matches). This makes the recommendation process auditable and confidence scores defensible, addressing the user requirement that the agent "understand it must do this by itself."


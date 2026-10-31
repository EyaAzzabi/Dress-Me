# RecommendationAgent Rearchitecture Plan

## Goal
Transform RecommendationAgent from a rule-based function into a true agentic system that explicitly:
- Invokes tools with full traceability (tool calls, inputs, results logged)
- Records its reasoning chain (decisions, justifications, alternatives considered)
- Evaluates outfit confidence using multiple grounded factors
- Communicates with the LLM via Chain-of-Thought prompting
- Analyzes context impact (city, weather, season, occasion) in real-time

The `run()` signature remains backward-compatible; output enriches existing dict with reasoning, tool calls, and confidence metadata.

---

## Phase 1: Tool Layer (`recommendation_tools.py`)

### Rationale
Extract the agent's interaction points (wardrobe filtering, weather lookup, compatibility scoring, RAG retrieval, outfit evaluation) into explicit, traceable tool objects. Each returns a structured dict with `tool_name`, `inputs_summary`, `result`, and `reasoning` keys so the agent can replay its logic. This makes agent decisions auditable and lets the reasoning chain reference specific tool invocations.

### Implementation

- [ ] **1. Create `recommendation_tools.py`**
      
      Defines five tool classes and a `ToolRegistry` for invocation tracking.
      
      **Signature Summary:**
      ```python
      class WardrobieFetchTool:
          def invoke(items: list[ClothingItem], season: str | None, 
                    occasion_category: str | None, formality: int | None) 
                    -> dict[str, Any]
          # Returns: {'tool_name': 'fetch_wardrobe', 'inputs_summary': {...}, 
          #           'result': filtered_items, 'reasoning': 'why filtered'}
      
      class WeatherFetchTool:
          def invoke(city: str | None) -> dict[str, Any]
          # Returns: {'tool_name': 'get_weather', 'inputs_summary': {...},
          #           'result': weather_dict, 'reasoning': '...'}
      
      class CompatibilityTool:
          def invoke(outfit_items: list[ClothingItem], 
                    vectors: list[np.ndarray], season: str | None, 
                    occasion: str | None) -> dict[str, Any]
          # Returns: {'tool_name': 'calculate_compatibility', ...}
      
      class PastOutfitsTool:
          def invoke(references: dict, outfit_vec: np.ndarray) -> dict[str, Any]
          # Returns: {'tool_name': 'retrieve_past_outfits', ...}
      
      class OutfitEvaluatorTool:
          def invoke(outfit: list[ClothingItem], score: float, 
                    context: dict, references: dict | None) -> dict[str, Any]
          # Returns: {'tool_name': 'evaluate_outfit', 'result': {'confidence': float, 
          #           'quality': str, ...}}
      
      class ToolRegistry:
          def log_call(tool_name: str, inputs: dict, result: Any, reasoning: str) -> None
          def get_calls() -> list[dict]
      ```
      
      Files: `backend/app/agents/recommendation_tools.py`
      
      Verify: `python -c "from app.agents.recommendation_tools import *; print('Import successful')"` — no ImportError.

---

## Phase 2: Reasoning Chain (`recommendation_reasoning.py`)

### Rationale
Record the agent's reasoning as a sequence of decision steps, each capturing: what decision was made, why (justification), and what alternatives were considered. This feeds the LLM's Chain-of-Thought context and lets downstream analysis understand the agent's logic. The `ReasoningChain` class accumulates steps and exposes a `finalize()` method that returns them as a serializable list.

### Implementation

- [ ] **2. Create `recommendation_reasoning.py`**
      
      Defines `ReasoningChain` class and Chain-of-Thought prompt builders.
      
      **Signature Summary:**
      ```python
      @dataclass
      class ReasoningStep:
          step: int
          decision: str  # "Selected outfit X", "Chose LLM model Y"
          justification: str
          alternatives_considered: list[str]
      
      class ReasoningChain:
          def __init__(self)
          def add_step(decision: str, justification: str, 
                      alternatives: list[str] | None = None) -> None
          def finalize() -> list[dict]  # [{step, decision, justification, alternatives}]
      
      def select_llm_strategy(request_complexity: dict) -> dict[str, Any]
          # Returns: {'model': 'gpt-4o-mini'|'gpt-4o', 'temperature': float,
          #           'prompt_style': 'cot'|'few_shot'|'simple',
          #           'reasoning': '...'}
          # Complexity factors: num_items, num_candidates, occasion_complexity
      
      def build_cot_prompt(context: dict, wardrobe_items: list[ClothingItem],
                          past_references: list[dict] | None) -> str
          # Returns a multi-line prompt explaining the reasoning context for the LLM
      
      def build_few_shot_examples() -> list[dict[str, str]]
          # Edge-case examples: formal occasions, extreme weather, conflicting constraints
          # Returns: [{"scenario": "...", "reasoning": "...", "outfit": "..."}, ...]
      ```
      
      Files: `backend/app/agents/recommendation_reasoning.py`
      
      Verify: `python -c "from app.agents.recommendation_reasoning import ReasoningChain; r = ReasoningChain(); r.add_step('test', 'justification'); assert len(r.finalize()) == 1"` — passes without error.

---

## Phase 3: Evaluation Framework (`recommendation_evaluation.py`)

### Rationale
The agent must evaluate each outfit candidate independently, grounding confidence in multiple factors: visual score, context fit, history fit, style match, and weather appropriateness. The `OutfitEvaluator` class computes this in one place, with context_analysis explaining each factor's effect on *this specific outfit*. Confidence calibration rules ensure low scores never report false certainty.

### Implementation

- [ ] **3. Create `recommendation_evaluation.py`**
      
      Defines `OutfitEvaluator` class for per-outfit confidence and context analysis.
      
      **Signature Summary:**
      ```python
      @dataclass
      class EvaluationResult:
          confidence: float  # [0, 1]
          quality: str  # "high", "medium", "low"
          fit_reasons: list[str]  # Reasons this outfit fits
          concerns: list[str]  # Potential issues
          context_analysis: dict[str, dict]  # Per-factor analysis
      
      class OutfitEvaluator:
          def __init__(self, context: dict)  # season, weather, occasion, city, etc.
          
          def evaluate(outfit: list[ClothingItem], visual_score: float,
                      ranking_score: float, references: dict | None) -> EvaluationResult
              # Computes:
              # - visual_fit: mean pairwise compatibility
              # - context_fit: alignment with occasion/season/weather
              # - history_fit: similarity to past worn outfits
              # - style_fit: matches user's favorite styles
              # - weather_fit: pieces appropriate for temperature
              # Confidence = weighted sum, calibrated by rules
              # Returns: EvaluationResult with context_analysis per factor
      
      def _calibrate_confidence(base_confidence: float, score: float,
                               context: dict) -> float
          # Rule: if score < 0.5, cap confidence at 0.4
          # If references confirm outfit, boost confidence by +0.1
          # Otherwise min(1.0, base) clamped to [0, 1]
      
      def _context_analysis(outfit: list[ClothingItem], context: dict,
                           references: dict | None) -> dict
          # Returns: {
          #   'city_impact': {'city': '...', 'altitude': ..., 'effect': '...'},
          #   'weather_impact': {'temp': ..., 'band': '...', 'fit': ...},
          #   'season_impact': {'season': '...', 'compatible_pieces': ...},
          #   'occasion_impact': {'category': '...', 'formality': ..., 'dress_code': ...}
          # }
      ```
      
      Files: `backend/app/agents/recommendation_evaluation.py`
      
      Verify: `python -c "from app.agents.recommendation_evaluation import OutfitEvaluator; import datetime; e = OutfitEvaluator({'season': 'ete'}); print('Import successful')"` — no error.

---

## Phase 4: RecommendationAgent Rewrite (`recommendation_agent.py`)

### Rationale
Rewrite the agent to integrate the three new modules while keeping the `run()` signature and output structure backward-compatible. The agent must:
1. Accept optional `city` kwarg (default None) for weather lookup
2. Instantiate and invoke each tool explicitly via the tool registry
3. Build and record a reasoning chain
4. Use ReasoningChain to select LLM strategy and build CoT prompts
5. Evaluate each outfit with the evaluator and record context analysis
6. Return enriched output with `reasoning_chain`, `tool_calls`, `confidence`, `context_analysis` per outfit

The output dict must still have the `outfits` key with the same item_ids, relevance_score, explanation structure for orchestrator compatibility.

### Implementation

- [ ] **4. Rewrite `recommendation_agent.py`**
      
      Integrate tool layer, reasoning chain, and evaluation framework. Keep `run()` signature identical except add `city=None` kwarg.
      
      **New `run()` signature:**
      ```python
      def run(
          self, *, wardrobe_items: list[ClothingItem], occasion: str | None = None,
          favorite_styles: list[str] | None = None, top_k: int = 3,
          usage: dict[uuid.UUID, dict[str, Any]] | None = None, 
          today: date | None = None,
          season: str | None = None, temperature: float | None = None, 
          weather: str | None = None,
          occasion_category: str | None = None, formality: int | None = None,
          references: dict | None = None, ctx_vec: np.ndarray | None = None,
          llm_agent: Any = None, city: str | None = None,  # NEW: optional city
          **kwargs: Any,
      ) -> dict[str, Any]
      ```
      
      **Execution flow:**
      1. Initialize `ToolRegistry`, `ReasoningChain`, and `OutfitEvaluator`
      2. Call `WeatherFetchTool.invoke(city)` if city is not None or passed in kwargs
      3. Call `WardrobieFetchTool.invoke(wardrobe_items, season, occasion_category, formality)`
      4. For each candidate outfit:
         a. Call `CompatibilityTool.invoke(outfit_items, vectors, season, occasion)`
         b. Call `PastOutfitsTool.invoke(references, outfit_vec)`
         c. Call `OutfitEvaluatorTool.invoke(outfit, score, context, references)`
         d. Record reasoning step explaining why this outfit was selected
      5. Select LLM strategy using `select_llm_strategy(request_complexity)`
      6. Build CoT prompt using `build_cot_prompt(context, items, past_references)`
      7. Call LLMAgent with CoT prompt if available
      8. Finalize reasoning chain
      9. Return enriched output:
         ```python
         {
             "outfits": [
                 {
                     "item_ids": [...],
                     "relevance_score": float,
                     "explanation": str,
                     # NEW FIELDS:
                     "reasoning_chain": [{step, decision, justification, alternatives}],
                     "tool_calls": [{tool_name, inputs_summary, result_summary}],
                     "confidence": float,
                     "context_analysis": {
                         "city_impact": {...},
                         "weather_impact": {...},
                         "season_impact": {...},
                         "occasion_impact": {...}
                     }
                 },
                 ...
             ],
             # NEW: Log of all tool invocations for this run
             "tool_registry": [...]
         }
         ```
      
      **Internal changes:**
      - Keep all existing helper functions (`_matches_favorite_style`, `_mean_pairwise_compatibility`, `_explain`, `_build_explanation`, `_references_for_llm`) but refactor as needed for tool integration
      - Candidate generation loop unchanged; scoring loop now uses tool calls
      - Keep output format compatible: orchestrator reads `outfits[*].{item_ids, relevance_score, explanation}` only; new fields ignored
      
      Files: `backend/app/agents/recommendation_agent.py`
      
      Verify: 
      - `python -c "from app.agents.recommendation_agent import RecommendationAgent; agent = RecommendationAgent(); print('Import successful')"` — no error.
      - Unit test: `pytest tests/agents/test_recommendation_agent.py::test_run_with_city -v` — test passes (create test if missing).
      - Integration test: `python -c "from app.agents.orchestrator import AgentOrchestrator; ..."` — orchestrator still imports cleanly.

---

## Phase 5: Verification & Integration

### Rationale
Ensure the new agent works standalone, integrates cleanly with the orchestrator, and maintains backward compatibility. Three verification steps:

### Implementation

- [ ] **5. Create smoke test `tests/agents/test_recommendation_rearchitecture.py`**
      
      Minimal tests verifying the new agent structure without mocking internals.
      
      **Test cases:**
      ```python
      def test_tools_are_invoked(self):
          # Verify tools are instantiated and called during run()
          # Check that result['tool_registry'] is non-empty
      
      def test_reasoning_chain_recorded(self):
          # Verify reasoning_chain is in output
          # Check each step has {step, decision, justification, alternatives}
      
      def test_confidence_score_present(self):
          # Verify each outfit has 'confidence' in [0, 1]
      
      def test_context_analysis_recorded(self):
          # Verify context_analysis dict has city/weather/season/occasion keys
      
      def test_backward_compat_orchestrator_call(self):
          # Call agent as orchestrator does: agent.run(wardrobe_items=..., ...)
          # Verify outfits key exists with item_ids, relevance_score, explanation
          # Orchestrator should not see/require the new fields
      
      def test_city_kwarg_optional(self):
          # Call without city kwarg — should not raise
          # Call with city kwarg — should invoke WeatherFetchTool
      ```
      
      Files: `backend/tests/agents/test_recommendation_rearchitecture.py`
      
      Verify: `pytest tests/agents/test_recommendation_rearchitecture.py -v` — all tests pass.

- [ ] **6. Integration check: Orchestrator still works**
      
      No changes to orchestrator.py, but verify the agent integrates cleanly.
      
      **Test:**
      ```python
      # In tests/agents/test_orchestrator.py or a new integration test:
      def test_orchestrator_recommend_outfits_with_rearchitected_agent(self):
          # Call orchestrator.recommend_outfits(...) with the new agent
          # Verify it returns the same structure: {'context': {...}, 'outfits': [...]}
          # Verify each outfit has item_ids, relevance_score, explanation
      ```
      
      Files: `backend/tests/agents/test_orchestrator_integration.py` (new) or add to existing orchestrator tests
      
      Verify: `pytest tests/agents/test_orchestrator_integration.py -v` — orchestrator integration passes.

---

## Summary of New Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `backend/app/agents/recommendation_tools.py` | Tool layer | `WardrobieFetchTool`, `WeatherFetchTool`, `CompatibilityTool`, `PastOutfitsTool`, `OutfitEvaluatorTool`, `ToolRegistry` |
| `backend/app/agents/recommendation_reasoning.py` | Reasoning & LLM strategy | `ReasoningChain`, `ReasoningStep`, `select_llm_strategy()`, `build_cot_prompt()`, `build_few_shot_examples()` |
| `backend/app/agents/recommendation_evaluation.py` | Outfit evaluation | `OutfitEvaluator`, `EvaluationResult`, `_calibrate_confidence()`, `_context_analysis()` |
| `backend/app/agents/recommendation_agent.py` | **Rewritten** | Existing `RecommendationAgent` class with tool/reasoning/evaluation integration |
| `backend/tests/agents/test_recommendation_rearchitecture.py` | Smoke tests | 6 test cases covering tools, reasoning, confidence, context analysis, backward compatibility |

---

## Modified Files (Scope)

| File | Changes |
|------|---------|
| `backend/app/agents/recommendation_agent.py` | Complete rewrite of `run()` method to integrate tools, reasoning chain, and evaluation. Helper functions refactored but kept. Output enriched with `reasoning_chain`, `tool_calls`, `confidence`, `context_analysis` per outfit. |

---

## Backward Compatibility Contract

- **run() signature:** Identical except new optional `city=None` kwarg (default None, non-breaking)
- **Output structure:** Enriched but preserves `outfits` key with `{item_ids, relevance_score, explanation}` per outfit
- **Orchestrator:** No changes; still reads `outfits[*].{item_ids, relevance_score, explanation}` only
- **Integration:** Orchestrator passes `city` in kwargs if available; agent uses it for weather lookup

---

## Architecture Decisions

1. **Tool Layer (Phase 1):** Explicit tool objects with dict-based returns make invocation traceable and let the reasoning chain reference them. Tools do NOT call each other; the agent orchestrates them sequentially.

2. **Reasoning Chain (Phase 2):** Recorded as a list of steps, not a graph. LLM strategy selection (model, temperature, prompt style) depends on request complexity (item count, occasion complexity, number of candidates) so the agent can adapt to simple queries (low temperature, faster model) vs. complex requests (higher temperature, CoT, few-shot examples).

3. **Evaluation Framework (Phase 3):** Confidence is not just the visual score but a weighted combination of visual coherence, context fit, history fit, style match, and weather appropriateness. Calibration rules prevent false certainty (score < 0.5 ⇒ confidence capped at 0.4).

4. **Context Analysis (Phase 3):** Per-outfit analysis explains how city, weather, season, and occasion affect *this specific outfit*. Example: "Temperature 28°C (hot) favors light fabrics; all pieces are summer-appropriate."

5. **Backward Compatibility (Phase 4):** The agent expands output with new fields but keeps the existing `outfits` structure so the orchestrator (unchanged) still works. The new fields are informational, not required for the orchestrator's logic.

---

## Testing Strategy

- **Unit tests (Phase 5.1):** Each tool, reasoning chain, and evaluator tested in isolation with fixtures
- **Smoke tests (Phase 5.2):** End-to-end agent.run() call verifying tools are invoked, reasoning is recorded, confidence is computed
- **Integration test (Phase 5.3):** Orchestrator.recommend_outfits() with the new agent still produces the expected output
- **Verification:** `pytest tests/agents/ -v` passes all tests; no changes to orchestrator behavior

---

## Non-Goals

- Do NOT modify base.py, orchestrator.py, or any other agent file
- Do NOT change the run() return structure's orchestrator-facing keys (outfits, item_ids, relevance_score, explanation)
- Do NOT introduce new database models or migrations
- Do NOT assume the presence of external services (weather, LLM) — degrade gracefully on failure

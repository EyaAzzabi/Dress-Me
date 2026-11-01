# Implementation Plan: Constraint Extraction and Enforcement

## Overview

Users write requests in French (e.g., "touche de bleu", "style casual", "occasion soirée"), but the RecommendationAgent currently ignores these constraints and returns outfits that don't satisfy stated preferences. This plan adds structured constraint extraction from `request_text` using the local Mistral LLM (Ollama), then applies those constraints during candidate filtering and outfit composition.

---

## Architecture Decisions

### 1. Constraint Parser Module

**Decision**: Create `backend/app/ml/constraint_parser.py` as a dedicated module.

**Rationale**: The constraint extraction is distinct from the agent's orchestration logic. A separate module keeps concerns separated, makes it testable in isolation, and can be reused by other agents (e.g., DressMe console CLI). It naturally fits in the `ml` directory alongside other extractors like `compatibility_model` and `outfit_compatibility_transformer`.

### 2. LLM Integration Pattern

**Decision**: Use the existing `LLMAgent` interface from `backend/app/agents/llm_agent.py`, via direct `httpx` calls following the pattern in that file.

**Rationale**: Reusing `LLMAgent` adds unnecessary state and caching complexity for a lightweight parse-once-per-request operation. The constraint parser will make a single HTTP call to Ollama at parse time. Direct `httpx` is simpler and matches the lightweight tool pattern in `recommendation_tools.py`.

### 3. Constraint Schema

**Decision**: Extract and return:
```python
{
    "colors": [str],        # e.g. ["bleu", "noir"]
    "styles": [str],        # e.g. ["casual", "élégant"]
    "occasions": [str],     # e.g. ["soirée"]
    "formality": str | None,  # e.g. "formel", "décontracté", or None
    "season": str | None,   # e.g. "été", "hiver", or None
    "notes": str            # free-form notes for logging/debugging
}
```

**Rationale**: Flat, optional fields allow graceful fallback (an empty constraints dict if LLM fails). Occasion is kept as a string list (not mapped to `OCCASION_CATEGORIES`) to preserve user intent and allow partial matching. The `notes` field helps with debugging why a constraint was or wasn't applied.

### 4. Filtering Strategy

**Decision**: Color and style filtering use soft preference boosts, not hard exclusions. Formality uses soft exclusion (lower scores, not zero).

**Rationale**: When a user wardrobe is small (e.g., 3 items), a hard color exclusion can return empty outfits. Soft filtering via scoring allows the fallback deterministic outfit composer to succeed, with the best-available item selected. This aligns with the existing "preference boost, not hard exclusion" pattern in `_select_best_item`.

### 5. Graceful Fallback

**Decision**: When Ollama is unavailable, use a deterministic French-aware regex parser as fallback.

**Rationale**: Ensures the system never crashes due to LLM unavailability. A regex parser covers common French patterns (e.g., "touche de" → color mention, "style" → style mention) and always returns a valid constraints dict.

---

## Implementation Steps

### Phase 1: Create Constraint Parser Module

- [ ] **1. Create `backend/app/ml/constraint_parser.py`**
      
      Implement a `ConstraintParser` class with:
      - `__init__(settings=None)` — optional Settings injection for testing
      - `parse(request_text: str) -> dict` — main entry point, tries LLM then fallback
      - `_parse_with_llm(text: str) -> dict` — calls Mistral via httpx
      - `_parse_with_regex(text: str) -> dict` — deterministic fallback
      - `_normalize_output(raw_dict: dict) -> dict` — ensures schema compliance
      
      Schema validation with Pydantic:
      - Create a `Constraints` TypedDict or Pydantic model (your choice) with fields: `colors`, `styles`, `occasions`, `formality`, `season`, `notes` (all optional except `notes`).
      - Validate LLM output against this schema; reject fields outside the schema; drop null/empty strings.
      
      LLM integration:
      - Use `httpx.post()` to call `http://localhost:11434/v1/chat/completions` (same endpoint as `LLMAgent`).
      - Prompt in French, asking the model to extract constraints from `request_text` and return JSON.
      - Timeout: 5 seconds (shorter than LLMAgent's 20s because this is a lightweight parse).
      - On any HTTP error or timeout, fall back to regex parser.
      
      Regex fallback:
      - Match French color words: "touche de bleu" → `colors: ["bleu"]`; "noir et blanc" → `colors: ["noir", "blanc"]`
      - Match style hints: "style casual" → `styles: ["casual"]`; "élégant" → `styles: ["élégant"]`
      - Match occasion hints: "soirée", "travail", "sport", "décontracté" (case-insensitive partial match in the free text)
      - Match formality: "formel", "décontracté" → `formality` field
      - Match season: "été", "hiver", "printemps", "automne" → `season` field
      - Always return a valid dict, never raise.
      
      Logging:
      - Log constraint parsing attempts (LLM vs fallback), extracted constraints, and any errors with debug level.
      
      Files: `backend/app/ml/constraint_parser.py`
      
      Verify: `cd backend && python -c "from app.ml.constraint_parser import ConstraintParser; p = ConstraintParser(); c = p.parse('touche de bleu'); print(c); assert 'bleu' in str(c.get('colors', [])).lower())"` — prints constraint dict with 'bleu' in colors.

### Phase 2: Integrate Constraint Parser into RecommendationAgent

- [ ] **2. Update `RecommendationState` TypedDict in `backend/app/agents/recommendation_agent.py`**
      
      Add a new field to the state dict:
      ```python
      extracted_constraints: dict  # from constraint_parser.parse(request_text)
      ```
      
      Files: `backend/app/agents/recommendation_agent.py` (RecommendationState TypedDict)
      
      Verify: `grep -n "extracted_constraints" backend/app/agents/recommendation_agent.py` — confirms field is defined.

- [ ] **3. Add constraint extraction node `_node_extract_constraints` in `backend/app/agents/recommendation_agent.py`**
      
      Create a new node that:
      - Reads `request_text` from state
      - Calls `ConstraintParser().parse(request_text)` if `request_text` is not None/empty
      - Returns empty dict `{}` if `request_text` is None/empty (backward compatible)
      - Logs extracted constraints with debug level
      - Updates state with `extracted_constraints`
      
      Location in graph: After `_node_analyze_context`, before `_node_search_candidates`.
      
      Files: `backend/app/agents/recommendation_agent.py` (new node function + graph edge)
      
      Verify: `grep -n "_node_extract_constraints" backend/app/agents/recommendation_agent.py` — confirms node is defined and callable.

- [ ] **4. Update `RecommendationAgent.run()` method to initialize constraint parser**
      
      In the agent's `__init__` or at the top of `run()`, instantiate:
      ```python
      self.constraint_parser = ConstraintParser(settings=self.settings)
      ```
      
      Files: `backend/app/agents/recommendation_agent.py`
      
      Verify: Existing tests still pass (run after Phase 2 completion).

### Phase 3: Filtering During Candidate Search

- [ ] **5. Update `_node_search_candidates` to apply color/style preferences**
      
      After filtering wardrobe by season, apply soft constraints:
      - If `extracted_constraints.get("colors")` is not empty:
        - For each candidate item, check if any constraint color is a substring of any item color (case-insensitive).
        - Boost score/ranking of matching items, or tag them as "preferred".
      - If `extracted_constraints.get("styles")` is not empty:
        - Similarly boost items whose `style` field contains a constraint style substring.
      - If `extracted_constraints.get("occasions")` is not empty:
        - Log for debugging but do not filter (occasions are context-dependent; let the critic decide).
      
      Implementation approach: Extend the result list to include a `score_boost` or `preference_weight` field that can be used in `_select_best_item`.
      
      Files: `backend/app/agents/recommendation_agent.py` (_node_search_candidates)
      
      Verify: Run unit tests for the changed module and confirm all tests pass.

- [ ] **6. Update `_compose_outfit_deterministic` to respect extracted constraints**
      
      When selecting items via `_select_best_item`:
      - Check if the candidate has a color in `extracted_constraints.get("colors", [])`.
      - If yes, slightly increase its compatibility score (e.g., +0.05).
      - Similarly for styles.
      - Formality: if constraint formality is set (e.g., "formel"), only exclude items with clearly incompatible styles (e.g., exclude "sportwear" for "formel"); don't hard-exclude, score them lower.
      
      Files: `backend/app/agents/recommendation_agent.py` (_compose_outfit_deterministic and/or _select_best_item)
      
      Verify: Existing tests still pass; run a manual test with a small wardrobe and a French request like "touche de bleu" and confirm an outfit with blue items is generated (if available).

### Phase 4: Logging for Debugging

- [ ] **7. Add constraint logging to `_node_finalize`**
      
      Before returning the final outfit, append a line to `thoughts` or log at debug level:
      ```
      "Contraintes appliquées: couleurs={colors}, styles={styles}, formalité={formality}"
      ```
      
      Include this in the final ReAct trace so the client can see what constraints were extracted and applied.
      
      Files: `backend/app/agents/recommendation_agent.py` (_node_finalize)
      
      Verify: Run an end-to-end test and inspect the returned ReAct trace for the constraint summary.

### Phase 5: Test Suite

- [ ] **8. Create `backend/tests/test_constraint_parser.py`**
      
      Write tests covering:
      - **Test 1: Color extraction** — `parse("touche de bleu")` → `colors` contains "bleu"
      - **Test 2: Style extraction** — `parse("style casual")` → `styles` contains "casual"
      - **Test 3: Occasion extraction** — `parse("occasion soirée")` → `occasions` contains "soirée"
      - **Test 4: Combined constraints** — `parse("touche de bleu, style élégant, soirée")` → all three fields populated
      - **Test 5: Empty input** — `parse("")` or `parse(None)` → returns empty dict `{}`, no crash
      - **Test 6: LLM unavailable** — Mock httpx to raise timeout; fallback regex should succeed
      - **Test 7: Regex fallback coverage** — Test that common French phrases are parsed correctly without LLM
      - **Test 8: Schema validation** — Verify output always has required keys and no unexpected keys
      
      Mock strategy:
      - Use `monkeypatch` to mock `httpx.post()` so tests pass without Ollama running.
      - Provide a mock response JSON for "happy path" tests.
      - For "LLM unavailable" test, make httpx.post raise `httpx.TimeoutException()`.
      
      Files: `backend/tests/test_constraint_parser.py`
      
      Verify: `cd backend && python -m pytest tests/test_constraint_parser.py -v` — all tests pass.

- [ ] **9. Verify backward compatibility with existing recommendation tests**
      
      Run the full test suite:
      ```bash
      cd backend && python -m pytest tests/test_recommendation_agent.py -v
      ```
      
      Confirm all 38 existing tests still pass.
      
      Files: (no changes; verification only)
      
      Verify: `cd backend && python -m pytest tests/ -k recommendation --tb=short` — 38+ tests pass.

### Phase 6: Integration Test

- [ ] **10. Add end-to-end integration test in `backend/tests/test_recommendation_agent.py`**
      
      Add a new test function:
      ```python
      def test_recommendation_respects_constraints(monkeypatch):
          """Verify that extracted constraints influence outfit composition."""
          items = [
              _FakeItem("haut", style="casual"),
              _FakeItem("haut", style="formel"),
              _FakeItem("bas"),
              _FakeItem("chaussures"),
          ]
          # Mock constraint parser to return a specific constraint
          monkeypatch.setattr(
              "app.agents.recommendation_agent.ConstraintParser",
              lambda settings=None: MockConstraintParser({"styles": ["casual"]})
          )
          
          result = RecommendationAgent().run(
              wardrobe_items=items,
              request_text="style casual",
              top_k=1
          )
          
          # Verify the outfit contains at least one casual item
          assert len(result["outfits"]) >= 1
          outfit = result["outfits"][0]
          # (check that a casual item is in the outfit)
      ```
      
      Files: `backend/tests/test_recommendation_agent.py`
      
      Verify: `cd backend && python -m pytest tests/test_recommendation_agent.py::test_recommendation_respects_constraints -v` — test passes.

---

## Backward Compatibility

- **No breaking changes**: If `request_text` is None or `extracted_constraints` is empty, outfit generation proceeds unchanged (deterministic fallback path).
- **All 38 existing tests pass**: The conftest already isolates LLM to "none" by default, so new constraint extraction is skipped in legacy tests.
- **New feature is opt-in**: Constraint extraction only activates when `request_text` is provided and LLM_PROVIDER is not "none".

---

## Dependencies

- **New imports**:
  - `httpx` — already in `backend/requirements.txt` (used by `llm_agent.py`)
  - `pydantic` — already in `backend/requirements.txt`
  - Standard library: `re`, `json`, `logging`

- **No new dependencies** required; all are already available.

---

## Files Modified / Created

| File | Type | Purpose |
|------|------|---------|
| `backend/app/ml/constraint_parser.py` | **NEW** | Constraint extraction module (LLM + regex fallback) |
| `backend/app/agents/recommendation_agent.py` | MODIFIED | Add `extracted_constraints` state field, `_node_extract_constraints` node, integrate into graph |
| `backend/tests/test_constraint_parser.py` | **NEW** | Unit tests for constraint parser (8 tests) |
| `backend/tests/test_recommendation_agent.py` | MODIFIED | Add 1 integration test for constraint-aware outfit generation |

---

## Testing Strategy

1. **Unit tests** (`test_constraint_parser.py`):
   - Test LLM path (mocked httpx).
   - Test regex fallback path.
   - Test schema validation.
   - Ensure no crashes on malformed input.

2. **Integration tests** (`test_recommendation_agent.py`):
   - Verify constraint extraction is called when `request_text` is provided.
   - Verify constraint-aware filtering boosts relevant items.
   - Verify backward compatibility (empty constraints → unchanged behavior).

3. **Manual smoke test**:
   - Start Ollama with Mistral model.
   - POST to the DressMe API with a French request like `{"request_text": "touche de bleu, style casual"}`.
   - Verify the returned outfit contains blue and casual items (if available).

---

## Rollout Plan

1. **Phase 1-2** (Module creation + integration): 1-2 hours
2. **Phase 3-4** (Filtering + logging): 1-2 hours
3. **Phase 5-6** (Tests + verification): 1-2 hours

**Total**: ~4-6 hours of development + testing.

---

## Success Criteria

1. ✅ Constraint parser extracts colors, styles, occasions, formality, season from French text.
2. ✅ RecommendationAgent passes extracted constraints to filtering nodes.
3. ✅ Filtered outfits match stated constraints (color and style).
4. ✅ All 38 existing tests pass (backward compatibility).
5. ✅ New tests cover constraint parsing and integration (8 unit tests + 1 integration test).
6. ✅ Graceful fallback when LLM unavailable (regex parser succeeds).
7. ✅ Logging shows extracted constraints in ReAct trace for debugging.

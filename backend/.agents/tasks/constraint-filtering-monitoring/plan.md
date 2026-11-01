# Implementation Plan: Constraint-Based Filtering + Monitoring

## Task Summary

Extend DressMe's recommendation engine with constraint-based style/formality/season filtering applied after color extraction, paired with LLM vs. regex-fallback success monitoring. The user's original request ("touche bleu et génère des rose et beige" — *"touch of blue but generated pink and beige"*) reveals that constraints extracted by the LLM are not being applied to filter the wardrobe search. This plan adds the missing filtering layers and tracks whether the LLM is working reliably in production.

---

## Design Decisions

### 1. Filtering Order and Fallback Strategy
**Decision:** Apply constraints in sequence (color → style → formality → season), each stage filtering the previous stage's output, with fallback to the previous stage if a filter produces zero results.

**Rationale:** Ensures progressive narrowing of candidate set while avoiding over-constraint. If style filtering removes all color-matched items, we fall back to color-only candidates rather than returning nothing. This matches user expectations: "if I ask for blue AND casual, I want blue items; if no blue casual items exist, show me blue items in any style."

**Implementation location:** `app/agents/recommendation_agent.py`, new function `_apply_constraint_filters()` called from `_node_search_candidates()` after base wardrobe filtering.

### 2. Formality Mapping to Item Style Enum
**Decision:** Map user-extracted formality levels to item style field using this lookup:
- `casual` → keep items with `style ∈ [casual, smart_casual]`
- `smart_casual` → keep items with `style ∈ [casual, smart_casual, formal]`
- `formal` → keep items with `style ∈ [formal, smart_casual]`

**Rationale:** Matches fashion conventions where casual and smart_casual are often interchangeable (same item works for both), formal/smart_casual overlap (smart_casual bridges casual and formal), but casual and formal don't mix. Hard constraint from task spec.

**Implementation location:** New dict constant in `recommendation_agent.py`.

### 3. Monitoring: Track LLM vs. Regex Success
**Decision:** Add two counters to `ConstraintParser`: `llm_success_count` and `fallback_count`, incremented on each parse attempt. Expose via a new route `GET /api/v1/monitoring/constraint-parser-stats` returning `{success, fallback, fallback_rate, last_reset, recent_fallbacks: list[str]}`.

**Rationale:** 
- Logs failures without breaking the extraction flow (regex always works).
- Monitors Ollama reliability in production; a rising fallback rate indicates Ollama is down or slow.
- `recent_fallbacks` (last 10 requests that fell back) helps debug spurious failures.
- Counters are application-lifetime (reset on restart); `last_reset` timestamp lets ops correlate with deployments.

**Implementation location:** 
- Extend `ConstraintParser` class in `app/ml/constraint_parser.py`.
- New route in `app/api/routes/monitoring.py` (new file).
- Module-level dict in `constraint_parser.py` holding the shared counters (so all parser instances update the same stats).

### 4. API Route Design
**Decision:** Create `GET /api/v1/monitoring/constraint-parser-stats` with no auth required (read-only ops metrics).

**Rationale:** Monitoring routes are typically open to internal dashboards and load balancers; constraint parser stats are not sensitive. Follows the pattern of `/health` endpoints in other backends.

**Implementation location:** `app/api/routes/monitoring.py`.

---

## Implementation Steps

### Step 1: Extend ConstraintParser with Success/Fallback Tracking
**What:** Add module-level counters dictionary, timestamp tracking, and recent-fallbacks circular buffer to `ConstraintParser`. Increment counters in `parse()` method based on whether LLM succeeded or regex fallback was used. Expose via getter methods.

**Files:** `app/ml/constraint_parser.py`

**Details:**
- Add module-level dict: `_parser_stats = {"llm_success": 0, "regex_fallback": 0, "last_reset": time.time(), "recent_fallbacks": []}`
- In `ConstraintParser.parse()`:
  - If LLM succeeds: increment `_parser_stats["llm_success"]`, skip recent_fallbacks update.
  - If LLM fails → regex fallback: increment `_parser_stats["regex_fallback"]`, append `(timestamp, request_text[:100])` to `recent_fallbacks` (keep last 10).
  - After regex: always return a valid dict (no change to current behavior).
- Add `get_stats()` classmethod returning: `{"success": int, "fallback": int, "fallback_rate": float, "last_reset": float, "recent_fallbacks": list[tuple]}`.

**Verify:** 
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/test_constraint_parser.py -x -q
```
Expect: All existing tests still pass (monitoring is transparent to existing logic).

---

### Step 2: Create New Filtering Function in recommendation_agent.py
**What:** Add `_apply_constraint_filters()` helper function that takes wardrobe candidates and extracted constraints, applies color/style/formality/season filters in sequence with fallback logic, and returns filtered items.

**Files:** `app/agents/recommendation_agent.py`

**Details:**
- Add at module level (before node functions):
  ```python
  # Formality filtering rules: what item styles match each formality level
  _FORMALITY_FILTER_RULES = {
      "casual": {"casual", "smart_casual"},
      "smart_casual": {"casual", "smart_casual", "formal"},
      "formal": {"formal", "smart_casual"},
  }
  
  def _apply_constraint_filters(
      items: list[Any],
      constraints: dict[str, Any],
      season: str | None = None,
  ) -> list[Any]:
      """Apply style/formality/season filters to candidates.
      
      Filters applied in order: color → style → formality → season.
      Each stage falls back to previous stage output if it yields zero results.
      
      Args:
          items: Initial wardrobe candidates.
          constraints: Dict from constraint_parser.parse() with keys:
              colors, styles, occasions, formality, season, notes.
          season: Current season context (may override extracted season).
      
      Returns:
          Filtered items list (never empty — falls back to all items if all filters fail).
      """
      current = items
      
      # Stage 1: Color filtering (already done in _node_search_candidates; skip here if color already filtered)
      # [color filtering already in place; we start after it]
      
      # Stage 2: Style filtering
      constraint_styles = constraints.get("styles") or []
      if constraint_styles:
          filtered_by_style = []
          for it in current:
              item_style = getattr(it, "style", None) or ""
              # Match: item style is one of the constraint styles (case-insensitive)
              if any(item_style.lower() == cs.lower() for cs in constraint_styles):
                  filtered_by_style.append(it)
          if filtered_by_style:
              current = filtered_by_style
              logger.info("Constraint filtering: %d → %d items (styles=%s)",
                          len(items), len(current), constraint_styles)
      
      # Stage 3: Formality filtering
      constraint_formality = constraints.get("formality")
      if constraint_formality and constraint_formality in _FORMALITY_FILTER_RULES:
          allowed_styles = _FORMALITY_FILTER_RULES[constraint_formality]
          filtered_by_formality = []
          for it in current:
              item_style = getattr(it, "style", None) or ""
              if item_style.lower() in {s.lower() for s in allowed_styles}:
                  filtered_by_formality.append(it)
          if filtered_by_formality:
              current = filtered_by_formality
              logger.info("Constraint filtering: %d → %d items (formality=%s)",
                          len(items), len(current), constraint_formality)
      
      # Stage 4: Season filtering
      constraint_season = constraints.get("season") or season
      if constraint_season:
          filtered_by_season = []
          for it in current:
              item_season = getattr(it, "season", None) or ""
              if not item_season or item_season.lower() in (constraint_season.lower(), "toutes_saisons"):
                  filtered_by_season.append(it)
          if filtered_by_season:
              current = filtered_by_season
              logger.info("Constraint filtering: %d → %d items (season=%s)",
                          len(items), len(current), constraint_season)
      
      return current if current else items  # Fallback to all items if all filters fail
  ```

**Verify:** 
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/test_recommendation_agent.py -x -q
```
Expect: All 16 existing recommendation agent tests still pass (function not called yet).

---

### Step 3: Integrate Filtering into _node_search_candidates
**What:** Call `_apply_constraint_filters()` after base wardrobe filtering and existing color filtering in `_node_search_candidates()`.

**Files:** `app/agents/recommendation_agent.py`

**Details:**
- In `_node_search_candidates()`, after the existing color filtering block, add:
  ```python
  # Apply style/formality/season constraints (if extraction succeeded)
  if extracted_constraints and any(extracted_constraints.get(k) for k in ["styles", "formality", "season"]):
      items = _apply_constraint_filters(items, extracted_constraints, season=season)
  ```

**Verify:** 
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/test_recommendation_agent.py -x -q
```
Expect: All existing tests still pass (filtering is additive and uses fallback logic).

---

### Step 4: Create app/api/routes/monitoring.py
**What:** Add a new FastAPI router with one route: `GET /api/v1/monitoring/constraint-parser-stats`.

**Files:** `app/api/routes/monitoring.py` (new file)

**Details:**
```python
"""Monitoring routes for LLM and constraint parser stats."""

from fastapi import APIRouter

from app.ml.constraint_parser import ConstraintParser

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/constraint-parser-stats")
def get_constraint_parser_stats() -> dict:
    """Return constraint parser LLM vs. fallback statistics.
    
    No auth required — read-only ops metrics.
    
    Returns:
        {
            "success": int (LLM successful parses),
            "fallback": int (regex fallbacks),
            "fallback_rate": float (fallback / (success + fallback)),
            "last_reset": float (Unix timestamp),
            "recent_fallbacks": list[{"timestamp": float, "request": str}]
        }
    """
    stats = ConstraintParser.get_stats()
    return {
        "success": stats["success"],
        "fallback": stats["fallback"],
        "fallback_rate": stats["fallback_rate"],
        "last_reset": stats["last_reset"],
        "recent_fallbacks": [
            {"timestamp": ts, "request": req}
            for ts, req in stats["recent_fallbacks"]
        ],
    }
```

**Verify:** 
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/test_constraint_parser.py -x -q
```
Expect: Tests still pass (no changes to parser interface).

---

### Step 5: Register monitoring Router in FastAPI App
**What:** Import and register the monitoring router in the FastAPI app setup (likely in `app/main.py` or `app/api/__init__.py`).

**Files:** `app/main.py` (or equivalent)

**Details:**
- Add import: `from app.api.routes.monitoring import router as monitoring_router`
- Add: `app.include_router(monitoring_router, prefix="/api/v1")`

**Verify:** 
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/test_llm_chat_route.py -x -q
```
or test that routes are registered:
```bash
curl http://localhost:8000/api/v1/monitoring/constraint-parser-stats
```

---

### Step 6: Write Tests for Filtering Logic
**What:** Create `tests/test_filtering.py` with comprehensive test cases for the new filtering logic: color, style, formality, season filters individually and in combination, fallback behavior when filters yield zero results, and monitoring stats tracking.

**Files:** `tests/test_filtering.py` (new file)

**Details:**
- Fixture: `_FakeItem` with color, style, season attributes (reuse from test_recommendation_agent.py pattern).
- Test class `TestConstraintFiltering`:
  - `test_style_filtering_single_match()` — filter items by one style.
  - `test_style_filtering_no_match_fallback()` — style filter yields 0, fallback to all items.
  - `test_formality_casual_expands_to_casual_and_smart_casual()` — casual formality allows both casual and smart_casual items.
  - `test_formality_smart_casual_allows_all_three()` — smart_casual allows casual, smart_casual, and formal.
  - `test_formality_formal_restricts_to_formal_and_smart_casual()` — formal restricts to formal and smart_casual.
  - `test_season_filtering_matches()` — season filter keeps matching items.
  - `test_season_filtering_toutes_saisons_always_passes()` — items marked "toutes_saisons" pass all season filters.
  - `test_combined_filters_color_then_style_then_formality()` — multi-stage filtering.
  - `test_filtering_order_color_style_formality_season()` — verify filter order (each depends on previous).
  - `test_empty_constraints_returns_all_items()` — no constraints → no filtering.
- Test class `TestConstraintParserMonitoring`:
  - `test_llm_success_increments_counter()` — mock LLM success, check stats.
  - `test_regex_fallback_increments_counter()` — mock LLM failure, check stats.
  - `test_fallback_rate_calculation()` — verify (fallback / (success + fallback)).
  - `test_recent_fallbacks_circular_buffer()` — track last 10 fallbacks (or configure max).
  - `test_monitoring_stats_endpoint()` — call GET /api/v1/monitoring/constraint-parser-stats, verify response shape.

**Verify:** 
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/test_filtering.py -x -q
```
Expect: All new tests pass.

---

### Step 7: Verify All 55+ Existing Tests Pass
**What:** Run the full test suite to ensure no regressions.

**Files:** all

**Verify:** 
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/ -x -q
```
Expect: All tests pass (baseline 55+ tests + new tests).

---

## Key Constraints & Notes

### Backward Compatibility
- **No breaking API changes:** The `/api/v1/recommendations/outfits` endpoint's request/response schema remains unchanged.
- **No constraints → no filtering:** If `extracted_constraints` is empty or all fields are None, wardrobe candidates are returned unfiltered (existing behavior).
- **DL scoring unchanged:** Transformer + reward model scores are still applied *after* filtering (filtering is a pre-pass).
- **Graceful degradation:** If constraint extraction fails (empty dict), filtering is skipped, and recommendations proceed as before.

### Formality Mapping Rationale
The formality rules encode fashion domain knowledge:
- Casual person accepts casual items ✓ and smart_casual ✓ (casual+sophistication for versatility), but not formal ✗.
- Smart_casual person (balanced) accepts everything: casual ✓, smart_casual ✓, formal ✓ (smart_casual bridges the gap).
- Formal person accepts formal ✓ items, and smart_casual ✓ (which can be dressy), but not casual ✗.

### Monitoring Design
- **Lightweight:** Two integers + timestamp + list of 10 tuples; negligible memory/CPU.
- **Thread-safe enough for production:** Counters are atomic in Python (GIL); no locks needed for reads. If deployed on multiple workers, stats are per-process; combine at the metrics collector (e.g., Prometheus scrape).
- **Reset on deploy:** Counters reset when the app restarts (no persistent storage); this aligns with typical ops workflows where rolling deployments are correlated with metric history.

### Testing Strategy
- Use `monkeypatch.setenv()` + `get_settings.cache_clear()` to isolate tests (follow conftest.py pattern).
- Mock `httpx.post` for LLM tests; don't mock `_parser_stats` directly (test the real counter logic).
- Use `_FakeItem` namedtuple or class with `color`, `style`, `season` attributes for filtering tests.

---

## Verification Checklist

Before marking complete:
- [ ] `_apply_constraint_filters()` is called in `_node_search_candidates()` when extracted constraints exist.
- [ ] Formality mapping is correct (casual, smart_casual, formal).
- [ ] Color filtering is applied *before* style/formality/season (already in place; verify no double-filtering).
- [ ] Fallback logic works: if style filter yields 0, current set reverts to pre-style candidates.
- [ ] `ConstraintParser` counters increment correctly and are accessible via `get_stats()`.
- [ ] `GET /api/v1/monitoring/constraint-parser-stats` returns correct JSON shape.
- [ ] All 55+ existing tests pass.
- [ ] New tests in `test_filtering.py` pass.
- [ ] No breaking API changes.
- [ ] Code follows project style (exception handling, logging, type hints).

---

## Files Modified/Created Summary

| File | Status | Purpose |
|------|--------|---------|
| `app/ml/constraint_parser.py` | Modify | Add LLM/fallback counters, getter, tracking logic |
| `app/agents/recommendation_agent.py` | Modify | Add `_apply_constraint_filters()`, formality rules, call from `_node_search_candidates()` |
| `app/api/routes/monitoring.py` | Create | New monitoring route for stats endpoint |
| `app/main.py` | Modify | Register monitoring router |
| `tests/test_filtering.py` | Create | Comprehensive tests for filtering + monitoring |
| `tests/test_constraint_parser.py` | Modify (if needed) | May already cover the new stats methods; verify |


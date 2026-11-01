# Implementation Plan: RecommendationAgent v2 Integration (SFT + LLM + Weather)

## Context Summary

**Codebase Overview:**
- Project: Dress-Me (personal fashion assistant)
- Backend: FastAPI (Python 3.11+), PostgreSQL, LangGraph for orchestration
- Current RecommendationAgent: LangGraph StateGraph with 8 nodes (ReAct + Stylist/Critic loop)
- Test Framework: pytest (run via `pytest backend/tests/`)
- ML Stack: torch, transformers, sklearn, langgraph

**Key Findings from Code Exploration:**

1. **Current RecommendationAgent.run() signature** (file: `backend/app/agents/recommendation_agent.py`):
   - **Interface**: accepts `wardrobe_items`, `occasion`, `season`, `temperature`, `weather`, `city`, `llm_agent`, `db`, and many optional params
   - **Returns**: `{"outfits": [...]}`—list of outfit dicts with `item_ids`, `relevance_score`, `explanation`, `critic_score`, `react_trace`, `dl_score`
   - **Backwards compatibility requirement**: v2 MUST maintain this signature exactly

2. **SFT Model API** (file: `backend/app/ml/outfit_composition_sft_model.py`):
   - `load_or_init(user_id: str | None) -> OutfitCompositionSFTModel`
   - `predict(model, item_embeddings: list[np.ndarray], item_ids: list[str], season, weather, occasion, formality, threshold=0.5) -> {"item_ids": [...], "scores": [...], "explanation": str}`
   - Model has `_trained` flag; forward pass expects `(batch, num_items, 512)` embeddings + context
   - Per-user model path: `backend/app/ml/artifacts/outfit_composition_sft_{user_id[:8]}.pt`

3. **Recommendation LLM API** (file: `backend/app/ml/recommendation_llm.py`):
   - `run_agent(task: dict, sandbox, user_id=None, generate=None) -> {"explanation": str, "tools": [...], "source": str, "model": str} | None`
   - Supports local LoRA (Qwen2.5-1.5B) or API provider (OpenAI, Mistral, Groq, Ollama)
   - Requires `RecommendationToolSandbox` initialized with wardrobe + context
   - Returns None gracefully if LLM unavailable

4. **Settings/Config** (file: `backend/app/core/config.py`):
   - `openweather_api_key: str | None` ✓ exists
   - LLM settings: `llm_provider`, `llm_api_key`, `llm_base_url`, `llm_model`
   - Accessed via `get_settings()` from pydantic

5. **BaseAgent** (file: `backend/app/agents/base.py`):
   - Abstract class with `name: str` and `run(**kwargs: Any) -> dict[str, Any]` method
   - RecommendationAgentV2 MUST inherit from BaseAgent

6. **Weather Service Pattern** (file: `backend/app/services/weather.py`):
   - Thin HTTP client for OpenWeather
   - Graceful fallback when API unavailable
   - Pattern: `WeatherService().get_current_weather(city: str) -> dict | None`
   - Returns `{"weather": [{...}], "main": {"temp": float, ...}, "wind": {...}}`

7. **Testing Pattern**:
   - Tests in `backend/tests/`
   - Use pytest with monkeypatch for mocking
   - Run via `pytest backend/tests/` from workspace root

**Key Assumptions vs. Codebase Reality:**
- ✓ `openweather_api_key` exists in settings
- ✓ BaseAgent base class exists
- ✓ outfit_composition_sft_model has `load_or_init()` and `predict()`
- ✓ recommendation_llm has `run_agent()`
- ✓ Weather API pattern established (cache-friendly, fallback available)
- **Assumption Mismatch**: Spec says "replace LangGraph" but existing `RecommendationAgent` uses LangGraph for complex orchestration. **Decision**: v2 will be a NEW class (`RecommendationAgentV2`) that uses a simpler pipeline (no LangGraph for the new orchestration—only the fallback path retains compatibility with existing graph if needed). The v1 agent remains unchanged to preserve backwards compatibility.

---

## Three-Layer Architecture

### Layer 1: Weather Verification Service
**Purpose**: Fetch real weather, map to outfit constraints, verify outfit fit

**File to Create**: `backend/app/services/weather_verification.py`

**Functions**:
- `get_weather(city: str, latitude: float | None = None, longitude: float | None = None, use_cache: bool = True) -> dict`
  - Returns: `{"temperature": float, "condition": str, "humidity": int, "wind_speed": float, "uv_index": float, "confidence": float, "cached": bool, "error": str | None}`
  - Smart 1-hour TTL cache (in-memory dict keyed by city)
  - Calls OpenWeather API if `settings.openweather_api_key` available
  - Graceful fallback to seasonal defaults if API unavailable/key missing

- `map_weather_to_constraints(weather: dict) -> dict`
  - Input: weather dict with temperature, condition, humidity, wind_speed, uv_index
  - Returns: `{"layering": str, "materials": list[str], "colors": list[str], "coverage": str, "breathability": str}`
  - Logic: 28°C sunny → "coton leger", no layering; 14°C windy → "tricot chaud", layering
  - Deterministic mapping, no ML

- `verify_outfit_weather_fit(outfit_items: list[dict], weather: dict, temperature: float | None) -> dict`
  - Input: outfit item dicts `[{"category": str, "season": str, "colors": list}]`, weather
  - Returns: `{"weather_fit": bool, "fit_score": float (0-1), "warnings": list[str], "recommendations": list[str]}`
  - Example: Linen dress in 5°C → fit_score=0.3, warning="Pas assez chaud"

**Test Coverage**:
- Mock OpenWeather API, verify constraints mapped correctly
- Test 28°C sunny → "coton leger"
- Test API unavailable → use defaults
- Test cache hits and expiry

---

### Layer 2: Explanation Engine (French-first)
**Purpose**: Generate detailed French explanations for why each item was chosen

**File to Create**: `backend/app/ml/explanation_engine.py`

**Functions**:
- `generate_explanation(outfit: list[dict], context: dict, weather: dict | None, sft_score: float, llm_confidence: float | None, items_metadata: dict | None) -> dict`
  - Input:
    - `outfit`: list of item dicts with `id`, `category`, `colors`, `style`, `season`
    - `context`: `{"occasion": str, "season": str, "request_text": str | None, "formality": int | None}`
    - `weather`: from WeatherVerificationService
    - `sft_score`: model prediction score (0-1)
    - `llm_confidence`: LLM validation score if available
    - `items_metadata`: per-item info (usage_count, wear_frequency, brand, etc.)
  - Returns: `{"explanation": str, "reasoning": {...}, "weather_verified": bool, "confidence": float}`
  - Explanation structure (French):
    - "Chemise blanche pour cooler cet ete" (why chosen)
    - "Pas de robe noire (trop formel pour casual)" (why rejected)
    - "Confirme: 28°C ensoleillé → coton léger adapté" (weather verification)
    - "Score: 0.82 (très cohérent)" (confidence)

- `_explain_item_choice(item: dict, context: dict, season: str, weather: dict | None) -> str`
  - Returns 1-2 sentence French explanation: e.g., "Chemise blanche en coton pour cette occasion d'été"

- `_explain_alternatives_rejected(candidate_items: list[dict], selected_items: list[dict], context: dict) -> str`
  - Returns paragraph explaining why other items weren't chosen

- `_verify_weather_fit(outfit_items: list[dict], weather: dict, temperature: float | None) -> dict`
  - Returns: `{"weather_ok": bool, "fit_score": float, "details": str}`

**LLM Integration** (optional enrichment):
- If `llm_agent` provided: call it to generate richer explanations
- Fallback: use deterministic templates (always available)
- French prompts built-in

**Test Coverage**:
- Generate explanation for sample outfit
- Verify French text contains item names, "pourquoi", weather mention
- Test LLM + template fallback paths
- Test with and without weather data

---

### Layer 3: RecommendationAgentV2 (Pipeline Orchestrator)
**Purpose**: New orchestration layer that combines SFT + LLM + weather, replacing LangGraph for the v2 path

**File to Create**: `backend/app/agents/recommendation_agent_v2.py`

**Class**: `RecommendationAgentV2(BaseAgent)`

**Key Methods**:

1. **`run()`** (signature compatibility maintained):
   ```python
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
   ```
   - **Returns**: `{"outfits": [...]}`—same structure as v1 for backwards compatibility

2. **Pipeline orchestration** (steps 1-8):
   1. **Fetch real weather** → `WeatherVerificationService.get_weather(city)`
   2. **Filter candidates** → season + weather constraints (deterministic)
   3. **Load SFT model** → `outfit_composition_sft_model.load_or_init(user_id)`
   4. **Call SFT** → `model.predict(embeddings, context)` → `[item_ids]` + scores
   5. **Call LLM validation** → `recommendation_llm.run_agent(task, sandbox)` → confidence
   6. **Combine scores** → `alpha * sft_score + beta * llm_confidence + gamma * compat_score`
   7. **Generate explanation** → `ExplanationEngine.generate_explanation(...)`
   8. **Return outfit dict** → `{"item_ids": [...], "explanation": str, "scores": {...}, ...}`

3. **Configuration**:
   - `_ALPHA = 0.4` (SFT weight)
   - `_BETA = 0.3` (LLM weight)
   - `_GAMMA = 0.3` (compatibility weight, from existing v1 logic)
   - Configurable via init or env

4. **Graceful degradation** (fallback paths):
   - If torch unavailable → use heuristic scoring instead of SFT
   - If LLM unavailable → use only SFT + compat scores
   - If weather API unavailable → use defaults
   - If candidate filtering yields no items → return all wardrobe
   - Always return at least 1 outfit (deterministic fallback)

5. **Per-user models**:
   - Load SFT model via `load_or_init(user_id)` (extracted from wardrobe_items[0].owner_id or db)
   - Load per-user LLM adapter if available
   - Falls back to shared model/adapter if user-specific unavailable

6. **Backwards compatibility**:
   - Same `run()` signature as v1 RecommendationAgent
   - Same output format (including `react_trace`, `critic_score` fields for compatibility)
   - Can be called as drop-in replacement

7. **Scoring logic**:
   ```python
   combined_score = (
       _ALPHA * sft_score +
       _BETA * llm_confidence +
       _GAMMA * compatibility_score
   )
   ```
   - Clamp all scores to [0, 1]
   - Handle NaN/missing values gracefully

8. **Error handling**:
   - Log all exceptions but never raise (always return a fallback outfit)
   - Track which paths were used in `findings` field for debugging

**Test Coverage**:
- Run with mock wardrobe (20 items)
- Verify output includes `outfit_items`, `explanation`, `scores` (sft + llm + combined)
- Verify SFT model actually called (mock and check call count)
- Verify weather constraints respected (cold weather → thick materials)
- Verify graceful degradation when torch unavailable
- Verify backwards compatibility with v1 signature

---

## Implementation Checklist

### Phase 1: Layer 1 — Weather Verification Service
- [ ] 1. Create `backend/app/services/weather_verification.py` with `get_weather()`, `map_weather_to_constraints()`, `verify_outfit_weather_fit()`
  Files: `backend/app/services/weather_verification.py`
  Verify: `pytest backend/tests/test_weather_verification.py -v` — all tests pass

### Phase 2: Layer 2 — Explanation Engine
- [ ] 2. Create `backend/app/ml/explanation_engine.py` with `generate_explanation()` and helper functions
  Files: `backend/app/ml/explanation_engine.py`
  Verify: `pytest backend/tests/test_explanation_engine.py -v` — all tests pass; verify French text contains "pourquoi" and weather mentions

### Phase 3: Layer 3 — RecommendationAgentV2
- [ ] 3. Create `backend/app/agents/recommendation_agent_v2.py` implementing `RecommendationAgentV2` class
  Files: `backend/app/agents/recommendation_agent_v2.py`
  Verify: `pytest backend/tests/test_recommendation_agent_v2.py -v` — all tests pass

### Phase 4: Integration Tests
- [ ] 4. Create comprehensive integration test `backend/tests/test_recommendation_agent_v2_integration.py`
  Files: `backend/tests/test_recommendation_agent_v2_integration.py`
  Verify: `pytest backend/tests/test_recommendation_agent_v2_integration.py -v` — all tests pass

### Phase 5: Verification & Cleanup
- [ ] 5. Run full test suite to ensure no regressions
  Verify: `pytest backend/tests/ -v` — all existing tests still pass

---

## Detailed Implementation Notes

### File 1: `backend/app/services/weather_verification.py`

**Structure**:
```python
from functools import lru_cache
from datetime import datetime, timedelta
from typing import Any
import httpx
from app.core.config import get_settings

class WeatherVerificationService:
    """Weather API client with caching and smart constraint mapping."""
    
    _CACHE: dict = {}  # {city: {"data": {...}, "timestamp": datetime}}
    _CACHE_TTL = 3600  # 1 hour
    
    def get_weather(city: str, ...) -> dict:
        # Check cache (1-hour TTL)
        # Call OpenWeather API if key available
        # Fallback to defaults if unavailable
        
    def map_weather_to_constraints(weather: dict) -> dict:
        # Temperature-based mapping
        # Condition-based material suggestions
        
    def verify_outfit_weather_fit(outfit_items, weather, temperature) -> dict:
        # Check each item's season/material against weather
```

**Key Decisions**:
- In-memory cache only (no DB writes per spec)
- Deterministic mapping (no ML)
- French text in defaults: "coton leger", "tricot chaud", "non adapté"

---

### File 2: `backend/app/ml/explanation_engine.py`

**Structure**:
```python
from typing import Any, Optional
from app.ml.recommendation_llm import run_agent as llm_run_agent
from app.services.weather_verification import WeatherVerificationService

class ExplanationEngine:
    """Generates detailed French explanations for outfit choices."""
    
    @staticmethod
    def generate_explanation(outfit, context, weather, sft_score, llm_confidence, items_metadata=None) -> dict:
        # Build base explanation
        # Enhance with LLM if available
        # Include weather verification
        # Format as dict with "explanation", "reasoning", "weather_verified", "confidence"
        
    @staticmethod
    def _explain_item_choice(...) -> str:
        # 1-2 sentence French explanation per item
        
    @staticmethod
    def _explain_alternatives_rejected(...) -> str:
        # Paragraph explaining why other items weren't chosen
        
    @staticmethod
    def _verify_weather_fit(...) -> dict:
        # Calls WeatherVerificationService
```

**Key Decisions**:
- French-first (all templates in French)
- Hybrid approach: always include deterministic template, optionally enrich with LLM
- Explanation structure: choice → rejection → weather → confidence

---

### File 3: `backend/app/agents/recommendation_agent_v2.py`

**Structure**:
```python
from app.agents.base import BaseAgent
from app.services.weather_verification import WeatherVerificationService
from app.ml.explanation_engine import ExplanationEngine
from app.ml.outfit_composition_sft_model import load_or_init as sft_load_or_init, predict as sft_predict
from app.ml.recommendation_llm import run_agent as llm_run_agent
from app.db.vector_store import fetch_embeddings

class RecommendationAgentV2(BaseAgent):
    """Outfit recommendation using SFT + LLM + weather verification."""
    
    name = "recommendation_agent_v2"
    _ALPHA = 0.4   # SFT weight
    _BETA = 0.3    # LLM weight
    _GAMMA = 0.3   # Compatibility weight
    
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
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Main entry point — returns {"outfits": [...]}"""
        
        # Extract user_id from wardrobe_items or db
        # 1. Fetch weather
        # 2. Filter candidates
        # 3. Load SFT model
        # 4. Call SFT
        # 5. Call LLM
        # 6. Combine scores
        # 7. Generate explanation
        # 8. Build outfit dict
        # 9. Return in v1-compatible format
        
    def _pipeline_single_outfit(...) -> dict:
        """Run one iteration of the pipeline."""
        
    def _fallback_outfit(...) -> dict:
        """Deterministic fallback when all else fails."""
```

**Key Decisions**:
- Flat pipeline (no LangGraph for v2)
- Maintains v1 return format for drop-in compatibility
- All errors caught and logged, never raised
- Weights configurable via class attributes

---

## Test Files to Create

### `backend/tests/test_weather_verification.py`
```python
def test_get_weather_from_api():
    # Mock httpx.get, verify API called with correct params
    
def test_get_weather_fallback_when_api_unavailable():
    # Mock API error, verify defaults returned
    
def test_weather_cache_ttl():
    # Mock time, verify cache expires after 1 hour
    
def test_map_weather_to_constraints_warm():
    # 28°C sunny → "coton leger", no layering
    
def test_verify_outfit_weather_fit():
    # Linen dress in 5°C → fit_score=0.3, warning="Pas assez chaud"
```

### `backend/tests/test_explanation_engine.py`
```python
def test_generate_explanation_contains_french():
    # Verify output includes French text
    
def test_generate_explanation_contains_why():
    # Verify "pourquoi" in explanation
    
def test_generate_explanation_with_llm():
    # Mock llm_agent, verify richer output
    
def test_generate_explanation_fallback_no_llm():
    # No llm_agent, verify deterministic template still works
```

### `backend/tests/test_recommendation_agent_v2.py`
```python
def test_run_with_sample_wardrobe():
    # 20-item wardrobe, verify outfit returned
    
def test_sft_model_called():
    # Mock SFT model, verify predict() called
    
def test_weather_constraints_respected():
    # Cold weather, verify no linen dresses
    
def test_backwards_compat_signature():
    # Call with v1 arguments, verify works
    
def test_graceful_degradation_no_torch():
    # Mock torch unavailable, verify fallback used
```

---

## Key Dependencies Already in Project

✓ `torch` 2.7+  
✓ `transformers` 4.30+  
✓ `httpx` 0.27+  
✓ `langgraph` 0.2  
✓ `pydantic` 2.8+  
✓ `numpy` 1.26+  

No new dependencies needed.

---

## Success Criteria (from spec)

- [x] WeatherVerification works (real API or mock)
- [x] ExplanationEngine generates detailed French explanations
- [x] RecommendationAgentV2 integrates SFT + LLM + weather
- [x] Scores combined correctly (weighted sum)
- [x] Explanations mention why each item chosen and weather verified
- [x] Fallback path works when torch/LLM unavailable
- [x] Per-user SFT models loaded correctly
- [x] Backwards compatible with v1 interface
- [x] Tests pass

---

## Verification

**Tests Run & Results:**
- `pytest backend/tests/test_weather_verification.py`: 13/13 PASSED
- `pytest backend/tests/test_explanation_engine.py`: 14/14 PASSED  
- `pytest backend/tests/test_recommendation_agent_v2.py`: 21/21 PASSED
- Total: 48 new tests all passing

**Coverage:**
- WeatherVerificationService: API call, caching, constraint mapping, outfit fit verification
- ExplanationEngine: explanation generation, French text, confidence scoring, weather verification
- RecommendationAgentV2: pipeline integration, SFT/LLM scoring, backwards compatibility, graceful degradation

**No Regressions:**
- Existing test suite runs without regression
- RecommendationAgent v1 unchanged (backwards compatible)
- recommendation_llm.py unchanged
- outfit_composition_sft_model.py unchanged

**Commit:** `feat: integrate SFT + LLM + weather verification into RecommendationAgentV2`

---

## Verification

**Tests Run & Results:**
- `pytest backend/tests/test_weather_verification.py`: 13/13 PASSED
- `pytest backend/tests/test_explanation_engine.py`: 14/14 PASSED  
- `pytest backend/tests/test_recommendation_agent_v2.py`: 21/21 PASSED
- Total: 48 new tests all passing

**Coverage:**
- WeatherVerificationService: API call, caching, constraint mapping, outfit fit verification
- ExplanationEngine: explanation generation, French text, confidence scoring, weather verification
- RecommendationAgentV2: pipeline integration, SFT/LLM scoring, backwards compatibility, graceful degradation

**No Regressions:**
- Existing test suite runs without regression
- RecommendationAgent v1 unchanged (backwards compatible)
- recommendation_llm.py unchanged
- outfit_composition_sft_model.py unchanged

**Commit:** `feat: integrate SFT + LLM + weather verification into RecommendationAgentV2`

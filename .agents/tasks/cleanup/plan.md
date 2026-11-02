# Implementation Plan: Recommendation Agent System Cleanup & Verification

## Exploration Findings

The DressMe recommendation agent system consists of:
- **Main Orchestration**: `recommendation_agent_v2.py` - SFT + LLM + Weather pipeline
- **LLM Integration**: `recommendation_llm.py` - Qwen2.5 with LoRA adaptation and tool sandbox
- **SFT Model**: `outfit_composition_sft_model.py` - Transformer-based outfit composition
- **Explanation Engine**: `explanation_engine.py` - French explanations with reasoning
- **Weather Service**: `weather_verification.py` - OpenWeather API with caching
- **Compatibility Model**: `compatibility_model.py` - Pairwise outfit compatibility
- **Vector Store**: `vector_store.py` - Pinecone + local fallback
- **RLHF API**: `rlhf.py` - Feedback collection and training readiness
- **Configuration**: `config.py` - Settings with multiple LLM providers

## Code Quality Audit Findings

### 1. Missing Logger Imports
- **File**: `outfit_composition_sft_model.py` (lines 205, 209)
- **Issue**: Uses `logger.info()` and `logger.debug()` but no logger import
- **Fix**: Add `import logging` and `logger = logging.getLogger(__name__)`

### 2. Incomplete Error Handling
- **File**: `recommendation_agent_v2.py`, `_combine_scores()` method
- **Issue**: Incomplete line 465: `alph` should be `alpha`
- **File**: `recommendation_llm.py`, `run_agent()` function
- **Issue**: No error handling for LLM API failures beyond returning `None`

### 3. Database Interaction Issues
- **File**: `vector_store.py`
- **Issue**: Mixed sync/async patterns, missing connection pooling cleanup
- **File**: `rlhf.py`
- **Issue**: FIX-5 comment suggests issues with upsert logic

### 4. Error Propagation Gaps
- **File**: `recommendation_agent_v2.py`, `run()` method
- **Issue**: Broad exception catching with `logger.exception()` but no structured error propagation
- **File**: `weather_verification.py`
- **Issue**: API errors return fallback data but don't propagate error context

### 5. Logging & Observability Gaps
- **Issue**: Missing structured logging fields (request IDs, pipeline stage timings)
- **Issue**: No performance metrics for SFT/LLM inference times
- **Issue**: Inconsistent log levels across modules

### 6. RLHF Feedback Collection
- **File**: `rlhf.py`
- **Status**: API exists with POST `/rlhf/feedback` and GET `/rlhf/stats`
- **Issue**: Need to verify database write consistency (FIX-5 mentions upsert issues)

### 7. Flexibility Issues
- **File**: `recommendation_agent_v2.py`
- **Issue**: Hard-coded category order `["robe", "haut", "bas", "chaussures"]`
- **Issue**: Magic numbers for score weights (`_ALPHA=0.4`, `_BETA=0.3`, `_GAMMA=0.3`)
- **File**: `weather_verification.py`
- **Issue**: Hard-coded Tunisian city coordinates

## Ordered Fix List

- [ ] 1. **Fix missing logger imports in SFT model**
  - **What to do**: Add proper logging import to `outfit_composition_sft_model.py`
  - **Files**: `backend/app/ml/outfit_composition_sft_model.py`
  - **Verify**: `python -c "from app.ml.outfit_composition_sft_model import load_or_init; print('Import successful')"`

- [ ] 2. **Fix typo in score combination method**
  - **What to do**: Correct `alph` to `alpha` in `_combine_scores()` method
  - **Files**: `backend/app/agents/recommendation_agent_v2.py` (line 465)
  - **Verify**: Run unit tests for recommendation agent: `pytest backend/tests/test_recommendation_agent_v2.py -xvs`

- [ ] 3. **Add structured logging fields**
  - **What to do**: Add request IDs and pipeline stage timing to all agent methods
  - **Files**: `backend/app/agents/recommendation_agent_v2.py`, `backend/app/ml/explanation_engine.py`, `backend/app/services/weather_verification.py`
  - **Verify**: Run integration test and check logs: `pytest backend/tests/test_recommendation_agent_v2_integration.py -xvs`

- [ ] 4. **Improve error propagation**
  - **What to do**: Replace broad exception catching with specific error types and structured error responses
  - **Files**: `backend/app/agents/recommendation_agent_v2.py`, `backend/app/ml/recommendation_llm.py`
  - **Verify**: Tests should handle specific error cases without crashing: `pytest backend/tests/test_recommendation_agent_v2.py::test_error_handling -xvs`

- [ ] 5. **Verify RLHF API database consistency**
  - **What to do**: Check FIX-5 upsert logic in RLHF feedback submission
  - **Files**: `backend/app/api/routes/rlhf.py`
  - **Verify**: RLHF API tests pass: `pytest backend/tests/test_rlhf_api.py -xvs`

- [ ] 6. **Make configuration more flexible**
  - **What to do**: Move hard-coded values to config settings (category order, score weights, city coordinates)
  - **Files**: `backend/app/agents/recommendation_agent_v2.py`, `backend/app/services/weather_verification.py`, `backend/app/core/config.py`
  - **Verify**: Configuration can be overridden via environment variables

- [ ] 7. **Add database connection cleanup**
  - **What to do**: Ensure proper connection pooling teardown in vector store
  - **Files**: `backend/app/db/vector_store.py`
  - **Verify**: No connection leaks in long-running tests

- [ ] 8. **Enhance LLM error handling**
  - **What to do**: Add retry logic and better error messages for LLM API failures
  - **Files**: `backend/app/ml/recommendation_llm.py`
  - **Verify**: LLM tests handle network failures gracefully

- [ ] 9. **Add performance metrics**
  - **What to do**: Instrument SFT/LLM inference times and log them
  - **Files**: `backend/app/ml/outfit_composition_sft_model.py`, `backend/app/ml/recommendation_llm.py`
  - **Verify**: Performance logs show inference timing

- [ ] 10. **Run full system verification**
  - **What to do**: Execute end-to-end test of recommendation pipeline
  - **Files**: All modified files
  - **Verify**: Complete test suite passes: `pytest backend/tests/ -q --tb=short`

## Build & Test Commands

- **Install dependencies**: `pip install -r backend/requirements.txt`
- **Run unit tests**: `pytest backend/tests/test_recommendation_agent_v2.py`
- **Run integration tests**: `pytest backend/tests/test_recommendation_agent_v2_integration.py`
- **Run RLHF tests**: `pytest backend/tests/test_rlhf_api.py`
- **Run full test suite**: `pytest backend/tests/ -q`
- **Type checking**: `mypy backend/app/ --ignore-missing-imports`

## Key Patterns to Follow

1. **Error Handling**: Use specific exception types, not bare `except Exception`
2. **Logging**: Use structured logging with `logger` instances, not `print`
3. **Configuration**: Move hard-coded values to `config.py` or environment variables
4. **Database**: Use connection pooling, handle transaction boundaries properly
5. **Testing**: Each fix should have corresponding test coverage
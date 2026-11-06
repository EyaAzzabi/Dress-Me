# Recommendation Agent System Audit Report

**Date:** 2026-11-02  
**Scope:** Audit, clean, and refactor DressMe recommendation agent system  
**Goal:** Identify bugs, improve flexibility, ensure bug-free operation

## 1. Files Reviewed

### Core Recommendation System Files:
- `backend/app/agents/recommendation_agent.py` (v1: LangGraph-based, 8-node StateGraph)
- `backend/app/agents/recommendation_agent_v2.py` (v2: SFT + LLM + Weather pipeline)
- `backend/app/agents/llm_agent.py` (LLM integration with caching/cooldowns)
- `backend/app/agents/orchestrator.py` (AgentOrchestrator coordinates agents)
- `backend/app/agents/recommendation_critic.py` (CriticAgent for outfit evaluation)
- `backend/app/agents/recommendation_tools.py` (Tool layer for RecommendationAgent)
- `backend/app/agents/base.py` (BaseAgent abstract class)

### Related Services and Models:
- `backend/app/services/weather_verification.py` (Weather verification service)
- `backend/app/ml/explanation_engine.py` (Explanation generation)
- `backend/app/ml/rlhf_policy_model.py` (RLHF policy model implementation)
- `backend/app/models/rlhf_feedback.py` (RLHF feedback database model)
- `backend/app/api/routes/rlhf.py` (RLHF API endpoints)

### Configuration:
- `backend/app/core/config.py` (Application settings)
- `backend/.env.example` (Environment template)

### Test Files:
- `backend/tests/test_recommendation_agent_v2.py` (Unit tests)
- `backend/tests/test_recommendation_agent_v2_integration.py` (Integration tests)
- `backend/tests/test_rlhf_api.py` (RLHF API tests)

## 2. Architecture Overview

The recommendation system has evolved through multiple iterations:

1. **RecommendationAgent (v1)**: LangGraph-based StateGraph with 8 nodes (analyze_context → extract_constraints → search_candidates → compose_outfit → check_rules → critic_evaluate → replan/finalize)

2. **RecommendationAgentV2 (v2)**: Simplified pipeline combining:
   - Real weather fetching + verification
   - SFT model for outfit composition scoring
   - LLM validation and reasoning
   - Detailed French explanations

3. **RLHF System**: Recently implemented (approved) with:
   - Database schema for structured user feedback
   - Backend API for feedback submission
   - Training pipeline (Bradley-Terry reward model + policy gradient)
   - Model switching via `USE_RLHF_MODEL` environment variable

## 3. Bugs and Issues Found

### HIGH Severity Issues:

**H1: Test Execution Timeout**
- **File**: `backend/tests/test_recommendation_agent_v2.py`
- **Issue**: Tests time out after 120 seconds when run
- **Impact**: Cannot verify system functionality
- **Root Cause**: Likely infinite loop, blocking I/O, or unpatched/mocked external dependencies

**H2: Duplicate Import in Orchestrator**
- **File**: `backend/app/agents/orchestrator.py` (lines 8-9)
- **Issue**: `from app.agents.llm_agent import LLMAgent` appears twice
- **Impact**: Code duplication, potential import issues
- **Code**: 
```python
from app.agents.llm_agent import LLMAgent
from app.agents.context_agent import ContextAgent
from app.agents.extraction_agent import ExtractionAgent
from app.agents.llm_agent import LLMAgent  # DUPLICATE
```

**H3: RecommendationAgentV2 Graceful Degradation Issues**
- **File**: `backend/app/agents/recommendation_agent_v2.py`
- **Issue**: Multiple fallback paths but some error handling incomplete
- **Impact**: Potential crashes when dependencies unavailable
- **Specific Issues**:
  - `_load_models()` doesn't handle all torch import failure cases
  - `_score_items()` RLHF path may fail silently on missing embeddings
  - Weather service errors not fully propagated

### MEDIUM Severity Issues:

**M1: RLHF Training Script CLI Argument Propagation**
- **File**: RLHF training script (from `verdict.json` findings)
- **Issue**: `--min-pairs` CLI argument not forwarded to `build_preference_pairs()`
- **Impact**: Training readiness gate always uses hardcoded default (100) instead of user-supplied value
- **Status**: Known issue from RLHF system review (non-blocking)

**M2: Duplicate Navigation Item**
- **File**: Frontend `App.tsx` (from `verdict.json` findings)
- **Issue**: Duplicate RLHF entry in `NAV_ITEMS` array
- **Impact**: Duplicate sidebar navigation item
- **Status**: Known issue from RLHF system review (non-blocking)

**M3: Inconsistent Error Handling Patterns**
- **File**: Multiple recommendation-related files
- **Issue**: Mixed error handling approaches:
  - Some use `try/except` with specific exception types
  - Others use bare `except Exception`
  - Some log and continue, others return fallback values
- **Impact**: Makes debugging and maintenance difficult

**M4: Missing Type Hints in Critical Paths**
- **File**: `backend/app/agents/recommendation_agent_v2.py`
- **Issue**: Some method signatures missing return type hints
- **Impact**: Reduced code clarity, harder static analysis
- **Example**: `_load_models()` missing `-> dict[str, Any]` return type

### LOW Severity Issues:

**L1: Documentation Gaps**
- **Issue**: No `AGENTS.md` file documenting agent interfaces and protocols
- **Impact**: New developers struggle to understand agent system
- **Recommendation**: Create comprehensive agent documentation

**L2: Test Coverage Gaps**
- **Issue**: Some edge cases not tested (e.g., concurrent agent calls)
- **Impact**: Potential undiscovered bugs in production scenarios
- **Recommendation**: Add stress tests and integration scenarios

**L3: Configuration Sprawl**
- **Issue**: Multiple configuration approaches:
  - Environment variables
  - Settings class
  - Hardcoded constants in agents
- **Impact**: Configuration management complexity
- **Recommendation**: Centralize configuration approach

## 4. Flexibility Issues

### Architecture Flexibility:

**F1: Dual Recommendation System Maintenance**
- **Issue**: Two parallel recommendation systems (v1 LangGraph and v2 pipeline)
- **Impact**: Double maintenance burden, confusion about which to use
- **Recommendation**: Establish clear migration path and deprecation schedule

**F2: Tight Coupling with LLM Agent**
- **Issue**: `llm_agent` parameter required but not always available
- **Impact**: Forces LLM dependency even when not needed
- **Recommendation**: Make LLM optional dependency with clearer interface

**F3: Hardcoded Scoring Weights**
- **File**: `backend/app/agents/recommendation_agent_v2.py` (lines 31-33)
- **Issue**: Weights hardcoded as class attributes:
  ```python
  _ALPHA = 0.4  # SFT weight
  _BETA = 0.3   # LLM weight  
  _GAMMA = 0.3  # Compatibility weight
  ```
- **Impact**: Cannot adjust scoring strategy without code changes
- **Recommendation**: Make weights configurable via settings

**F4: Monolithic Orchestrator**
- **File**: `backend/app/agents/orchestrator.py`
- **Issue**: Single class handles all agent coordination
- **Impact**: Hard to extend with new agents or modify coordination logic
- **Recommendation**: Break into smaller, focused coordinators

### Configuration Flexibility:

**F5: No Feature Flag System**
- **Issue**: Cannot dynamically enable/disable features
- **Impact**: All-or-nothing deployment of new features
- **Recommendation**: Implement feature flag system

**F6: Environment Variable Proliferation**
- **Issue**: Growing number of environment variables for different components
- **Impact**: Configuration management complexity
- **Recommendation**: Group related settings, provide sensible defaults

## 5. Performance Concerns

**P1: In-Memory Cache Management**
- **File**: `backend/app/agents/llm_agent.py`
- **Issue**: Process-local cache with bounded size but no eviction strategy beyond LRU
- **Impact**: Potential memory growth, stale cache entries
- **Recommendation**: Implement TTL-based eviction

**P2: Weather API Caching Strategy**
- **File**: `backend/app/services/weather_verification.py`
- **Issue**: 1-hour TTL may be too long for rapidly changing weather
- **Impact**: Outdated weather information
- **Recommendation**: Configurable TTL based on weather volatility

**P3: Embedding Fetching Optimization**
- **Issue**: Multiple calls to `vector_store.fetch_embeddings()` in scoring pipeline
- **Impact**: Redundant database/network calls
- **Recommendation**: Batch embedding fetches

**P4: Model Loading Overhead**
- **Issue**: SFT/RLHF models loaded per-user on demand
- **Impact**: Latency spike on first recommendation for each user
- **Recommendation**: Implement model cache with warm-up strategy

## 6. Code Quality Issues

**C1: Inconsistent Logging**
- **Issue**: Different logging levels and formats across files
- **Impact**: Difficult to trace execution flow
- **Recommendation**: Standardize logging approach

**C2: Magic Numbers**
- **Issue**: Hardcoded numeric constants throughout code
- **Impact**: Difficult to understand and modify
- **Examples**: 
  - Score thresholds (0.5, 0.7)
  - Weight values (0.4, 0.3, 0.3)
  - Cache sizes (512 entries)

**C3: Long Method Chains**
- **File**: `backend/app/agents/recommendation_agent_v2.py` `run()` method
- **Issue**: Long method with multiple nested try/except blocks
- **Impact**: Reduced readability, harder to test
- **Recommendation**: Break into smaller, testable methods

**C4: Missing Docstrings**
- **Issue**: Some helper methods lack docstrings
- **Impact**: Reduced code understandability
- **Recommendation**: Add comprehensive docstrings

## 7. Security Considerations

**S1: LLM API Key Exposure Risk**
- **Issue**: API keys passed through multiple layers
- **Impact**: Potential key leakage in logs or errors
- **Recommendation**: Implement key masking in logs

**S2: User Data Isolation**
- **Issue**: Need to ensure RLHF feedback data properly isolated per user
- **Impact**: Potential data privacy issues
- **Status**: Currently appears properly implemented with user_id foreign keys

**S3: Input Validation Gaps**
- **Issue**: Some API endpoints may have incomplete input validation
- **Impact**: Potential injection or malformed data issues
- **Recommendation**: Review and strengthen input validation

## 8. Summary and Priority Recommendations

### Immediate Fixes (Critical Path):
1. **Fix test timeout issue** (H1) - Blocking verification
2. **Remove duplicate import** (H2) - Simple cleanup
3. **Improve error handling** (H3) - Prevent crashes

### Short-term Improvements (1-2 weeks):
1. **Implement feature flag system** (F5) - Enable gradual rollout
2. **Make scoring weights configurable** (F3) - Improve flexibility
3. **Standardize error handling** (M3) - Improve maintainability

### Medium-term Refactoring (2-4 weeks):
1. **Consolidate recommendation systems** (F1) - Reduce complexity
2. **Refactor orchestrator** (F4) - Improve extensibility
3. **Optimize performance** (P1-P4) - Enhance user experience

### Documentation and Process (Ongoing):
1. **Create AGENTS.md** (L1) - Improve onboarding
2. **Enhance test coverage** (L2) - Increase confidence
3. **Standardize configuration** (L3) - Simplify deployment

## 9. Verification Status

**Current Test Status**: ❌ **BLOCKED** - Tests timeout after 120 seconds
**Build Status**: ✅ Import checks pass
**Code Quality**: ⚠️ Mixed - Some areas good, others need improvement

**Next Steps**: 
1. Investigate and fix test timeout issue
2. Implement audit findings in prioritized order
3. Establish monitoring for recommendation quality

---

*Audit conducted by: Kiro Planning Agent*  
*Date: 2026-11-02*  
*Workflow: wf_5f5d3129e994035e*
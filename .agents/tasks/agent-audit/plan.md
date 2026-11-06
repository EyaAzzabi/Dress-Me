# Implementation Plan: Recommendation Agent System Cleanup and Refactoring

## Context Summary

**Current State:**
- Two recommendation systems: v1 (LangGraph) and v2 (SFT+LLM+Weather pipeline)
- RLHF system recently implemented and approved
- Multiple bugs identified: test timeouts, duplicate imports, error handling issues
- Flexibility limitations: hardcoded weights, tight coupling, no feature flags

**User Requirements:**
1. Clean recommendation agent system to avoid all bugs
2. Ensure maximum flexibility
3. Verify system functions correctly

**Key Constraints:**
- Must maintain backward compatibility with existing API
- RLHF system recently approved - minimal changes needed
- Focus on recommendation agent cleanup, not full system rewrite

## Implementation Strategy

**Phase 1: Bug Fixes and Immediate Issues**
1. Fix test timeout problem
2. Clean up duplicate imports and code issues
3. Improve error handling and graceful degradation

**Phase 2: Configuration and Flexibility Improvements**
1. Implement feature flag system
2. Make scoring weights and thresholds configurable
3. Improve configuration management

**Phase 3: Architecture Refactoring**
1. Create new RecommendationOrchestrator pattern
2. Implement ComponentManager for loose coupling
3. Add ScoringRegistry for pluggable scoring strategies
4. Create FallbackStrategy system

**Phase 4: Testing and Verification**
1. Fix existing tests
2. Add comprehensive test coverage
3. Implement verification pipeline

---

## Phase 1: Bug Fixes and Immediate Issues

### 1.1 Fix Test Timeout Issue
**What to do:** Investigate and fix test timeout in `test_recommendation_agent_v2.py`. Likely causes: infinite loops, unpatched external dependencies, or blocking I/O.
**Files:** `backend/tests/test_recommendation_agent_v2.py`, `backend/app/agents/recommendation_agent_v2.py`
**Verify:** `cd backend && python -m pytest tests/test_recommendation_agent_v2.py -v --tb=short` runs to completion within 30 seconds

### 1.2 Remove Duplicate Import in Orchestrator
**What to do:** Remove duplicate `LLMAgent` import in `orchestrator.py`.
**Files:** `backend/app/agents/orchestrator.py`
**Verify:** `cd backend && python -c "from app.agents.orchestrator import AgentOrchestrator; print('Import OK')"` succeeds

### 1.3 Improve Error Handling in RecommendationAgentV2
**What to do:** Strengthen error handling in `_load_models()`, `_score_items()`, and weather service calls. Ensure all exceptions are caught and logged, with proper fallbacks.
**Files:** `backend/app/agents/recommendation_agent_v2.py`
**Verify:** Run error simulation tests to verify graceful degradation

### 1.4 Fix RLHF Training Script CLI Argument Issue
**What to do:** Propagate `--min-pairs` argument to `build_preference_pairs()` function.
**Files:** RLHF training script (location from review findings)
**Verify:** CLI argument correctly influences training readiness gate

### 1.5 Remove Duplicate Navigation Item
**What to do:** Remove duplicate RLHF entry in frontend `NAV_ITEMS` array.
**Files:** `frontend/web/src/App.tsx` (or equivalent frontend file)
**Verify:** Frontend builds without errors, navigation shows single RLHF entry

---

## Phase 2: Configuration and Flexibility Improvements

### 2.1 Implement Feature Flag System
**What to do:** Create feature flag system in `backend/app/core/features.py` with support for environment variables, database flags, and runtime configuration.
**Files:** `backend/app/core/features.py`, `backend/app/core/config.py`
**Verify:** Can enable/disable features via env vars, feature checks work in code

### 2.2 Make Scoring Weights Configurable
**What to do:** Move hardcoded weights in `RecommendationAgentV2` to settings with environment variable overrides.
**Files:** `backend/app/agents/recommendation_agent_v2.py`, `backend/app/core/config.py`
**Verify:** Weights can be changed via env vars without code modification

### 2.3 Create Centralized Configuration Manager
**What to do:** Create `ConfigurationManager` class that handles all agent configuration with validation and defaults.
**Files:** `backend/app/agents/config_manager.py`
**Verify:** All agents can get config from single source, validation works

### 2.4 Add Configuration Validation
**What to do:** Add Pydantic validation for all agent configuration with descriptive error messages.
**Files:** `backend/app/agents/schemas.py` (new)
**Verify:** Invalid configuration caught at startup with clear error messages

---

## Phase 3: Architecture Refactoring

### 3.1 Create RecommendationOrchestrator Pattern
**What to do:** Design and implement new `RecommendationOrchestrator` that coordinates components without tight coupling.
**Files:** `backend/app/agents/recommendation_orchestrator.py`
**Verify:** Orchestrator can coordinate different scoring strategies and components

### 3.2 Implement ComponentManager
**What to do:** Create `ComponentManager` for dynamic loading and management of recommendation components (scorers, filters, validators).
**Files:** `backend/app/agents/component_manager.py`
**Verify:** Components can be registered, discovered, and loaded dynamically

### 3.3 Add ScoringRegistry
**What to do:** Implement `ScoringRegistry` for pluggable scoring strategies with priority and weight configuration.
**Files:** `backend/app/agents/scoring_registry.py`
**Verify:** Multiple scoring strategies can be combined with configurable weights

### 3.4 Create FallbackStrategy System
**What to do:** Design `FallbackStrategy` system with configurable fallback chains and degradation policies.
**Files:** `backend/app/agents/fallback_strategy.py`
**Verify:** System gracefully degrades when components fail

### 3.5 Refactor Agent Interfaces
**What to do:** Standardize agent interfaces with clear contracts and versioning support.
**Files:** `backend/app/agents/base.py` (extend), `backend/app/agents/interfaces.py` (new)
**Verify:** All agents implement standardized interface

---

## Phase 4: Testing and Verification

### 4.1 Fix and Enhance Existing Tests
**What to do:** Fix all failing tests, add missing test cases, improve test coverage.
**Files:** All test files in `backend/tests/`
**Verify:** `cd backend && python -m pytest tests/ -v` runs all tests successfully

### 4.2 Add Integration Test Suite
**What to do:** Create comprehensive integration tests covering all agent interactions and edge cases.
**Files:** `backend/tests/test_recommendation_integration.py`
**Verify:** Integration tests pass and cover critical paths

### 4.3 Implement Verification Pipeline
**What to do:** Create automated verification pipeline that checks system health and recommendation quality.
**Files:** `backend/scripts/verify_recommendations.py`
**Verify:** Pipeline runs automatically and reports system status

### 4.4 Add Performance Tests
**What to do:** Implement performance tests for recommendation generation under load.
**Files:** `backend/tests/test_recommendation_performance.py`
**Verify:** System meets performance requirements under expected load

### 4.5 Create Monitoring Dashboard
**What to do:** Build simple dashboard to monitor recommendation system health and metrics.
**Files:** `backend/app/api/routes/monitoring.py`, frontend monitoring page
**Verify:** Dashboard shows system status, error rates, performance metrics

---

## Detailed Implementation Notes

### Feature Flag System Design
```python
# backend/app/core/features.py
class FeatureFlags:
    """Centralized feature flag management."""
    
    def __init__(self):
        self._flags = self._load_flags()
    
    def is_enabled(self, feature: str) -> bool:
        """Check if feature is enabled."""
        return self._flags.get(feature, False)
    
    def _load_flags(self) -> dict:
        # Load from env vars, database, config file
        # Priority: runtime > database > env > defaults
```

### Configuration Manager Design
```python
# backend/app/agents/config_manager.py
class AgentConfiguration:
    """Centralized configuration for all agents."""
    
    def __init__(self):
        self._config = self._load_config()
    
    def get_scoring_weights(self) -> dict:
        """Get scoring weights for recommendation algorithms."""
        return self._config.get('scoring_weights', DEFAULT_WEIGHTS)
    
    def get_feature_settings(self, feature: str) -> dict:
        """Get settings for specific feature."""
        return self._config.get('features', {}).get(feature, {})
```

### RecommendationOrchestrator Design
```python
# backend/app/agents/recommendation_orchestrator.py
class RecommendationOrchestrator:
    """Orchestrates recommendation generation using pluggable components."""
    
    def __init__(self, config: AgentConfiguration, component_manager: ComponentManager):
        self.config = config
        self.components = component_manager
        
    def recommend(self, context: RecommendationContext) -> List[Outfit]:
        """Generate recommendations using configured components."""
        # 1. Filter candidates
        # 2. Score with multiple strategies
        # 3. Combine scores
        # 4. Apply business rules
        # 5. Return ranked results
```

### Component Registration Pattern
```python
# Example component implementation
class SFTScorer:
    """SFT-based scoring component."""
    
    name = "sft_scorer"
    version = "1.0"
    weight = 0.4  # Configurable
    
    def score(self, items: List, context: dict) -> Dict[str, float]:
        """Score items using SFT model."""
        # Implementation
```

---

## Order of Changes to Preserve Backward Compatibility

1. **Bug fixes first** - Fix immediate issues without changing interfaces
2. **Add configuration system** - New system, doesn't break existing code
3. **Implement new architecture alongside old** - Dual implementation during transition
4. **Gradually migrate to new system** - Using feature flags
5. **Deprecate old system** - After verification and stabilization
6. **Remove old code** - Final cleanup after successful migration

## Verification Steps

### After Phase 1 (Bug Fixes):
- All existing tests pass
- No runtime errors in recommendation generation
- System handles errors gracefully

### After Phase 2 (Configuration):
- Configuration can be changed via environment variables
- Feature flags work correctly
- No performance regression

### After Phase 3 (Architecture):
- New orchestrator produces same results as old system
- Components can be added/removed dynamically
- System more resilient to failures

### After Phase 4 (Testing):
- Test coverage > 80% for recommendation system
- Integration tests cover all critical paths
- Performance tests show acceptable latency
- Monitoring dashboard shows system health

## Success Criteria

1. **Bug-free operation**: No crashes or unexpected errors in recommendation generation
2. **Maximum flexibility**: Configuration allows tuning without code changes
3. **Verification working**: Comprehensive tests and monitoring in place
4. **Backward compatibility**: Existing API endpoints continue to work
5. **Performance maintained**: No significant latency increase
6. **Code quality improved**: Cleaner, more maintainable architecture

---

*Plan created by: Kiro Planning Agent*  
*Date: 2026-11-02*  
*Workflow: wf_5f5d3129e994035e*
# Post-Refactoring Test Plan for Recommendation Agent

## Overview
After the refactoring workflow completes, we need to thoroughly test the recommendation agent to ensure all bugs are fixed and the system is flexible and maintainable.

## Test Categories

### 1. Database Integration Tests
- [ ] Test Supabase PostgreSQL connection with psycopg2
- [ ] Verify all database operations work without prepared statement cache errors
- [ ] Test database schema compatibility (field length limits, especially for 'occasion' field)
- [ ] Verify RLHF feedback collection to database

### 2. Recommendation Pipeline Tests
- [ ] Test end-to-end recommendation generation:
  - Weather verification service
  - Outfit filtering based on weather
  - SFT model inference for outfit composition
  - LLM enhancement and refinement
  - Explanation generation
- [ ] Verify all components integrate correctly
- [ ] Test error handling at each pipeline stage

### 3. Model Performance Tests
- [ ] Verify SFT model loads and makes predictions
- [ ] Test with sample Polyvore data
- [ ] Verify model doesn't produce unreasonable outfits
- [ ] Check explanation quality (should not fall back to rule-based too often)

### 4. RLHF System Tests
- [ ] Test RLHF API endpoints (if rlhf.py exists)
- [ ] Verify feedback collection works
- [ ] Test reward model training pipeline
- [ ] Verify PPO training can run

### 5. Configuration and Flexibility Tests
- [ ] Test configuration through environment variables
- [ ] Verify components can be swapped/modified independently
- [ ] Test with different LLM backends (if configurable)
- [ ] Verify logging and monitoring setup

### 6. Frontend Integration Tests
- [ ] Test recommendation display in frontend
- [ ] Verify explanation rendering
- [ ] Test feedback collection UI
- [ ] Verify error handling in UI

## Test Data Preparation

### Sample Test Cases
1. **Normal case**: User with wardrobe, valid weather data
2. **Edge case**: User with minimal wardrobe items
3. **Error case**: Weather service unavailable
4. **Error case**: LLM timeout
5. **Error case**: Database connection failure

### Test Users
- Create test user with comprehensive wardrobe
- Create test user with limited wardrobe
- Use existing test data from development

## Success Criteria

### Must Have
- All database operations work without errors
- Recommendation pipeline produces valid outfits
- Explanations are generated (not rule-based fallback)
- Error handling prevents system crashes
- RLHF feedback can be collected (if implemented)

### Should Have
- System recovers gracefully from component failures
- Configuration allows component swapping
- Logging provides useful debugging information
- Performance is acceptable (< 5 seconds for full recommendation)

### Nice to Have
- SFT model produces high-quality outfit combinations
- LLM enhances outfits meaningfully
- Explanations are personalized and helpful
- RLHF training improves model over time

## Execution Steps

1. **Run unit tests**: `pytest backend/tests/ -v`
2. **Run integration tests**: Manual end-to-end tests
3. **Load test**: Simulate multiple concurrent users
4. **Error injection tests**: Deliberately break components
5. **Frontend verification**: Manual UI testing

## Verification Checklist

- [ ] All tests pass
- [ ] No new bugs introduced
- [ ] Code follows clean architecture principles
- [ ] Documentation is updated
- [ ] Performance meets requirements
- [ ] Error handling is robust

## Rollback Plan
If tests reveal critical issues:
1. Revert to last known good state (git commit)
2. Document issues found
3. Create focused fix workflow for specific problems
4. Re-test after fixes

## Next Steps After Successful Testing
1. Deploy to staging environment
2. Monitor for real-world issues
3. Collect user feedback
4. Plan next improvements (TTS, MCP fashion trends, etc.)
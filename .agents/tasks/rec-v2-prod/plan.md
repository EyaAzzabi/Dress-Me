# Implementation Plan

## Summary
Connect recommendation_agent_v2 to production by updating the orchestrator import, verify no bugs exist, and clean up obsolete files.

## Exploration Findings

### 1. Bug: Logger import in outfit_composition_sft_model.py
**Finding:** The logger is already imported at line 17 of `backend/app/ml/outfit_composition_sft_model.py`. No fix needed.

### 2. Bug: Typo "alph" -> "alpha" in v2
**Finding:** Not found in v2 - the code correctly uses `_ALPHA`. May already be fixed or never existed. No fix needed.

### 3. Interface Compatibility
**Finding:** v2's `run()` method signature is compatible with v1's:
- Both accept `wardrobe_items`, `occasion`, `request_text`, `season`, `temperature`, `weather`, etc.
- v2 returns all required fields: `outfits` (list of dicts with `item_ids`, `explanation`, `relevance_score`)
- The orchestrator only calls `self.recommendation_agent.run()` (line 104 in orchestrator.py)
- No adapter needed - the import alias handles the class swap

### 4. Files to Delete
- `recommendation_agent.py` - v1, used by orchestrator (will be replaced)
- `recommendation_rag.py` - only imported inside v1's `_node_analyze_context` (local import)
- `recommendation_tools.py` - only imported inside v1's nodes (local imports)
- `recommendation_critic.py` - only imported inside v1's `_node_critic_evaluate` (local import)

All these files will become unused once v2 replaces v1.

---

- [ ] 1. Update orchestrator.py to import v2 instead of v1
      Files: e:\Téléchargements\Dress-Me-main\backend\app\agents\orchestrator.py (line 13)
      Change: FROM `from app.agents.recommendation_agent import RecommendationAgent`
              TO `from app.agents.recommendation_agent_v2 import RecommendationAgentV2 as RecommendationAgent`
      Verify: Run `python -c "from app.agents.orchestrator import AgentOrchestrator; print('Import OK')"` from backend directory

- [ ] 2. Delete obsolete v1 files (only after step 1 passes)
      Files to delete:
        - e:\Téléchargements\Dress-Me-main\backend\app\agents\recommendation_agent.py
        - e:\Téléchargements\Dress-Me-main\backend\app\agents\recommendation_rag.py
        - e:\Téléchargements\Dress-Me-main\backend\app\agents\recommendation_tools.py
        - e:\Téléchargements\Dress-Me-main\backend\app\agents\recommendation_critic.py
      Verify: Run `python -c "from app.agents.orchestrator import AgentOrchestrator; print('Import OK')"` to confirm v2 still works after deletion

- [ ] 3. Run recommendation-related tests if they exist
      Files: Check for tests in tests/ directory
      Verify: Run relevant test commands from backend directory

---

## Notes
- The orchestrator import change is handled by the alias: `from app.agents.recommendation_agent_v2 import RecommendationAgentV2 as RecommendationAgent`
- No code modifications to orchestrator.py are actually needed since v2's interface is backward compatible
- If tests reference v1 directly, they will fail after deletion (expected - they test deprecated code)
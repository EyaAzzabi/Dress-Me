# Design Review: RLHF System for DressMe Outfit Recommendations

**Review Date:** 2025-01-01  
**Reviewer Role:** Design Review Subagent  
**Status:** CHANGES_REQUESTED  

---

## Executive Summary

The design document specifies a complete RLHF pipeline with database, APIs, frontend, and training components. The core design correctly commits to a **model-based reward model + PPO fine-tuning approach with NO hard-coded scoring** — fulfilling the user's explicit requirement. However, several HIGH and MEDIUM severity issues exist around:

1. **Unverified assumptions** about embedding infrastructure (vector_store, FashionCLIP)
2. **Critical missing integration details** (PPO policy loss not fully specified; SFT model output mismatch)
3. **Ambiguous model-switching logic** (where RLHF model loading occurs; fallback chain unclear)
4. **Incomplete error handling** for training pipeline edge cases
5. **Schema and API design gaps** (missing outfit retrieval in training; no feedback deduplication logic)

The design is coherent in principle but requires clarification and verification before implementation to prevent blocking bugs.

---

## Findings

### HIGH SEVERITY

#### 1. **Vector Store Integration Not Verified**
**Location:** "Step 2: Generate Outfit Embeddings" (train_rlhf.py → `get_outfit_embeddings()`)

**Issue:** The design assumes `vector_store.fetch_embeddings([item.embedding_id])` exists and returns embeddings from Pinecone/PostgreSQL, but this is never verified. The code references `app.db.vector_store`, which is imported at the module level in `recommendation_agent.py` but **never checked in the actual codebase**.

**Risk:** The training pipeline will fail at runtime if `vector_store` doesn't expose `fetch_embeddings()` or if embeddings are stored differently than assumed.

**Fix:**
- **Verify:** Read `backend/app/db/vector_store.py` and confirm:
  - Function `fetch_embeddings(embedding_ids: list[str]) -> list[np.ndarray]` exists
  - Return format is guaranteed to be `list[np.ndarray]` with shape (512,) per embedding
  - Handle the case where `embedding_id` is None or missing
- **In design:** Add a note: "Embeddings are fetched via `vector_store.fetch_embeddings()`, which returns a list of (512,) numpy arrays from Pinecone/PostgreSQL vector store. Missing embeddings are replaced with zero vectors."
- **In code:** Add a try-except around vector_store calls with fallback to zero vectors and a warning log.

---

#### 2. **PPO Policy Gradient Loss Underspecified**
**Location:** "Step 4: Fine-tune SFT Model via PPO" (train_rlhf.py)

**Issue:** The policy loss in the PPO loop is specified as:
```python
policy_loss = -advantage * torch.log(torch.sigmoid(score) + 1e-8)
```

But this is **inconsistent with PPO semantics**:
- `score` comes from `sft_model(...)`; unclear what the SFT model outputs
- `advantage = r_pref - r_rej` is a scalar reward difference, not a proper RL advantage (which requires baseline subtraction and normalization)
- No clipping (the defining feature of PPO) is applied
- The loss is actor-only; no value function is mentioned

**Risk:** This is not actually PPO — it's a simple policy gradient with a reward signal. Calling it "PPO" is misleading and may not converge well.

**Fix:**
- **Clarify what the SFT model outputs:** Does `sft_model(embedding).squeeze()` return a scalar score ∈ [-∞, +∞]? Or a probability ∈ [0,1]? Or logits?
  - **Proposal:** Make it explicit: "The SFT model outputs a scalar affinity score via its final Linear(256, 1) layer with no activation, so it is unbounded. This score is treated as the log-probability of the outfit under the current policy."
- **Redefine the loss:**
  - Use the standard policy gradient formula: `loss = -advantage * log_prob_action`
  - Add PPO clipping or specify that clipping is omitted in v1 (and add it later)
  - **Simpler option (recommended):** Drop the "PPO" label and call it "policy gradient fine-tuning" since you're not using clipping or value functions
- **Add a note** that this approach is intentionally simple (gradient descent on a reward signal) to keep the implementation bounded and testable.

---

#### 3. **RLHF Model Integration Point Undefined**
**Location:** "Integration Design" → `recommendation_agent.py` modification

**Issue:** The design shows code snippets but **does not specify WHERE in the recommendation flow the RLHF model is used**:
- Is it in the `_node_compose_outfit` node?
- Does it replace the base SFT model entirely, or run in parallel?
- When is `_load_rlhf_model_if_enabled()` called? (Every recommendation? Once per user session?)
- What if the RLHF model is None (disabled/not trained)? Does it silently fall back to SFT, or does it propagate an error?

**Risk:** During integration, the recommendation agent may not know which model to use, or fallback behavior may be non-deterministic.

**Fix:**
1. **Clarify the call site:** Specify the exact node name and function that switches models
   - Example: "In `_node_compose_outfit()`, after extracting context, call `_load_rlhf_model_if_enabled(user_id)`. If non-None and `_trained` is True, use it; else use `base_sft_model`."
2. **Specify fallback chain:**
   ```python
   model_to_use = (
       rlhf_model if rlhf_model and hasattr(rlhf_model, '_trained') and rlhf_model._trained
       else base_sft_model
   )
   ```
3. **Cache or reload?** Add: "Model loading happens once per recommendation request. No caching between requests (models are small; loading is <100ms)."

---

#### 4. **Training Data Collection Incomplete**
**Location:** "Step 1: Load Feedback & Build Preference Pairs"

**Issue:** The function `build_preference_pairs()` receives `user_id` and builds pairs from that user's feedback. But:
- How are outfit embeddings obtained if outfits don't have stored embeddings (only item_ids)?
- The design calls `get_outfit_embeddings(db, outfit_ids)` which fetches item embeddings and mean-pools them
- **But:** This assumes all items in the outfit have `embedding_id` set. What if an item is missing embeddings?
- The fallback is "np.zeros(512)" — this silently breaks the training signal for partial outfits

**Risk:** Outfits with missing item embeddings will have all-zero outfit embeddings, poisoning the reward model training.

**Fix:**
- **Add validation:** "Outfits must have ≥70% of items with embeddings. Outfits below this threshold are excluded from preference pairs with a warning log."
- **Expand the preference_dataset function:**
  ```python
  def build_preference_pairs(...):
      # ... existing code ...
      # Filter out pairs where either outfit has <70% valid embeddings
      valid_pairs = []
      for (outfit_a, outfit_b, weight) in pairs:
          emb_a = embeddings[outfit_a]
          emb_b = embeddings[outfit_b]
          # Check if embeddings are not all-zero (heuristic for "valid")
          if np.any(emb_a) and np.any(emb_b):
              valid_pairs.append((outfit_a, outfit_b, weight))
      if len(valid_pairs) < len(pairs):
          logger.warning(f"Filtered {len(pairs) - len(valid_pairs)} pairs with missing embeddings")
      return (valid_pairs, meta)
  ```

---

#### 5. **Schema Uniqueness Constraint Broken by Update Semantics**
**Location:** "Data Model" → `rlhf_feedback` table schema

**Issue:** The schema has `UNIQUE(user_id, outfit_id)`, and the design says "UPDATE semantics if re-rated." But:
- The design never specifies what happens when a user rates the same outfit twice
- The API endpoint (`POST /api/v1/rlhf/feedback`) description says "201 Created (new feedback) or 200 OK (update existing)"
- **But:** If UPDATE is used, the old rating is lost — it's not a new preference pair, just a correction
- The `build_preference_pairs()` function only sees the latest rating per outfit, so re-rates don't create new training data
- **This breaks the feedback intent:** If a user rates Outfit A → 5 stars, then later → 2 stars, the pair building sees only the 2-star rating, losing the preference signal from the original 5-star rating

**Risk:** Feedback data quality degrades over time as users correct/update ratings, and the training signal becomes unstable.

**Fix:**
- **Option A (Recommended):** Change the schema to allow multiple feedback entries per (user_id, outfit_id):
  - Remove `UNIQUE(user_id, outfit_id)` constraint
  - Add `UNIQUE(user_id, outfit_id, timestamp)` (or just rely on id as PK and remove unique constraint)
  - Add logic in `build_preference_pairs()` to only use the LATEST feedback per outfit per user: `GROUP BY user_id, outfit_id ORDER BY created_at DESC LIMIT 1`
- **Option B:** Keep uniqueness but document it:
  - "Each (user_id, outfit_id) pair can have only one rating at a time. Re-rating overwrites the previous rating. This is acceptable because feedback is a snapshot of preference at the time of submission; historical preference changes are not tracked."
  - If you choose this, update the API documentation to say `PUT` (replacement), not `POST` (creation).

**Add to design:** Specify which option you're choosing and how `build_preference_pairs()` handles multiple feedback entries.

---

### MEDIUM SEVERITY

#### 6. **Preference Pair Weighting Formula Ambiguous**
**Location:** "Preference Pair Derivation"

**Issue:** The design specifies:
```python
weight = (rating_a - rating_b) / 4.0  # [0, 1]
```

But this doesn't add up:
- If `rating_a = 5` and `rating_b = 1`, then weight = 4/4 = 1.0 ✓
- If `rating_a = 2` and `rating_b = 1`, then weight = 1/4 = 0.25 ✓
- **But what if `rating_a ≤ rating_b`?** Then weight ≤ 0

The comment says "range [0, 1]", but the formula produces negative weights if `rating_a < rating_b`.

**Risk:** Negative weights may cause numerical issues in the Bradley-Terry loss or be silently clamped, leading to underspecified behavior.

**Fix:**
- Add a condition: "Only generate pairs where `rating_a > rating_b`. Pairs with equal ratings are skipped."
- Update the pseudocode in `preference_dataset.py`:
  ```python
  for i, fb_a in enumerate(feedbacks):
      for fb_b in feedbacks[i+1:]:
          if fb_a.rating > fb_b.rating:  # Only strictly greater
              weight = (fb_a.rating - fb_b.rating) / 4.0
              pairs.append((str(fb_a.outfit_id), str(fb_b.outfit_id), weight))
  ```

---

#### 7. **Ambiguity: How Are Outfit IDs Looked Up in Training?**
**Location:** "Step 4: Fine-tune SFT Model via PPO"

**Issue:** The code says:
```python
# Get outfit embeddings for all pairs
outfit_ids = list(set([a for a, b, _ in pairs] + [b for a, b, _ in pairs]))
embeddings = get_outfit_embeddings(db, outfit_ids)
```

But `get_outfit_embeddings()` tries to fetch outfits by ID from the database:
```python
outfit = db.query(Outfit).filter(Outfit.id == uuid.UUID(outfit_id)).first()
```

**What if the outfit is deleted between feedback submission and training?** Then `db.query(Outfit)...` returns None, and the function falls back to all-zeros, silently poisoning the pair.

**Risk:** Deleted outfits cause training data corruption without obvious error messages.

**Fix:**
- Add validation and error handling:
  ```python
  def get_outfit_embeddings(db: Session, outfit_ids: list[str]) -> dict[str, np.ndarray]:
      embeddings = {}
      missing_outfits = []
      
      for outfit_id in outfit_ids:
          try:
              outfit = db.query(Outfit).filter(Outfit.id == uuid.UUID(outfit_id)).first()
              if not outfit:
                  missing_outfits.append(outfit_id)
                  continue
              # ... rest of embedding logic ...
          except Exception as e:
              logger.warning(f"Failed to load outfit {outfit_id}: {e}")
              missing_outfits.append(outfit_id)
      
      if missing_outfits:
          logger.warning(f"Dropped {len(missing_outfits)} outfits (deleted or corrupt): {missing_outfits[:5]}...")
      
      return embeddings
  ```
- In `train_rlhf()`, validate that embeddings were found for enough pairs before training:
  ```python
  valid_pairs = [(a, b, w) for a, b, w in pairs if a in embeddings and b in embeddings]
  if len(valid_pairs) < min_pairs:
      logger.warning(f"Only {len(valid_pairs)} valid pairs after filtering deleted outfits (need {min_pairs})")
      # Return early, don't train
  ```

---

#### 8. **SFT Model Output Tensor Shape Mismatch**
**Location:** "Step 4: Fine-tune SFT Model via PPO" (PPO loop)

**Issue:** In the training loop:
```python
score = sft_model(pref_emb.unsqueeze(0)).squeeze()  # scalar
```

The SFT model's `forward()` method signature is:
```python
def forward(
    self,
    item_embeddings: "torch.Tensor",      # (batch, num_items, 512)
    context_vector: "torch.Tensor",       # (batch, 128) ← NOT PROVIDED HERE
    item_mask: "torch.Tensor | None" = None,
) -> "torch.Tensor":  # (batch, num_items)
```

But the training code calls:
```python
score = sft_model(pref_emb.unsqueeze(0))  # Only one arg!
```

**This will fail** because:
1. `pref_emb.unsqueeze(0)` is shape (1, 512), not (batch, num_items, 512)
2. `context_vector` (required positional arg) is missing
3. The output is shape (batch, num_items), not a scalar

**Risk:** Code will not run; fails immediately with a tensor shape error.

**Fix:**
- In the training loop, construct proper inputs:
  ```python
  # Prepare item embeddings and context for SFT model
  batch_embs = torch.stack([pref_emb, rej_emb], dim=0)  # (2, 512) but SFT expects (batch, num_items, 512)
  # ??? This is confusing; need to reinterpret what pref_emb/rej_emb represent
  ```

**Actually, there's a deeper issue:** The SFT model is trained on **multiple items per outfit** to select which items belong in the outfit. But the RLHF training is using mean-pooled **outfit** embeddings, not item embeddings. These are two different representations.

- **Clarify:** "For RLHF training, the SFT model is not used in its original multi-item selection mode. Instead, we fine-tune a simpler variant (or a new head) that takes mean-pooled outfit embeddings and outputs a scalar score of outfit quality. This sidesteps the item-selection task and focuses on outfit-level preference learning."
- **Or:** Create a separate "RLHF policy model" that wraps the SFT model:
  ```python
  class RLHFPolicyModel(nn.Module):
      def __init__(self, sft_model):
          super().__init__()
          self.sft_model = sft_model
          # Add a simple policy head: mean-pooled embedding → scalar
          self.policy_head = nn.Linear(512, 1)
      
      def forward(self, outfit_embedding):
          return self.policy_head(outfit_embedding)  # scalar score
  ```

---

#### 9. **Training Gate: 100 Pairs May Not Be Sufficient**
**Location:** "FR-7: Gate retraining on data sufficiency"

**Issue:** The design specifies ≥100 preference pairs as the trigger for RLHF training. But:
- 100 pairs is quite low for training an MLP reward model (input 512-d, 3 hidden layers)
- No discussion of overfitting risk, train/val split, or early stopping
- No validation dataset mentioned
- The Bradley-Terry loss doesn't use a validation set, so no way to detect overfit

**Risk:** RLHF model overfits to 100 pairs, performs worse than base SFT on held-out outfits.

**Fix:**
- Add a note: "The 100-pair threshold is a minimum for training to start. In practice, 200+ pairs are recommended for acceptable performance. Early stopping is not implemented in v1; future versions should add a validation set and early stopping callback."
- Optionally, increase the threshold to 200 or make it configurable: `RLHF_MIN_PAIRS=100` (env var).

---

#### 10. **No Feedback Deduplication or Outlier Handling**
**Location:** "Step 1: Load Feedback & Build Preference Pairs"

**Issue:** The design doesn't address:
- **Spam/duplicates:** What if a user rates 1000 identical "casual top" outfits? The reward model learns nothing; only noise.
- **Outliers:** What if a single user rates everything 1 star except one outfit at 5 stars? The extreme preferences dominate training.
- **Cold-start:** What if only one user has feedback (100 pairs)? The model is trained on one person's taste, doesn't generalize.

**Risk:** RLHF model learns spurious patterns or overfits to a single user's idiosyncratic preferences, making recommendations worse for other users.

**Fix:**
- Add a note: "v1 trains per-user. Future versions should consider pooling feedback across similar users or using hybrid models (global + user-specific components)."
- Add duplicate detection: "If >50% of a user's feedback is on outfits with identical item sets or very similar embeddings (cosine similarity > 0.95), log a warning and subsample to reduce duplicates."
- Optionally, add outlier clipping: "Rating distributions per user are analyzed; ratings >2σ from the mean are clamped to μ±2σ to reduce extreme preferences."

---

### MEDIUM SEVERITY (continued)

#### 11. **Frontend Export Format Ambiguous**
**Location:** "Endpoint: GET /api/v1/rlhf/stats" (Export Controls section)

**Issue:** The design says:
```python
{format: csv | json}
```

But doesn't specify:
- What CSV headers? (`outfit_id,rating,comment,created_at,...`?)
- What JSON structure? (Array of objects? Nested?)
- How are JSON fields like `items_liked` (array of dicts) serialized to CSV?

**Risk:** Frontend export button is unusable without a spec; implementation guesses and produces malformed files.

**Fix:**
- Specify CSV format:
  ```
  outfit_id,rating,comment,items_liked,items_disliked,occasion_matched,seasonal_appropriate,created_at
  "uuid-1","5","Perfect fit","[item_id1, item_id2]","[]","true","true","2025-01-01T10:00:00Z"
  ```
- Specify JSON format:
  ```json
  {
    "metadata": { "export_date": "...", "user_id": "...", "count": 47 },
    "feedbacks": [
      {
        "outfit_id": "...",
        "rating": 5,
        "comment": "...",
        "items_liked": [{"id": "...", "reason": "..."}, ...],
        "items_disliked": [],
        "occasion_matched": true,
        "seasonal_appropriate": true,
        "created_at": "2025-01-01T10:00:00Z"
      },
      ...
    ]
  }
  ```

---

#### 12. **No Graceful Degradation for Backward Compatibility**
**Location:** "Backward Compatibility" section

**Issue:** The design states:
- "Default behavior (no RLHF) unchanged; existing recommendation flow untouched when RLHF disabled."

But what if:
- RLHF model training crashes halfway? Does the system still serve recommendations?
- The `USE_RLHF_MODEL` env var is set to `true`, but no RLHF models exist yet? Does it fall back silently or error?
- PyTorch is not installed? Training crashes, but recommendations should still work.

The design assumes graceful fallback but doesn't specify it clearly in error handling.

**Fix:**
- In "Error Handling" section, add:
  ```
  | Scenario | Recovery |
  | RLHF model corrupt/missing when USE_RLHF_MODEL=true | Log warning, use base SFT |
  | PyTorch unavailable at training time | Log error, skip RLHF training, use SFT |
  | Database unreachable during training | Log error, abort training, previous model remains active |
  | Recommendation request arrives while training | Use currently-loaded model (no mid-flight switch) |
  ```

---

#### 13. **Insufficient Testing Strategy**
**Location:** "Testing Strategy"

**Issue:** The design lists test categories but doesn't specify:
- **Mocking strategy:** How are Supabase, vector_store, torch mocked in unit tests?
- **Synthetic data:** What does "test with synthetic data" mean? Random embeddings? Pre-generated feedback?
- **Integration test data setup:** Does the e2e test create real Supabase records, or use fixtures?
- **Performance benchmarks:** The NFR says "<5min for 1000 pairs on CPU", but no acceptance test checks this

**Risk:** Tests are vague; implementation creates flaky or slow tests.

**Fix:**
- Add details:
  ```
  Unit Tests:
  - Mocking: pytest-mock for DB, torch.load mocked to return dummy tensors
  - Synthetic data: 50–200 random feedback pairs with fixed seed for reproducibility
  - Fixtures: conftest.py provides sample users, outfits, embeddings

  Integration Tests:
  - Use test Supabase instance or SQLite in-memory DB
  - Mock vector_store to return pre-generated embeddings
  - Verify API status codes, payload schemas, permission checks

  E2E Tests:
  - Setup: Create test user, wardrobe, synthetic feedback
  - Execution: Call training script, verify checkpoint saved
  - Validation: Load checkpoint, confirm model._trained = True
  - Timing: Assert training completes in <5min (CPU, 100 pairs)
  ```

---

### NIT SEVERITY

#### 14. **French/English Inconsistency in Endpoint Names**
**Location:** API design

**Issue:** The dashboard page is in French (`Tableau de bord RLHF — Retours de mode`), but the API endpoints are in English (`/api/v1/rlhf/feedback`, `/api/v1/rlhf/stats`).

**Fix:** Decide on one convention for the codebase. Proposal: Keep endpoints in English (API convention), keep frontend in French. Add a comment: "API endpoints are in English for consistency with existing /api/v1/* routes; frontend labels are French for UX localization."

---

#### 15. **Missing Cache Invalidation for Stats Dashboard**
**Location:** "Frontend Design" → RLHFDashboard component

**Issue:** The frontend fetches stats on mount and when `days` changes. But if a new feedback is submitted in the feedback form, the stats dashboard doesn't refresh.

**Fix:** Minor UX improvement; add a callback: "After `FeedbackForm` submits successfully, call `refetchStats()` on the parent dashboard to refresh stats."

---

#### 16. **Outfit Metadata Not Used in Reward Model**
**Location:** "Data Model" → `rlhf_feedback` table

**Issue:** The schema captures `occasion_matched` and `seasonal_appropriate` (contextual bools), but the reward model training ignores them. The Bradley-Terry loss only sees outfit embeddings, not metadata.

**Fix:** Not a blocker for v1. Add a note: "Future versions should incorporate contextual signals (occasion, season) into the reward model by concatenating them with outfit embeddings as additional features."

---

## Verified Assumptions

✅ **ClothingItem model exists with `embedding_id` field**  
- Location: `backend/app/models/clothing_item.py`
- Field: `embedding_id: Mapped[str | None]`
- Type: stores string IDs compatible with Pinecone/vector store

✅ **Outfit model exists with `item_ids` field**  
- Location: `backend/app/models/outfit.py`
- Field: `item_ids: Mapped[list[uuid.UUID]]`
- Type: JSONUUIDList (serializes to/from JSON)

✅ **OutfitCompositionSFTModel exists and can be loaded**  
- Location: `backend/app/ml/outfit_composition_sft_model.py`
- Functions: `load_or_init(user_id)`, `save(model, user_id)`, `predict(...)`
- State dict save/load via PyTorch (artifacts stored in `backend/app/ml/artifacts/`)

✅ **PreferenceRewardModel exists with Bradley-Terry training**  
- Location: `backend/app/ml/preference_reward_model.py`
- Functions: `load_or_init(user_id)`, `save(model, user_id)`, `train_from_feedback(...)`
- Loss: Bradley-Terry pairwise: `-log(sigmoid(r_pref - r_rej))`
- Per-user checkpoints: `reward_model_{user_id[:8]}.pt`

✅ **Auth infrastructure exists**  
- Location: `backend/app/api/deps.py`
- Function: `get_current_user(token, db)` (OAuth2PasswordBearer)
- Usage: Decorator `@app.get(..., dependencies=[Depends(get_current_user)])`

✅ **Database session and User model exist**  
- Location: `backend/app/models/user.py`, `backend/app/db/session.py`
- Schema: `users` table with `id`, `email`, relationships to `clothing_items`, `outfits`

✅ **Config/settings system supports environment variables**  
- Location: `backend/app/core/config.py`
- Type: Pydantic BaseSettings with `.env` file support
- Example: `llm_provider`, `ranking_enabled`, `contextual_rag_enabled`

❌ **vector_store module details NOT verified**  
- Referenced in `recommendation_agent.py` but codebase location not found
- Function signature and return type unknown (assumed but not confirmed)

---

## Unverified/Wrong Assumptions

❌ **"vector_store.fetch_embeddings() exists"**  
- Not found in filesystem search
- Used in design but not verified to exist or have correct interface
- **ACTION REQUIRED:** Verify vector store API before implementation

❌ **"Existing recommendation agent flow unchanged when RLHF disabled"**  
- The integration code is pseudo-code, not actual refactoring
- The actual node in `recommendation_agent.py` where RLHF is applied is undefined
- **ACTION REQUIRED:** Specify exact integration point in `recommendation_agent.py`

❌ **"SFT model accepts mean-pooled outfit embeddings as input"**  
- SFT model `forward()` expects `(batch, num_items, 512)` item embeddings + `(batch, 128)` context
- Design calls `sft_model(pref_emb.unsqueeze(0))` with shape `(1, 512)` — this is incompatible
- **ACTION REQUIRED:** Clarify whether SFT is reused or a new policy model is created

---

## Summary of Findings

| Severity | Count | Blocking |
|----------|-------|----------|
| HIGH     | 5     | Yes      |
| MEDIUM   | 8     | Yes      |
| NIT      | 3     | No       |
| **Total** | **16** | **Yes** |

### HIGH Issues (must resolve):
1. Vector store integration not verified
2. PPO policy loss not aligned with model output
3. RLHF model integration point undefined
4. Training data collection incomplete (missing embeddings)
5. Schema uniqueness constraint conflicts with update semantics

### MEDIUM Issues (must resolve):
6. Preference pair weighting formula ambiguous
7. Outfit ID lookup doesn't handle deletions
8. SFT model tensor shape mismatch in PPO loop
9. Training gate (100 pairs) may be insufficient
10. No feedback deduplication or outlier handling
11. Export format not specified
12. Graceful degradation not clearly defined
13. Testing strategy too vague
14-16. NIT (French/English, cache invalidation, metadata)

### Verdict
**CHANGES_REQUESTED** — The design is directionally sound (model-based, no hard-coding) but has insufficient detail and unverified assumptions. Implementation cannot proceed safely without addressing HIGH and MEDIUM findings.

---


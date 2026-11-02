# Requirements Document: RLHF System for DressMe

**Version:** 1.0  
**Date:** 2025-11-01  
**Project:** Dress-Me Outfit Recommendation System  
**Feature:** Reinforcement Learning from Human Feedback (RLHF) Integration

---

## Summary

Implement an end-to-end RLHF system that learns outfit recommendations from user feedback, delivering genuinely model-based improvements to outfit quality. The system captures user ratings (1–5 stars) and item-level preferences, builds preference pairs for training, trains a Bradley-Terry reward model, and fine-tunes the existing SFT model via policy gradient (PPO) optimization. All scoring decisions are derived from the trained reward model; no hand-coded heuristics.

**Core Constraint:** The user explicitly requires no hard-coded rules. Every decision (what makes a good outfit, how to rank items, which outfit to recommend) must come from the trained model, not from hand-written scoring functions or conditional logic.

---

## Functional Requirements

### FR-1: Structured Feedback Collection
**Description:** Users can submit feedback on recommended outfits.  
**Details:**
- Rate outfit 1–5 stars
- Optionally add free-text comment (≤500 chars)
- Select which items in the outfit they liked
- Select which items they disliked
- Optionally indicate whether outfit matched the requested occasion and was seasonally appropriate

**Mapped to constraint:** Captures granular preference signals; items_liked/disliked arrays feed into reward model training, eliminating hand-coded item compatibility rules.

### FR-2: Persistent Feedback Storage
**Description:** Feedback is stored in database with full audit trail.  
**Details:**
- Store user_id, outfit_id, rating, comment, items_liked (JSON array), items_disliked (JSON array)
- Track created_at, updated_at timestamps
- Enforce one feedback per user-outfit pair (update semantics on re-rating)
- Support efficient querying by user and time range

**Mapped to constraint:** Persistent storage enables model training on historical preferences, replacing heuristics with learned patterns.

### FR-3: Feedback Statistics & Analytics Dashboard
**Description:** Users see aggregated insights from their feedback.  
**Details:**
- Display total feedback count, average rating, rating distribution (1–5)
- Show recent feedbacks with outfit details
- Identify most liked and disliked items (from JSON arrays)
- Display rating trend over time (last 7, 30 days)
- Indicate readiness for model retraining (≥100 preference pairs available)
- Support CSV/JSON export of feedback

**Mapped to constraint:** Dashboard shows data quality and model readiness without revealing hand-coded scoring logic; all numbers come from feedback data and trained models.

### FR-4: Preference Pair Generation for Training
**Description:** Build comparison pairs from ratings to train reward model.  
**Details:**
- Group feedbacks by user
- Compare all pairs within time window: if rating_A > rating_B, then (Outfit_A, Outfit_B) is preferred pair
- Weight pairs by rating magnitude: weight = (rating_A - rating_B) / 4.0 ∈ [0, 1]
- Require minimum 100 pairs before training proceeds

**Mapped to constraint:** Preference pairs are derived entirely from user ratings, not from any hand-defined preference function. The model learns what users prefer by observing their feedback patterns.

### FR-5: Bradley-Terry Reward Model Training
**Description:** Train a neural reward model on preference pairs using Bradley-Terry pairwise loss.  
**Details:**
- Load outfit embeddings (mean-pooled from item FashionCLIP embeddings)
- Initialize or load existing PreferenceRewardModel (512-d input MLP)
- Use Bradley-Terry loss: L = -log(sigmoid(r_preferred - r_rejected))
- Train for ~20 epochs with Adam optimizer (lr=1e-4)
- Persist model state dict to `artifacts/reward_model_{user_id[:8]}.pt`

**Mapped to constraint:** The core of the constraint — this model learns to score outfits purely from preference data. There is no hand-coded "good outfit" function; the model discovers what users prefer and learns to predict that preference.

### FR-6: SFT Model Fine-Tuning via PPO
**Description:** Optimize the base SFT outfit generation model toward high reward scores using policy gradient.  
**Details:**
- Load base SFT model (`outfit_composition_sft.pt`)
- Load trained reward model
- For each preference pair, compute advantage: A = r_preferred - r_rejected
- Update SFT model parameters via gradient ascent: maximize log(π(a|s)) × A
- Use PPO clipping to control policy divergence
- Run 3 PPO update epochs
- Save fine-tuned model to `artifacts/outfit_composition_sft_rlhf_{user_id[:8]}.pt`

**Mapped to constraint:** Policy gradient optimization ensures the SFT model learns to generate outfits that score high according to the reward model. Every generated outfit is shaped by the learned preferences, not by rule-based composition logic.

### FR-7: Retraining Gate & Offline Training
**Description:** RLHF training only runs when sufficient data exists; training is offline.  
**Details:**
- Query preference pairs count before training
- Skip training if <100 pairs; log warning with metadata
- Training triggered manually via `python train_rlhf.py --user-id <id>`
- No blocking of inference; training runs in background process
- Log training progress and save metrics (loss, accuracy, duration)

**Mapped to constraint:** Ensures high-quality reward model training with sufficient data; prevents poor models trained on insufficient preferences. Manual triggering gives control over when the learned model is deployed.

### FR-8: Model Selection via Environment Variable
**Description:** Switch between base SFT and RLHF-trained model without code changes.  
**Details:**
- Add environment variable `USE_RLHF_MODEL` (true/false, default false)
- In recommendation agent, check setting; load appropriate model
- If RLHF model unavailable or corrupt, gracefully fallback to base SFT
- Log which model is in use for each recommendation

**Mapped to constraint:** Allows safe rollout of learned model; can toggle back to base SFT if RLHF model performs poorly.

### FR-9: Feedback Data Export
**Description:** Users can export feedback history for external analysis.  
**Details:**
- Dashboard provides "Export CSV" and "Export JSON" buttons
- CSV: tabular format with columns [outfit_id, rating, comment, items_liked, items_disliked, created_at]
- JSON: structured array of feedback objects
- Include aggregates (total, average, trends) in export

**Mapped to constraint:** Enables users and researchers to audit feedback quality and model decisions; transparency supports the principle that everything is learned, not hard-coded.

### FR-10: Backward Compatibility & Graceful Degradation
**Description:** Existing recommendation flow untouched when RLHF disabled or unavailable.  
**Details:**
- Default: `USE_RLHF_MODEL=false` → original behavior
- If RLHF model missing or corrupted → fallback to base SFT
- Feedback endpoints work regardless (feedback collected even if not used)
- No breaking changes to recommendation API contract

**Mapped to constraint:** Ensures safe integration; RLHF is additive, not forced. Team can gradually increase reliance on learned models.

---

## Non-Functional Requirements

### NFR-1: Model-Based Architecture
**Requirement:** Every outfit quality decision is derived from trained models; no hard-coded rules.  
**Verification:** Code review: search for outfit scoring functions; all must invoke trained model, not conditional logic. No string matches like `if formality == "formal"` → increase score.

### NFR-2: Performance
**Requirement:** 
- Feedback submission: <100ms latency (p95)
- Stats query: <500ms latency (p95)
- RLHF training (1000 pairs): <5 minutes on CPU

**Verification:** Load test with wrk or similar; benchmark training script on test data.

### NFR-3: Reliability & Graceful Degradation
**Requirement:** 
- Missing PyTorch → training skipped, no crash
- Corrupt model checkpoint → train from scratch
- Supabase unavailable → API returns 503, logged

**Verification:** Unit tests mock PyTorch absence; integration tests simulate DB failures.

### NFR-4: Security & Data Privacy
**Requirement:**
- Feedback is user-owned; no cross-user leakage
- Auth enforced on all feedback endpoints
- No PII in embeddings or model artifacts
- Audit logs for all feedback access

**Verification:** Integration tests verify auth checks; manual audit of logged data.

### NFR-5: UI/UX Consistency
**Requirement:**
- Dashboard matches DressMe visual identity (colors, fonts, spacing)
- Responsive design (mobile-first)
- French language labels throughout
- Intuitive feedback form (clear star rating, obvious item selection)

**Verification:** Visual regression tests; QA review by design team.

### NFR-6: Testability
**Requirement:**
- RLHF training tested with synthetic preference pairs
- Backend APIs tested with mocked database
- Frontend components testable in isolation (Jest + React Testing Library)
- E2E test validates full feedback → training → model switch → improvement

**Verification:** Unit and integration test coverage >80%; E2E test passes.

---

## Acceptance Criteria

### AC-1: Database Schema Deployed
- [ ] `rlhf_feedback` table exists in Supabase
- [ ] Columns: id, user_id, outfit_id, rating, comment, items_liked, items_disliked, occasion_matched, seasonal_appropriate, created_at, updated_at
- [ ] Constraints: CHECK rating ∈ [1, 5], UNIQUE (user_id, outfit_id), ForeignKeys to users and outfits
- [ ] Indexes: idx_user_created, idx_outfit_rating
- [ ] Alembic migration applied successfully

### AC-2: Backend API Functional
- [ ] POST `/api/v1/rlhf/feedback` accepts valid request, returns 201/200
- [ ] POST rejects invalid rating, returns 422
- [ ] POST rejects non-owned outfit, returns 404
- [ ] GET `/api/v1/rlhf/stats` returns aggregates with no errors
- [ ] GET stats includes: total_feedbacks, average_rating, recent_feedbacks, most_liked_items, avg_rating_trend, readiness_for_training
- [ ] Auth enforced: unauthenticated requests return 401
- [ ] Error responses include meaningful error messages

### AC-3: Frontend Dashboard Deployed
- [ ] Page at `/rlhf-dashboard` loads without errors
- [ ] Stats overview displays: total, average rating, last updated, readiness signal
- [ ] Rating trend chart renders correctly
- [ ] Most liked/disliked items lists populate and update on refresh
- [ ] Recent feedbacks list displays recent 10 feedbacks with outfit ID, rating, comment
- [ ] CSV export button triggers download of valid CSV file
- [ ] JSON export button triggers download of valid JSON file
- [ ] Navigation link in header/sidebar points to dashboard

### AC-4: RLHF Training Script Runs Successfully
- [ ] `python train_rlhf.py --user-id <test_id>` completes without errors
- [ ] Logs preference pair count, training epochs, loss values
- [ ] If <100 pairs: skips training, logs "Insufficient data", returns metadata
- [ ] If ≥100 pairs: trains reward model, trains SFT model, saves checkpoints
- [ ] Checkpoints saved to `artifacts/reward_model_*.pt` and `artifacts/outfit_composition_sft_rlhf_*.pt`
- [ ] Metrics logged: ppo_loss_history, initial/final accuracy, training duration

### AC-5: Model Switching Functional
- [ ] `USE_RLHF_MODEL=false` (default) → recommendations use base SFT
- [ ] `USE_RLHF_MODEL=true` → recommendations use RLHF model (if available)
- [ ] Missing RLHF model → fallback to base SFT, no crash
- [ ] Logs indicate which model is in use

### AC-6: Backward Compatibility
- [ ] Existing `/recommendations/outfits` endpoint unchanged
- [ ] Existing feedback endpoint (`PUT /outfits/{id}/feedback`) still works
- [ ] No breaking changes to request/response schemas
- [ ] Tests for existing recommendation flow still pass

### AC-7: Measurable Improvement
- [ ] Synthetic test: create high/low-rated outfit pairs
- [ ] Train reward model on 100+ pairs
- [ ] Fine-tune SFT model via PPO
- [ ] Verify: SFT-RLHF model predicts high-rated outfits higher reward than low-rated
- [ ] Accuracy >70% on held-out pairs

### AC-8: End-to-End Integration
- [ ] Collect 50+ feedbacks via API
- [ ] Run training script: training completes, models saved
- [ ] Switch `USE_RLHF_MODEL=true`
- [ ] Generate recommendations: uses RLHF model
- [ ] Verify logs indicate RLHF model in use
- [ ] Manually inspect recommended outfits for quality improvement

---

## Out of Scope

- **A/B Testing Infrastructure:** No built-in A/B testing or experimentation framework; testing is manual
- **Real-time Model Serving:** No online learning; model updates only via batch training
- **Mobile Integration:** Frontend assumes web-only; mobile requires separate implementation
- **Advanced RL Algorithms:** Scoped to Bradley-Terry + PPO; no DPO, ITERATIVE CAs, etc.
- **Explainability:** No attention maps, saliency plots, or other interpretability tools
- **Multi-user Collaborative Filtering:** Each user has independent model; no cross-user preference sharing
- **Production Orchestration:** No Kubernetes manifests, load balancing, or CI/CD automation beyond basic scripts

---

## Assumptions

1. **Existing FashionCLIP embeddings available:** ClothingItem records have embedding_id populated; vector_store can retrieve them.
2. **Outfit IDs immutable:** Outfit IDs do not change; feedback references are stable.
3. **PyTorch installed:** torch, torch.nn, torch.optim available in training environment.
4. **Supabase PostgreSQL with psycopg2:** DATABASE_URL uses psycopg2 driver; connection stable.
5. **FastAPI auth functional:** get_current_user works; all protected endpoints will enforce auth.
6. **Polyvore dataset available:** base SFT model trained on Polyvore; available at `backend/app/ml/artifacts/outfit_composition_sft.pt`.

---

## Mapping: Constraint → Requirements

**User Requirement:** "RLHF must be genuinely model-based with NO hard-coded rules."

| Requirement | How It Enforces No Hard-Coded Rules |
|-------------|-------------------------------------|
| FR-4 Preference pairs from ratings | Preference signal comes from user data, not pre-defined rules |
| FR-5 Bradley-Terry reward model | Learns to score outfits via gradient descent, not hand-coded formula |
| FR-6 PPO fine-tuning | SFT model optimized toward learned reward, not rule-based composition |
| NFR-1 Model-based architecture | Every decision invokes trained model; code review ensures no conditional scoring |
| AC-7 Measurable improvement | Proves learned model outperforms (or matches) heuristic baseline |

---

## Testing & Verification Plan

### Unit Tests
- Preference pair generation: test edge cases (empty feedback, single pair, ties)
- Reward model: Bradley-Terry loss computation, convergence
- SFT-PPO fine-tuning: policy gradient direction, advantage computation

### Integration Tests
- API feedback submission with auth, validation, permission checks
- API stats aggregation; trend calculation accuracy
- Training pipeline: full loop (load data → build pairs → train → save)

### End-to-End Tests
- Collect feedback via UI → verify API stores it → query stats → see feedback reflected → run training → verify models saved → switch model → recommend & verify RLHF model used

### Manual QA
- Dashboard UX walkthrough (star rating, item selection, export)
- Training script execution with real data
- A/A test: RLHF model vs. base SFT on held-out feedback pairs

---

## Success Definition

✅ **System is successful when:**

1. Users can submit outfit feedback (1–5 stars, items liked/disliked) via API and dashboard
2. Statistics dashboard displays real-time aggregates and trends
3. Training pipeline generates >70% accurate reward model on ≥100 preference pairs
4. RLHF-fine-tuned SFT model produces higher-rated outfits than base SFT (measurable in test)
5. Model switching works without code changes (environment variable)
6. All existing recommendation functionality unchanged (backward compatible)
7. No hard-coded outfit scoring logic; all decisions from trained models
8. System handles errors gracefully; PyTorch/DB unavailability does not crash

---

**Document Version:** 1.0  
**Created:** 2025-11-01  
**Status:** Ready for Design Review

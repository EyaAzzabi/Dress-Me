# Implementation Plan — RLHF + Deep Learning Upgrade for DressMe RecommendationAgent

## Context

- **Backend root:** `e:\Téléchargements\Dress-Me-main\Dress-Me-main\backend`
- **Test command:** `cd backend && .\venv\Scripts\python.exe -m pytest tests\test_recommendation_agent.py -x -q`
- **Full suite:** `cd backend && .\venv\Scripts\python.exe -m pytest tests\ -x -q`
- **PyTorch version:** 2.15.0+cpu (CPU-only — no CUDA)
- **Artifacts dir:** `backend\app\ml\artifacts\`

All four modules must leave the existing 16 `test_recommendation_agent` tests passing (additive-only). Every torch operation is wrapped in `try/except`.

---

- [ ] 1. Create `backend/app/ml/artifacts/` placeholder (already exists) and `outfit_transformer.pt` save path.
      The artifacts directory exists at `backend/app/ml/artifacts/`. No file to create — just confirm the path is used in the two new model files. This item is informational; no code change required.
      Files: *(none — verification only)*
      Verify: `python -c "from pathlib import Path; p=Path('app/ml/artifacts'); assert p.exists()"` run from `backend/`.

- [ ] 2. Create `backend/app/ml/outfit_compatibility_transformer.py`.
      Implement `OutfitCompatibilityTransformer(nn.Module)` with:
      - Learnable positional embedding `nn.Embedding(10, 512)` (max 10 garments; garments have no natural order so we use a learnable, not fixed sinusoidal, PE).
      - `nn.TransformerEncoder` with 2 layers, 4 heads, d_model=512, dim_feedforward=1024, dropout=0.1.
      - Mean pooling over the sequence dimension.
      - MLP head: `Linear(512,256) → ReLU → Dropout(0.1) → Linear(256,1) → Sigmoid`.
      - `train_on_polyvore_style_data(positive_pairs, negative_pairs)` — trains with `BCELoss`, Adam lr=1e-4, 10 epochs, CPU-only.
      - `score_outfit(embeddings: list[np.ndarray]) -> float` — inference; stacks embeddings, adds positional encoding, runs forward pass; returns Python float.
      - Module-level `load_or_init() -> OutfitCompatibilityTransformer` — loads from `artifacts/outfit_transformer.pt` if it exists, else returns a fresh untrained model.
      - Module-level `save_model(model)` — saves to `artifacts/outfit_transformer.pt` via `torch.save`.
      All torch operations wrapped in `try/except`; if torch unavailable, `score_outfit` returns 0.5.
      Files: `backend/app/ml/outfit_compatibility_transformer.py`
      Verify: `python -m pytest tests/test_outfit_compatibility_transformer.py -x -q` (new tests written in item 3).

- [ ] 3. Write unit tests for `outfit_compatibility_transformer.py`.
      Tests cover:
      - `score_outfit` with 2–5 random 512-d embeddings returns a float in [0, 1].
      - `load_or_init` with missing artifact returns an untrained model without error.
      - `train_on_polyvore_style_data` runs 1 epoch on 4 positives + 4 negatives without error and moves the loss below the initial value after 10 epochs.
      - `save_model` writes the file and `load_or_init` reloads it successfully.
      No FashionCLIP download required; use `np.random.default_rng(0).normal(size=512)` as fake embeddings.
      Files: `backend/tests/test_outfit_compatibility_transformer.py`
      Verify: `python -m pytest tests/test_outfit_compatibility_transformer.py -x -q` — all new tests pass.

- [ ] 4. Create `backend/app/ml/preference_reward_model.py`.
      Implement `PreferenceRewardModel(nn.Module)` with:
      - MLP: `Linear(512,256) → ReLU → Dropout(0.1) → Linear(256,128) → ReLU → Linear(128,1)`.
      - Output is an unbounded scalar reward (no activation on final layer).
      - `train_from_feedback(feedback_pairs: list[tuple[list[np.ndarray], list[np.ndarray]]])` — Bradley-Terry pairwise loss: `L = -log(sigmoid(R(preferred) - R(rejected)))`; Adam lr=1e-4, 20 epochs; stores `self._trained = True` after successful training with ≥1 pair.
      - `predict_reward(embeddings: list[np.ndarray]) -> float` — mean-pools garment embeddings to a single 512-d vector, runs forward pass, returns raw scalar (unbounded).
      - Module-level `load_or_init(user_id: str) -> PreferenceRewardModel` — loads from `artifacts/reward_model_{user_id[:8]}.pt` if exists, else returns fresh model with `_trained=False`.
      - `save(self, user_id: str)` — saves to `artifacts/reward_model_{user_id[:8]}.pt`.
      All torch operations wrapped in `try/except`; `predict_reward` returns 0.0 if torch unavailable.
      Files: `backend/app/ml/preference_reward_model.py`
      Verify: `python -m pytest tests/test_preference_reward_model.py -x -q` (new tests in item 5).

- [ ] 5. Write unit tests for `preference_reward_model.py`.
      Tests cover:
      - `predict_reward` on a list of 3 random 512-d embeddings returns a Python float.
      - `load_or_init` with missing artifact returns a model with `_trained=False`.
      - `train_from_feedback` on 2 (preferred, rejected) pairs runs without error, sets `_trained=True`.
      - Bradley-Terry loss decreases over 20 epochs (loss_final < loss_initial).
      - `save` + `load_or_init` round-trip preserves the model weights (output identical on same input before and after reload).
      Files: `backend/tests/test_preference_reward_model.py`
      Verify: `python -m pytest tests/test_preference_reward_model.py -x -q` — all new tests pass.

- [ ] 6. Create `backend/app/ml/preference_dataset.py`.
      Implement two functions:
      **`get_outfit_embeddings(outfit, vector_store) -> list[np.ndarray]`**
      - `outfit` is an `Outfit` ORM object; `outfit.item_ids` is a `list[uuid.UUID]`.
      - Calls `vector_store.fetch_embeddings([str(iid) for iid in outfit.item_ids])`.
      - Returns a list of `np.ndarray` (512-d), one per item where an embedding was found; skips missing items.
      - Returns `[]` if `vector_store` is None or fetch fails.

      **`build_preference_pairs(db: Session, user_id: str, vector_store) -> list[tuple[list, list]]`**
      - Queries `RecommendationFeedback` joined with `Outfit` where `owner_id == UUID(user_id)`.
        Import: `from app.models.recommendation_feedback import RecommendationFeedback`
        Import: `from app.models.outfit import Outfit`
      - Liked = `rating IN ('like', 'worn')`; disliked = `rating == 'dislike'`.
      - For each (liked_outfit, disliked_outfit) pair, call `get_outfit_embeddings` for both; skip pairs where either returns an empty list.
      - Returns the list of `(preferred_embeddings, rejected_embeddings)` tuples.
      - Wraps all DB access in `try/except`; returns `[]` on any error.
      Files: `backend/app/ml/preference_dataset.py`
      Verify: `python -m pytest tests/test_preference_dataset.py -x -q` (new tests in item 7).

- [ ] 7. Write unit tests for `preference_dataset.py`.
      Tests use entirely in-memory fakes (no real DB, no Pinecone):
      - Create fake `Outfit` objects (just set `.item_ids = [uuid4()]`, `.owner_id`).
      - Create a fake `vector_store` that returns a dict `{str(item_id): [0.1]*512}`.
      - Fake a `db.query(...)` chain using monkeypatching or a simple mock object.
      Tests cover:
      - `get_outfit_embeddings` returns one array per item found in vector_store.
      - `get_outfit_embeddings` returns `[]` when vector_store returns empty dict.
      - `build_preference_pairs` with 1 liked and 1 disliked outfit returns 1 pair.
      - `build_preference_pairs` skips pairs where embeddings are missing.
      - `build_preference_pairs` returns `[]` when DB raises an exception.
      Files: `backend/tests/test_preference_dataset.py`
      Verify: `python -m pytest tests/test_preference_dataset.py -x -q` — all new tests pass.

- [ ] 8. Integrate DL scoring into `_node_finalize` in `recommendation_agent.py`.
      In `_node_finalize`, after computing `relevance_score` and before building `outfit_dict`, add a `dl_score` block:

      ```python
      dl_score = _compute_dl_score(state, current_outfit)
      ```

      Implement `_compute_dl_score(state, current_outfit) -> dict` as a module-level helper:
      - Fetches embeddings for items in `current_outfit` via `vector_store.fetch_embeddings(item_ids)` (using the module-level `vector_store` import already present).
      - Computes `transformer_compatibility` = `outfit_transformer_module.score_outfit(embeddings)` if embeddings non-empty, else `relevance_score`.
      - Reads `state.get("reward_model")` (a `PreferenceRewardModel` or None); if trained (`model._trained` is True), computes `preference_reward` = `sigmoid(model.predict_reward(embeddings))` (normalized to [0,1]); else `0.5`.
      - Returns dict: `{"transformer_compatibility": float, "preference_reward": float, "combined": alpha*tc + beta*pr, "alpha": 0.6, "beta": 0.4}`.
      - Entire function is wrapped in `try/except`; fallback returns `{"transformer_compatibility": relevance_score, "preference_reward": 0.5, "combined": relevance_score, "alpha": 0.6, "beta": 0.4}`.

      Add `"dl_score": dl_score` to `outfit_dict` (additive; all existing fields preserved).

      Module-level imports (top of file, guarded by `try/except`):
      ```python
      try:
          from app.ml import outfit_compatibility_transformer as outfit_transformer_module
          from app.ml.preference_reward_model import PreferenceRewardModel as _PRM
      except Exception:
          outfit_transformer_module = None
          _PRM = None
      ```

      Also add `"reward_model": None` to `RecommendationState` TypedDict (total=False, so optional).

      Files: `backend/app/agents/recommendation_agent.py`
      Verify: `python -m pytest tests/test_recommendation_agent.py -x -q` — all 16 existing tests still pass; also `python -m pytest tests/test_dl_integration.py -x -q` (new tests in item 9).

- [ ] 9. Add `_maybe_train_reward_model` and wire it into `run()`.
      Implement `_maybe_train_reward_model(state: RecommendationState) -> PreferenceRewardModel | None`:
      - Calls `build_preference_pairs(db, user_id, vector_store)` (import `from app.ml.preference_dataset import build_preference_pairs`).
      - If ≥1 pair exists: loads or inits a `PreferenceRewardModel` for this user, calls `train_from_feedback(pairs)`, saves the model, returns it.
      - Otherwise returns None.
      - Entire function wrapped in `try/except`; returns None on any error.

      In `run()`, before the `for i in range(top_k)` loop, call:
      ```python
      reward_model = _maybe_train_reward_model(base_state)
      if reward_model is not None:
          base_state["reward_model"] = reward_model
      ```

      Import at top of file (guarded):
      ```python
      try:
          from app.ml.preference_dataset import build_preference_pairs as _build_preference_pairs
      except Exception:
          _build_preference_pairs = None
      ```

      Files: `backend/app/agents/recommendation_agent.py`
      Verify: `python -m pytest tests/test_recommendation_agent.py -x -q` — all 16 existing tests still pass (reward model path is no-op when db=None and no preference_pairs available).

- [ ] 10. Write integration tests for the DL scoring pipeline in `recommendation_agent`.
       Tests cover:
       - `dl_score` key is present in every outfit dict returned by `RecommendationAgent.run()`.
       - `dl_score["alpha"] == 0.6` and `dl_score["beta"] == 0.4`.
       - When `outfit_transformer_module` is None (monkeypatched), `dl_score["transformer_compatibility"]` equals `relevance_score` (fallback).
       - When reward model is untrained, `dl_score["preference_reward"] == 0.5`.
       - `_maybe_train_reward_model` returns None when `db=None` (no DB session).
       Files: `backend/tests/test_dl_integration.py`
       Verify: `python -m pytest tests/test_dl_integration.py tests/test_recommendation_agent.py -x -q` — all tests pass.

- [ ] 11. Run the full test suite to confirm no regressions.
       Files: *(none — verification only)*
       Verify: `cd backend && .\venv\Scripts\python.exe -m pytest tests\ -x -q` — all tests pass (16 existing + new tests from items 3, 5, 7, 10).

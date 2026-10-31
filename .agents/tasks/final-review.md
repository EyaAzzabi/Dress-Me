# RecommendationAgent Enrichment Review

Implementation of FEAT-001 through FEAT-005: fine-tuning ranking, contextual RAG, and LLM integration into the DressMe RecommendationAgent.

## Summary

The implementation delivers a cohesive enrichment to the RecommendationAgent across three axes: a learned ranking model (LogisticRegression on visual + context fit with deterministic additive layer), contextual RAG (historical and catalog retrieval via vector store and catalog index), and LLM-powered occasion parsing and explanation (Mistral/OpenAI compatible). All components degrade gracefully when artifacts or services are absent, preserving the existing heuristic path as a byte-for-byte identical fallback. The orchestrator computes the context vector and RAG references once before the generate closure, avoiding duplicate work. Backward compatibility is maintained through optional kwargs, unchanged API signatures, and test isolation that forces the fallback path by default.

**Watch for**: (1) missing ranking artifacts mean the learned path is never exercised; (2) token-based occasion parsing still vulnerable to partial-word matches in compound tokens; (3) historical RAG groups with deleted items produce degraded outfit vectors; (4) explanation truncation at 2048 chars is silent.

**Verdict**: APPROVED

## High-level view

Ranking model follows voie A: LogisticRegression on two Polyvore‑computable features with four contextual signals added deterministically. The `context_vector` implements three‑branch fallback (specific → band‑agnostic → zero); missing artifacts return zeros. `score_outfit` returns the exact existing heuristic when artifacts absent or `RANKING_ENABLED=false`, never touching the artifact.

Contextual RAG retrieves historical outfits from `ScheduledOutfit` and `WearLog` grouped by date (excludes generated `Outfit` lacking wear date), each carrying its mean outfit vector to avoid re‑fetching Pinecone. Catalog search is cross‑modal (`category=None`) grouped by `dressme_category`. Both degrade to empty when Pinecone or catalog unavailable.

LLM integration adds `parse_occasion` and `explain_outfit` with `provider=="none"` guard before network calls. `occasion_parse_rules` uses token‑based matching (injective) avoiding substring false positives. `ContextAgent` enriches its return with `temperature`, `weather_band`, `occasion_category`, `formality`, `dress_code` while preserving legacy keys.

Integration wires the three axes: `RecommendationAgent.run` accepts `ctx_vec`, `references`, optional kwargs; `orchestrator.recommend_outfits` computes `ctx_vec` and `references` once before closure. `weather_band` derived from `temperature`, never a kwarg. Test isolation in `conftest.py` forces fallback path by default.

<details>
<summary>Issues (4)</summary>

1. **Missing ranking artifacts** — `ranking_model.joblib` and `context_vectors.npz` are not present in the artifacts directory. The implementation correctly falls back to the heuristic, but the learned path cannot be exercised without running the training notebook and passing the ship‑gate.
2. **Token‑based parsing still partial‑word vulnerable** — The token splitter (`[^\wàâäéèêëïîôöùûüç]+`) treats apostrophes as separators, so `"commercial"` becomes a single token and `"mer"` inside it won't match. However `"commercial"` does not appear in the keywords list, so the risk is limited to future keyword additions.
3. **Historical RAG degrades with deleted items** — When an item is deleted from Pinecone, its embedding is missing from `fetch_embeddings`. The outfit vector is computed only from present items, which may distort the historical reference. The code skips groups with fewer than 2 present embeddings.
4. **Explanation truncation silent** — LLM‑generated explanations longer than 2048 characters (the `Outfit.explanation` column length) are silently truncated without warning. The design folds adjustment suggestions into the explanation text, increasing the risk of overflow.

</details>

<details>
<summary>Details</summary>

### Ranking model: voie A with deterministic additive layer (FEAT-002)

`SEASON_COMPAT_BONUS` and `HISTORY_FIT_WEIGHT` fixed at 0.1, not learned (Polyvore lacks season/style labels). `compute_learned_features` returns only `visual`, `context_fit`; other four signals applied in additive layer.

Fallback heuristic replicates existing formula byte‑for‑byte: `min(1.0, visual + (STYLE_MATCH_BONUS if style_match else 0.0))` then `max(0.0, score - RECENT_WEAR_PENALTY * recent)`. `ranking_enabled` kill‑switch and missing‑artifact detection both route here without loading artifact.

`context_vector` three‑branch chain: (1) `f"{occasion}|{season}|{band}"` when both season and band given; (2) `f"{occasion}|{season}|_any"` when season given but band absent; (3) `zeros(512)` when season `None`. Out‑of‑vocabulary `occasion_category` falls back to `"casual_quotidien"`. Missing `context_vectors.npz` returns zeros with once‑per‑process INFO log.

### Contextual RAG: retrieval without new collection (FEAT-003)

Historical references from `ScheduledOutfit` (native date + item_ids) and `WearLog` grouped by date (one row per item/day); generated `Outfit` excluded (no wear date). Each reference includes `"vec"` field (mean of items' embeddings) satisfying review‑F4.

Catalog search passes `category=None` (global cross‑modal) grouped by `dressme_category`. No occasion‑to‑category mapping defined (review‑F6). Graceful degradation: Pinecone off → `fetch_embeddings` returns `{}` → `historical=[]`; catalog unavailable → `catalog={}`.

For `WearLog` groups with deleted items (review‑F10), keeps only items still present in Pinecone, skips groups with <2 present embeddings.

### LLM agent: provider‑none guard before network (FEAT-004)

`parse_occasion` and `explain_outfit` guard `if self.settings.llm_provider == "none": return None` first line, before any `_chat` call — no HTTP request when provider `"none"`, preserving `test_no_provider_returns_none_without_a_network_call` invariant (review‑F11).

`parse_occasion` validates `occasion_category` against `OCCASION_CATEGORIES`, `formality` against 1‑5. `dress_code` validated against small vocabulary (`_DRESS_CODE_VOCABULARY`); out‑of‑vocabulary value dropped to `None` not hard failure (review‑F8). Any error (HTTP, timeout, invalid JSON) logs warning, returns `None` → deterministic rules fallback.

`explain_outfit` returns `None` on failure → `RecommendationAgent` uses template `_explain`. Prompt builders (`prompts.py`) pure functions assemble messages, accept `context_hints` for disambiguation.

### Occasion parsing: token‑based injective mapping

Token splitter `[^\wàâäéèêëïîôöùûüç]+` splits on non‑word characters; `"commercial"` becomes single token `["commercial"]`, so `"mer"` inside it doesn't match — avoids false‑positive `"commercial"` → `"plage"` (review‑F3). Compound tokens cannot be matched by any keyword (fine because `"commercial"` not in keyword list). Risk remains for future short keywords that appear as substrings of legitimate compound tokens.

Cascade evaluation (first matching row wins) ensures one text → one category (injective, review‑F7). Fallback `"casual_quotidien"`. `weather_band` uses same thresholds as season helpers (`COLD_BELOW_C=14`, `HOT_FROM_C=24`).

### Orchestrator integration: ctx_vec computed once (FEAT-005)

`orchestrator.recommend_outfits` computes `weather_band` from `temperature`, `ctx_vec` from `ranking_model.context_vector` before `generate` closure. `references` retrieved once (if `contextual_rag_enabled`), passed to both potential `generate` calls — addresses review‑F1 (ctx_vec availability for RAG) and review‑F13 (avoiding duplicate RAG calls).

`RecommendationAgent.run` accepts `ctx_vec` kwarg; when `None` (direct calls/tests), derives `weather_band` and looks up `ctx_vec` itself. `weather_band` never a kwarg (review‑F3). Computes `context_fit`, `season_compat`, `history_fit` (using `vec` from references), passes to `ranking_model.score_outfit`. Exception during feature computation → heuristic for that outfit + warning, other candidates unaffected.

Explanation building (`_build_explanation`) truncates to 2048 characters (review‑F7). LLM agent injected + `explain_outfit` succeeds → uses LLM text; otherwise template kept, plus single weather‑based adjustment note on fallback path.

### Backward compatibility and test isolation

API signatures unchanged: `RecommendationAgent.run` gains optional kwargs (`season`, `temperature`, `weather`, `occasion_category`, `formality`, `references`, `ctx_vec`, `llm_agent`) + `**kwargs`. `ContextAgent.run` preserves legacy keys `occasion`, `weather`, `season` while adding new ones. `LLMAgent.run` still returns `{"explanation": ...}`.

`conftest.py` isolation mechanism (review‑F2): autouse fixture sets `RANKING_ENABLED=false`, `CONTEXTUAL_RAG_ENABLED=false`, `LLM_PROVIDER=none` via `monkeypatch.setenv` + `get_settings.cache_clear()`. `get_settings` `@lru_cache` → next call re‑reads environment. Ensures existing tests run fallback path regardless of artifacts or developer `.env`.

Tests verify fallback path (`test_recommendation_agent.py` keeps existing assertions), artifact‑present path (mocked sklearn classifiers/vectors), three‑branch `context_vector` fallback, token‑based occasion parsing, RAG grouping, LLM guards. `test_context_agent.py` assertions relaxed to subset checks (review‑F6).

### Gaps and trade‑offs

Ranking artifacts absent — learned path cannot be exercised without running training notebook and passing ship‑gate. Intentional: artifacts committed only if ship‑gate passes, preventing regression. Fallback heuristic ensures system works either way.

`SEASON_COMPAT_BONUS` and `HISTORY_FIT_WEIGHT` fixed at 0.1, not calibrated on relevance labels (none exist) — design acknowledges this, leaves fine calibration as backlog.

Catalog search uses `category=None` (global cross‑modal). No occasion‑to‑`dressme_category` mapping defined — results may mix categories, affects only LLM explanation not ranking.

Explanation truncation at 2048 characters silent; warning log could be added but isn't required.

</details>

<details>
<summary>File map</summary>

**FEAT‑001 (shared infra)**
- `backend/app/core/config.py` — `ranking_enabled` and `contextual_rag_enabled` kill‑switches (default `True`)
- `backend/app/services/occasions.py` — `OCCASION_CATEGORIES` (8), `weather_band()`, `parse_occasion_rules()` (token‑based, injective)
- `backend/tests/conftest.py` — `isolate_enrichment_flags` fixture (forces fallback path)
- `backend/app/rag/__init__.py` — package
- `backend/tests/test_occasions.py` — tests for occasion parsing and weather bands

**FEAT‑002 (ranking model)**
- `backend/app/ml/ranking_model.py` — `LogisticRegression` loader, `context_vector()` three‑branch fallback, `score_outfit()` with heuristic fallback
- `backend/tests/test_ranking_model.py` — unit tests for indexing, fallbacks, heuristic replication
- `ml/notebooks/10_ranking_model.py` — training notebook with ship‑gate (δ=+0.02 AUC)

**FEAT‑003 (contextual RAG)**
- `backend/app/rag/context_retrieval.py` — `retrieve_references()` using `ScheduledOutfit` + `WearLog` grouped by date, includes `vec` in historical entries
- `backend/tests/test_context_retrieval.py` — tests for historical grouping, catalog search, graceful degradation

**FEAT‑004 (LLM + prompts)**
- `backend/app/agents/prompts.py` — `occasion_parse_prompt`, `explain_outfit_prompt` (pure functions)
- `backend/app/agents/llm_agent.py` — `parse_occasion()`, `explain_outfit()` with `provider=="none"` guard before network
- `backend/app/agents/context_agent.py` — enriched with `temperature`/`weather_band`/`occasion_category`/`formality`/`dress_code`
- `backend/tests/test_prompts.py`, `test_llm_agent.py`, `test_context_agent.py` — extended tests

**FEAT‑005 (capstone integration)**
- `backend/app/agents/recommendation_agent.py` — uses `ranking_model` + RAG + LLM, optional kwargs, `weather_band` derived
- `backend/app/agents/orchestrator.py` — computes `ctx_vec` + `references` once before closure
- `backend/.env.example` — kill‑switch documentation
- `backend/tests/test_recommendation_agent.py` — extended tests (fallback and enriched paths)

**Full diff**: `git diff HEAD~5 HEAD` shows all changes across the 5 FEAT commits.

</details>
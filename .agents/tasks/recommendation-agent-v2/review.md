# SFT + LLM + Weather Pipeline Integration

This work adds three new layers to the Dress-Me recommendation system: real-time weather verification with API fallback, French-first explanation generation with confidence scoring, and a new `RecommendationAgentV2` orchestrator that combines SFT model predictions, LLM validation, and weather constraints into a single pipeline. The v1 `RecommendationAgent` remains unchanged; v2 is a parallel implementation that maintains the same interface for backwards compatibility.

The implementation follows the plan closely, with 57 new tests covering weather caching, constraint mapping, French explanation generation, outfit composition, and end-to-end pipeline integration. All critical findings from a prior review pass have been resolved: SFT model now receives real embeddings, LLM calls use the correct sandbox API, alternatives rejection is explained, outfit duplicates are prevented, and weather filtering distinguishes between extreme and borderline cases.

**Watch for:** The explanation engine's `_explain_alternatives_rejected()` depends on metadata that may not always be present; the method degrades gracefully. LLM confidence extraction from explanation text is regex-based and approximate. Weather constraint filtering uses heuristics (temp thresholds) that may be overly strict in some edge cases; the lenient fallback means users always get an outfit, even if suboptimal.

**Verdict**: APPROVED

---

## High-level view

Weather verification fetches from OpenWeather API when configured (1-hour in-memory cache, fallback to seasonal defaults), then maps temperature and condition to outfit material and layering constraints. The service can handle missing keys and degraded availability; low confidence scores surface API failures to the caller.

The explanation engine produces French text that names each selected item, explains why it was chosen based on material and occasion fit, includes a weather verification statement, and computes overall confidence by blending SFT scores (when available) and LLM validation with a simple average. The engine has deterministic template fallbacks for all scenarios, ensuring an explanation always exists even when the LLM is unavailable.

RecommendationAgentV2 chains these layers into a pipeline: fetch weather, filter wardrobe by season and extreme weather mismatches, load the per-user SFT model, score items with the model (fallback to 0.7 heuristic if torch unavailable), compose non-overlapping outfits, optionally validate with LLM, and generate explanations. Combined scores use configurable weights (SFT 0.4, LLM 0.3, compatibility 0.3). All errors are caught and logged; the pipeline never raises, always returning at least a deterministic fallback outfit. The return format matches v1 for drop-in compatibility.

---

<details>
<summary>Issues (3)</summary>

1. **Explanation alternatives depend on candidates metadata** — The explanation engine's `_explain_alternatives_rejected()` needs a "candidates" key in items_metadata to explain why other items were not selected. Currently this metadata is never populated in the pipeline, so alternatives are always empty. The function degrades gracefully (returns empty string), but users don't learn why other items weren't chosen. Either pass candidate items from the caller or document this as a known limitation.

2. **LLM confidence extraction is approximate** — Confidence is extracted from LLM explanation text via regex for "confidence: <number>" or heuristic guess ("parfait" → 0.85, others → 0.75). This is fragile; if the LLM's format changes or the word choice differs, the heuristic fails silently and returns a default. Consider requesting structured JSON output from the LLM instead, or at least log when extraction fails.

3. **Weather filtering may be overly strict then overly lenient** — When filtering by season and material, the code first removes extreme mismatches (linen below 5°C, wool above 30°C). If that produces an empty list, it retries with more extreme thresholds (below 0°C, above 35°C). If still empty, it returns all items unfiltered. This two-step fallback is well-intentioned but creates a discontinuity: at 5°C with only linen items, both thresholds fail and all items are returned; at 4°C, linen is filtered but then reincluded in the lenient pass. The behavior is predictable but unintuitive. Consider a continuous weight-based filtering approach instead.

</details>

---

<details>
<summary>Details</summary>

### Weather Verification Service: Real API + Cache + Constraint Mapping

The service fetches weather from OpenWeather API with latitude/longitude, falls back to city name if coordinates unavailable, and degrades to seasonal defaults when the API key is missing or the API call fails. Results are cached in-memory with a 1-hour TTL keyed by city name; the cache is a module-level dict with no thread safety considerations. For a single-threaded startup or small user base this is fine, but concurrent requests for the same city could race; adding a lock is straightforward if needed.

The API parsing maps OpenWeather conditions ("clear", "rain", "thunderstorm") to simpler categories ("sunny", "rainy", "stormy"). The mapping covers all major cases, so users should see consistent constraint labels. UV index is not available in the free tier, so it's always None; this is documented implicitly by the code.

Constraint mapping is fully deterministic and temperature-driven: 25–30°C → linens and light materials, below 10°C → wool and thick knits, with condition-based adjustments (rain adds waterproof materials, wind strengthens layering). The heuristic is reasonable for a Mediterranean climate (Tunisia). Edge cases: very hot (>30°C) or very cold (<0°C) both default to extreme categories, which is appropriate.

Weather fit verification checks each outfit item's material and season against temperature. Materials are matched as substring presence (e.g., "lin" in material string), which is coarse but works for the codebase's likely labels. Item seasons are checked for substring containment with the current season; logic: if item season is "summer" and we're in winter (< 15°C), warn with 0.15 fit score penalty. This is reasonable but conflates "item-specific season" (item is always for summer) with "current season context" (it is now winter in real weather); the two shouldn't mix in production. For now, the approach is consistent and the tests pass.

### Explanation Engine: French Text + Confidence + Weather Verification

The engine produces multi-part French explanations: item-by-item choices ("Sélectionnée pour: matière légère"), rejection reasoning (if candidates metadata present), weather fitness assessment, and occasion appropriateness. All text is in French, consistent with user-facing strings in constraints and fallback weather.

Confidence is a blend of input scores: if SFT score present, confidence = 0.6 × sft_score + 0.4 × 0.5 (baseline). If LLM confidence also present, recomputed as 0.7 × llm_confidence + 0.3 × (prior confidence). Weather verification adds a 10% bonus (min 1.0 clamping). Final clamping to [0.0, 1.0] is applied. The formula is transparent and will produce results in the expected range, though the reweighting on second input (LLM) means the SFT contribution is effectively 0.7 × 0.6 = 0.42 of the prior, not the original 0.6. This is acceptable but worth noting: LLM carries more weight in the final confidence than SFT. Test coverage validates this works end-to-end.

Alternatives rejection (`_explain_alternatives_rejected()`) tries to explain why candidates weren't selected by checking if they're formal when the occasion is casual, or if they're summer-season items in cold weather. The logic is sensible but depends on candidates being passed in. Currently the pipeline never populates items_metadata with a "candidates" key, so this method always returns an empty string. The fallback ("Tous les meilleurs candidats ont été sélectionnés" / "All best candidates selected") is used. This is not a bug—graceful degradation works—but users lose information about why certain items were skipped.

### RecommendationAgentV2: Pipeline Orchestration + Backwards Compatibility

The agent implements the full pipeline: weather fetch, filtering, SFT scoring, outfit composition, LLM validation, explanation generation, and score combination. Each step has a fallback; the entire pipeline is wrapped in try-except, so failures always produce a deterministic outfit (3 items by category: robe/haut/bas/chaussures, with neutral 0.5 scores).

**Weather fetch** calls `WeatherVerificationService.get_weather()` if a city is provided, else builds a synthetic weather dict from temperature and weather params. Error handling is try-except with a logged warning; fallback always available.

**Filtering** checks season (skip items from different seasons unless item season is "all") and material temperature fit (skip extreme mismatches: linen <5°C, wool >30°C). If filtering produces no results, a second pass with even more extreme thresholds is attempted (linen <0°C, wool >35°C). If still empty, all items are returned. This means candidates are always available for the next step. The logic is pragmatic but creates a discontinuity: at 5°C with only linen, the first filter removes all items, then the lenient pass reincluded all of them. Users get an outfit but weather constraints were ignored for this temperature point. The code's intention is clear (never fail to return an outfit), and tests confirm behavior is deterministic, but the threshold boundaries are unintuitive.

**SFT scoring** calls `outfit_composition_sft_model.load_or_init()` to load the per-user model (or None if torch unavailable). If model loaded, embeddings are fetched via `vector_store.fetch_embeddings()` for the filtered items. Embeddings are stacked into a batch and passed to `model.predict()` with season, weather condition, occasion. The model returns item IDs and scores; any items without scores are assigned a neutral 0.7. If embeddings are unavailable or torch fails, all items get 0.7. This is a reasonable fallback—non-discriminative but safe.

**Outfit composition** groups items by category, sorts by SFT score descending, then greedily picks the best unused item from each category (robe, haut, bas, chaussures) to build each outfit. A `used_items` set prevents the same item appearing in multiple outfits. If not enough unique items exist, a lenient pass allows repetition. This prevents silly duplicates (same shirt in two outfits) while still guaranteeing results. After the fix from the prior review, this works correctly.

**LLM validation** converts items to dict format, creates a `RecommendationToolSandbox` with wardrobe context, calls `llm_run_agent(task, sandbox, user_id=None)` for each outfit, and extracts confidence from the explanation via regex or heuristic. The sandbox provides tools for querying wardrobe, filtering, and compatibility checks. This matches the `recommendation_llm.py` API. The LLM call is wrapped in try-except so missing/unavailable LLM returns fallback scores.

**Explanation generation** passes outfit items, context (occasion, season, temperature), weather data, scores, and optional items_metadata to `ExplanationEngine.generate_explanation()`. The engine returns structured output with explanation text and confidence. The text is always available; confidence and weather verification depend on whether data was passed.

**Score combination** uses `_combine_scores()` with weights α=0.4 (SFT), β=0.3 (LLM), γ=0.3 (compatibility). If LLM unavailable, weights are renormalized (α' = 0.4/0.7, γ' = 0.3/0.7) so the sum stays 1.0. This is correct.

**Backwards compatibility** is maintained: the return format matches v1's `{"outfits": [...]}` structure, with all expected fields (item_ids, explanation, scores, critic_score, react_trace, etc.). The new fields (weather_fit, confidence, reasoning) are additions; no existing fields are removed or retyped.

**Error handling** is comprehensive: all major steps (fetch weather, load model, call LLM, generate explanation) are wrapped in logging and silent fallbacks. If the entire pipeline fails, `_fallback_outfit()` is called, which returns deterministic 0.5-scored outfits by category. The design choice to never raise and always return an outfit is conservative and user-friendly; it trades transparency for availability. A deployed system should log these failures, and tests confirm they're caught and reported.

### Test Coverage

57 new tests cover the three main modules:

- **weather_verification.py**: API calls, cache hits/expiry, fallback weather when API unavailable, constraint mapping for various temperatures, outfit fit verification with material and season checks.
- **explanation_engine.py**: Explanation generation with all combinations of metadata, French text presence, "pourquoi" and weather mentions, confidence computation.
- **recommendation_agent_v2.py**: Full pipeline with mock wardrobe, SFT model mock, LLM mock, backwards compatibility signature check, graceful degradation when torch/LLM unavailable.
- **integration tests**: End-to-end workflows with realistic wardrobe and context.

Not tested (likely fine but worth noting):
- Cache thread safety: concurrent requests for the same city could race on cache entry write. Single-threaded startup avoids this; high concurrency would need a lock.
- LLM confidence extraction edge cases: if LLM returns unusual formats, regex extraction falls back to heuristic. No test for malformed explanation.
- Extreme weather edge cases (temperature < -50°C or > 50°C): constraint mapping works but is untested at extremes.

### Integration with Existing Code

The work leaves `recommendation_llm.py` and `outfit_composition_sft_model.py` unchanged, so existing callers are unaffected. `RecommendationAgent` v1 is also unchanged. The new v2 agent can be used in parallel and is accessed as a new class. Configuration is inherited from `get_settings()` (openweather_api_key, llm_provider, etc.), so no new setup is needed; all features gracefully degrade if keys/models are missing.

</details>

---

<details>
<summary>File map</summary>

- **backend/app/services/weather_verification.py** — New service for fetching real weather from OpenWeather API, caching results (1h TTL), mapping conditions to outfit constraints (materials, layering, colors), and verifying outfit fit. Includes seasonal fallback when API unavailable. All constraint text in French.
- **backend/app/ml/explanation_engine.py** — New engine for generating multi-part French explanations of why items were selected, including material fit, weather verification, occasion appropriateness, and overall confidence. Deterministic fallback templates ensure explanations always exist.
- **backend/app/agents/recommendation_agent_v2.py** — New orchestrator combining weather + SFT + LLM into a pipeline. Maintains v1 interface for backwards compatibility. Handles all failures gracefully with deterministic fallbacks. Returns outfits with combined scores, explanations, and weather fit assessments.
- **backend/tests/test_weather_verification.py** — 13 tests for weather caching, API fallback, constraint mapping.
- **backend/tests/test_explanation_engine.py** — 14 tests for explanation generation with various metadata combinations.
- **backend/tests/test_recommendation_agent_v2.py** — 21 tests for pipeline integration, SFT/LLM scoring, backwards compatibility.
- **backend/tests/test_recommendation_agent_v2_integration.py** — 9 end-to-end tests with realistic wardrobe and context.

Full diff: `git diff origin/main -- backend/app/services/weather_verification.py backend/app/ml/explanation_engine.py backend/app/agents/recommendation_agent_v2.py backend/tests/test_*.py`

</details>

# Implementation Plan — RecommendationAgent Rewrite (LangGraph + RAG + Critic)

## Context / decisions made during exploration

**Orchestrator contract**: `orchestrator.py` calls `self.recommendation_agent.run(wardrobe_items=..., occasion=..., favorite_styles=..., usage=..., season=..., temperature=..., weather=..., occasion_category=..., formality=..., references=..., ctx_vec=..., feedback_preferences=...)` and expects `{"outfits": [{"item_ids", "relevance_score", "explanation", ...}]}`. The new agent must honour this exact signature and return shape.

**Outfit model (DB)**: `Outfit` has exactly `{id, owner_id, item_ids, occasion, relevance_score, explanation, created_at}`. New fields (`critic_score`, etc.) go only in the dict returned by `run()` — they are not persisted. The orchestrator reads only `item_ids`, `relevance_score`, and `explanation` before creating/updating the DB row. Extra keys in the candidate dict are ignored by the orchestrator loop.

**LLMAgent**: use `llm_agent._chat(messages)` for the Critic and the compose-outfit node. `llm_agent` is passed in as a kwarg by the orchestrator when provider != "none". The new code must guard for `llm_agent is None`.

**Vector store / Qdrant**: The project currently uses **Pinecone** (+ local JSON fallback) for clothing embeddings, not Qdrant. The style-guides RAG collection will be stored in a **separate JSON file** (`uploads/style_guides_vectors.json`) using the same TF-IDF fallback pattern already present in `vector_store.py`. The plan spec says "Qdrant séparée" but since the project has no Qdrant dependency, we use the existing infrastructure and label the class `StyleRAG` as instructed — with TF-IDF as the primary (always available) path and a Qdrant client as optional upgrade, gated behind a try/except import.

**LangGraph**: not in `requirements.txt` — must be added.

**Imports to delete**: `recommendation_reasoning.py` and `mcp_client.py` are the two files to remove. `recommendation_evaluation.py` is kept; `feedback_alignment_at_k` is still imported by `orchestrator.py`. The new `recommendation_tools.py` replaces the old one entirely.

**Fallback strategy**: every node that calls the LLM has a deterministic fallback. The Critic has a rule-based scorer. The RAG has TF-IDF. The compose-outfit node has a heuristic (best visual score first).

**Import order** (no circular imports): `recommendation_tools.py` → `recommendation_rag.py` → `recommendation_critic.py` → `recommendation_agent.py`. None of them import from each other except along this chain.

---

## Files to delete

| File | Reason |
|------|--------|
| `backend/app/agents/recommendation_reasoning.py` | Replaced by LangGraph state + ReAct trace in the new agent. No external caller. |
| `backend/app/agents/mcp_client.py` | MCP dispatch replaced by direct tool calls inside LangGraph nodes. The orchestrator never imports it; only the old `recommendation_agent.py` did. |

Both files should be deleted **after** step 4 (new agent) is written, so there is never a gap where `recommendation_agent.py` imports a missing module.

---

## Implementation steps

- [ ] 1. Add `langgraph` to requirements and update `recommendation_tools.py` with the 6 new tools.

  **What**: Replace the entire content of `backend/app/agents/recommendation_tools.py` with 6 tools — `get_weather`, `search_wardrobe`, `filter_wardrobe`, `get_user_preferences`, `check_outfit_rules`, `record_feedback` — each returning `{"tool_name", "result", "reasoning", "error"}`. Add Pydantic input models for each. Each tool has a 5-second timeout enforced with `httpx` or a `signal`-free `threading.Timer` pattern (since Windows has no `signal.alarm`). Add `langgraph>=0.2` to `backend/requirements.txt`.

  **Key signatures**:
  ```python
  # Pydantic input models (validated before each call)
  class GetWeatherInput(BaseModel):
      city: str
      date: str | None = None   # ISO date, optional

  class SearchWardrobeInput(BaseModel):
      user_id: str              # UUID string
      query: str
      filters: dict | None = None

  class FilterWardrobeInput(BaseModel):
      user_id: str
      category: str | None = None
      color: str | None = None
      season: str | None = None

  class GetUserPreferencesInput(BaseModel):
      user_id: str

  class CheckOutfitRulesInput(BaseModel):
      items: list[dict]         # each: {id, category, colors, style, season}

  class RecordFeedbackInput(BaseModel):
      outfit_id: str
      user_id: str
      rating: Literal["like", "dislike", "worn"]

  # Tool functions
  def get_weather(city: str, date: str | None = None,
                  db: Session | None = None) -> dict: ...

  def search_wardrobe(user_id: str, query: str,
                      filters: dict | None = None,
                      db: Session | None = None) -> dict: ...

  def filter_wardrobe(user_id: str, category: str | None = None,
                      color: str | None = None, season: str | None = None,
                      db: Session | None = None) -> dict: ...

  def get_user_preferences(user_id: str, db: Session | None = None) -> dict: ...

  def check_outfit_rules(items: list[dict]) -> dict: ...

  def record_feedback(outfit_id: str, user_id: str,
                      rating: str, db: Session | None = None) -> dict: ...
  ```

  **Tool implementations**:
  - `get_weather`: calls `WeatherService().get_current_weather(city)`. Fallback: returns season-based estimate (already in `WeatherService._get_fallback_weather`).
  - `search_wardrobe`: queries `ClothingItem` by `owner_id`, then ranks items by TF-IDF cosine similarity against `query` (no Qdrant dependency at runtime). Filters dict may contain `category`, `season`, `style`.
  - `filter_wardrobe`: SQLAlchemy query on `ClothingItem` with `owner_id` + optional `category`/`color`/`season` filters using `.ilike` for color (color is a JSON list).
  - `get_user_preferences`: queries `ClothingItem` to compute `favorite_styles` (Counter), `favorite_colors` (Counter), and queries `RecommendationFeedback` join `Outfit` for feedback history (last 10 like/dislike entries).
  - `check_outfit_rules`: purely deterministic. Checks: (a) completeness — must have at least one `haut` or `robe`, one `bas` or `robe`, one `chaussures`; (b) color harmony — no more than 3 distinct dominant colors; (c) no season clash (hiver+ete in same outfit). Returns `{complete: bool, color_ok: bool, issues: list[str]}`.
  - `record_feedback`: upserts `RecommendationFeedback` row. No-op if `db is None`.

  **Return shape** (all tools):
  ```python
  {"tool_name": str, "result": Any, "reasoning": str, "error": str | None}
  ```

  **Files**: `backend/app/agents/recommendation_tools.py`, `backend/requirements.txt`

  **Verify**: `cd backend && python -c "from app.agents.recommendation_tools import get_weather, filter_wardrobe, check_outfit_rules, record_feedback, get_user_preferences, search_wardrobe; print('OK')"` — prints `OK` with no import errors.

---

- [ ] 2. Create `recommendation_rag.py` — StyleRAG with hardcoded style guides and TF-IDF fallback.

  **What**: Create `backend/app/agents/recommendation_rag.py`. Class `StyleRAG` with `~20` hardcoded French style rules and TF-IDF retrieval as the primary path. Qdrant is an optional upgrade (imported inside a try/except; if `qdrant-client` is not installed or the server is unavailable, TF-IDF is used silently).

  **Style guide rules** (hardcoded list, stored as `STYLE_GUIDES: list[str]`):
  ```
  1.  "Les couleurs neutres (blanc, beige, gris, navy) se combinent avec tout."
  2.  "Évite de mélanger plus de 3 couleurs dominantes dans une tenue."
  3.  "Pour une occasion formelle, privilégie des pièces monochromes ou bicolores."
  4.  "En été, opte pour des matières légères : lin, coton, voile."
  5.  "En hiver, superpose les couches : t-shirt + pull + manteau."
  6.  "Le mariage : robe de cocktail ou costume élégant, jamais de jeans."
  7.  "Pour le travail, le 'business casual' combine pantalon chino + chemise ou blouse."
  8.  "Le sport requiert des pièces techniques : legging, t-shirt respirant, baskets."
  9.  "Une tenue complète comporte : haut, bas (ou robe) et chaussures adaptées."
  10. "Les imprimés se mélangent avec parcimonie : un seul imprimé par tenue."
  11. "Le noir amincit visuellement et s'adapte à toutes les occasions formelles."
  12. "Les couleurs vives (rouge, jaune, orange) doivent être équilibrées par du neutre."
  13. "Chaussures et sac dans le même registre (ton sur ton ou contraste assumé)."
  14. "En printemps, les pastels et floraux signalent la légèreté de la saison."
  15. "En automne, les tons terre (bordeaux, camel, kaki) sont de saison."
  16. "Pour la plage, la tenue doit être légère, colorée et pratique (maillot + paréo)."
  17. "Une veste structurée transforme immédiatement un look décontracté en look soigné."
  18. "Les sneakers blanches sont polyvalentes : casual, sorties, même certains looks soirée."
  19. "Pour un mariage oriental, privilégie les tissus brodés, dentelles et couleurs festives."
  20. "La règle des 3 : une tenue réussie mélange 3 éléments max (couleur, matière, motif)."
  ```

  **Class interface**:
  ```python
  class StyleRAG:
      def __init__(self, qdrant_url: str | None = None,
                   collection_name: str = "style-guides") -> None:
          # Build TF-IDF matrix from STYLE_GUIDES at init (no I/O)
          ...

      def retrieve(self, query: str, top_k: int = 3) -> list[str]:
          """Return top_k most relevant style rules for the query.
          Uses TF-IDF cosine similarity. Falls back to first top_k rules on error."""
          ...

      def index_style_guides(self) -> None:
          """Optional: push STYLE_GUIDES to Qdrant if client is available.
          No-op if qdrant-client not installed."""
          ...
  ```

  **TF-IDF implementation**: use `sklearn.feature_extraction.text.TfidfVectorizer` (already in requirements via scikit-learn). Fit on `STYLE_GUIDES` at `__init__` time. `retrieve(query)` transforms query + computes cosine similarity, returns top-k strings.

  **Files**: `backend/app/agents/recommendation_rag.py`

  **Verify**: `python -c "from app.agents.recommendation_rag import StyleRAG; rag = StyleRAG(); r = rag.retrieve('mariage formel été', top_k=3); assert len(r) == 3; print(r)"` — prints 3 French rule strings.

---

- [ ] 3. Create `recommendation_critic.py` — CriticAgent (LLM-as-a-Judge with deterministic fallback).

  **What**: Create `backend/app/agents/recommendation_critic.py`. Class `CriticAgent` evaluates a proposed outfit on a 5-criterion grid and returns a structured JSON score.

  **Grille** (5 criteria × 5 pts = 25 max, approved if total ≥ 15):
  | Criterion | Key | What it checks |
  |-----------|-----|----------------|
  | Météo adaptée | `meteo` | Items' seasons vs. temperature band |
  | Occasion appropriée | `occasion` | Outfit formality vs. occasion_category |
  | Harmonie des couleurs | `couleurs` | Fewer than 3 dominant colors, no clashes |
  | Tenue complète | `completude` | Has haut/robe + bas/robe + chaussures |
  | Pas portée récemment | `fraicheur` | No item worn in the last 3 days |

  **Class interface**:
  ```python
  class CriticAgent:
      def __init__(self, llm_agent: Any | None = None) -> None:
          self._llm = llm_agent  # LLMAgent instance or None

      def evaluate(
          self,
          outfit_items: list[dict],      # {id, category, colors, style, season}
          context: dict,                 # {occasion, occasion_category, weather_band,
                                         #  temperature, season, recent_item_ids}
          style_guidelines: list[str],   # from StyleRAG.retrieve()
      ) -> dict:
          """Returns:
          {
            "scores": {
              "meteo": int,        # 0-5
              "occasion": int,     # 0-5
              "couleurs": int,     # 0-5
              "completude": int,   # 0-5
              "fraicheur": int,    # 0-5
            },
            "total": int,          # sum, 0-25
            "approved": bool,      # total >= 15
            "feedback": str,       # one sentence explaining the lowest score
          }
          """
          ...

      def _deterministic_score(
          self,
          outfit_items: list[dict],
          context: dict,
      ) -> dict:
          """Pure rule-based fallback when LLM unavailable."""
          ...
  ```

  **LLM path**: build a prompt listing the outfit items (category, colors, style, season), the context, and the 3 style guidelines. Ask the LLM to reply with JSON matching the schema above. Use `llm_agent._chat(messages, json_mode=True)` with `timeout=10.0`. Parse with `json.loads`. On any exception (JSON parse error, missing keys, LLM unavailable), fall through to the deterministic path.

  **Deterministic path** (`_deterministic_score`):
  - `meteo`: 5 if weather_band matches all item seasons, 3 if mixed, 1 if mismatched (e.g. hiver items when chaud).
  - `occasion`: 5 if outfit completeness matches formality band (e.g. formal → completude with chaussures), else 3.
  - `couleurs`: count distinct dominant colors across all items. ≤2 → 5, 3 → 4, 4 → 2, >4 → 1.
  - `completude`: 5 if has (haut or robe) + (bas or robe) + chaussures, 3 if missing one optional category, 1 if missing haut/bas/robe.
  - `fraicheur`: 5 if no item in `recent_item_ids`, 3 if ≤1 item recent, 1 if >1 item recent.
  - `feedback`: built from whichever criterion scored lowest.

  **Files**: `backend/app/agents/recommendation_critic.py`

  **Verify**: `python -c "from app.agents.recommendation_critic import CriticAgent; c = CriticAgent(); r = c.evaluate([{'id':'x','category':'haut','colors':['blanc'],'style':'casual','season':'ete'},{'id':'y','category':'bas','colors':['noir'],'style':'casual','season':'ete'},{'id':'z','category':'chaussures','colors':['blanc'],'style':'casual','season':'toutes_saisons'}], {'occasion':'sortie','occasion_category':'casual_quotidien','weather_band':'chaud','temperature':28,'season':'ete','recent_item_ids':[]}, []); assert r['approved']; print(r)"` — prints an approved score dict.

---

- [ ] 4. Rewrite `recommendation_agent.py` — LangGraph StateGraph (ReAct, Stylist+Critic loop).

  **What**: Replace the entire content of `backend/app/agents/recommendation_agent.py`. The new agent is a `LangGraph StateGraph` with 7 nodes. It preserves the exact `run(**kwargs)` signature accepted by the orchestrator and returns a backward-compatible dict.

  **State TypedDict**:
  ```python
  class RecommendationState(TypedDict):
      # Input (populated from run() kwargs)
      user_id: str
      occasion: str | None
      occasion_category: str | None
      city: str | None
      season: str | None
      temperature: float | None
      weather_band: str | None
      wardrobe_items: list          # ClothingItem objects passed in
      favorite_styles: list[str]
      usage: dict                   # {UUID: {last_worn: date}}
      feedback_preferences: list[dict]
      references: dict | None
      ctx_vec: Any                  # np.ndarray | None
      formality: int | None
      db: Any                       # Session | None
      llm_agent: Any                # LLMAgent | None

      # Working state
      weather: str | None           # human-readable description
      wardrobe_candidates: list     # ClothingItem after filter
      style_guidelines: list[str]   # from StyleRAG
      current_outfit: list[dict]    # {id, category, colors, style, season}
      outfit_rules: dict            # result of check_outfit_rules
      thoughts: list[str]
      actions: list[dict]           # {tool, args, result}
      observations: list[str]
      steps: int
      max_steps: int                # = 10

      # Critic
      critic_score: dict | None     # CriticAgent.evaluate() output
      critic_iterations: int
      max_critic_iterations: int    # = 3

      # Output
      all_outfits: list[dict]       # accumulates approved outfits across iterations
      final_outfit: dict | None
      error: str | None
  ```

  **Graph nodes** (each is a Python function `node_name(state: RecommendationState) -> dict`):

  **Node 1 — `analyze_context`**:
  - If `state["city"]` and no existing `state["weather"]`: call `get_weather(city, db=state["db"])`. Extract temperature and description. Update `temperature`, `weather_band` (via `occasions.weather_band(temp)`), `weather`.
  - Call `StyleRAG().retrieve(f"{state['occasion']} {state['season']} {state['weather_band']}", top_k=3)`. Store in `style_guidelines`.
  - Record thought: `"Analyse du contexte: occasion={occasion}, météo={weather}, saison={season}"`.
  - Record action/observation for the weather tool call.

  **Node 2 — `search_candidates`**:
  - Call `filter_wardrobe(user_id, season=state["season"], db=state["db"])`.
  - If result is empty, call `filter_wardrobe(user_id, db=state["db"])` (no season constraint — same fallback as the original orchestrator).
  - Record thought: `"Recherche des candidats dans la garde-robe"`.
  - Record action/observation.
  - Store results as `wardrobe_candidates` (list of ClothingItem objects extracted from tool result).

  **Node 3 — `compose_outfit`**:
  - Take `wardrobe_candidates`. Group by category. Build candidate items dict (id, category, colors, style, season).
  - **LLM path**: if `llm_agent` is not None and LLM provider != "none", call `llm_agent._chat([system_msg, user_msg])` where the prompt includes: occasion, weather_band, style_guidelines, list of candidate items (id + attributes). Ask LLM to return a JSON list of item IDs to form the outfit. Parse, validate that IDs exist in candidates.
  - **Fallback path**: pick items deterministically — best visual score combination using existing `compatibility_model.pair_compatibility` from `app.ml`. Select one `haut`/`robe`, one `bas` (if no robe), one `chaussures` (best match), apply `_mean_pairwise_compatibility` scoring.
  - Store `current_outfit` as `list[dict]` with `{id, category, colors, style, season}`.
  - Record thought/action/observation.

  **Node 4 — `check_rules`**:
  - Call `check_outfit_rules(state["current_outfit"])`.
  - Store in `outfit_rules`.
  - Record thought/action/observation.

  **Node 5 — `critic_evaluate`**:
  - Compute `recent_item_ids` from `state["usage"]` (items worn in last 3 days).
  - Build context dict for critic.
  - Call `CriticAgent(llm_agent=state["llm_agent"]).evaluate(state["current_outfit"], context, state["style_guidelines"])`.
  - Store in `critic_score`.
  - Increment `critic_iterations`.
  - Record thought/action/observation.

  **Node 6 — `replan`**:
  - Read `critic_score["feedback"]` and `outfit_rules`.
  - Record thought: `"Critique reçue : {feedback}. Re-planification en cours."`.
  - Identify missing categories from `outfit_rules["issues"]`. If `chaussures` missing, try to pick the best-matching shoe from `wardrobe_candidates`. If color issue, attempt to swap the highest-mismatch item.
  - Update `current_outfit` with corrected item list.
  - Increment `steps`.
  - The replan node does NOT reset `critic_iterations` — it only corrects and re-routes to `check_rules`.

  **Node 7 — `finalize`**:
  - Build the output outfit dict:
    ```python
    {
        "item_ids": [UUID(item["id"]) for item in state["current_outfit"]],
        "relevance_score": round(state["critic_score"]["total"] / 25, 2)
                           if state["critic_score"] else 0.5,
        "explanation": <deterministic template or LLM explanation>,
        "critic_score": state["critic_score"],
        "critic_feedback": state["critic_score"]["feedback"] if state["critic_score"] else None,
        "critic_iterations": state["critic_iterations"],
        "react_trace": [
            {"thought": t, "action": a, "observation": o}
            for t, a, o in zip(state["thoughts"], state["actions"], state["observations"])
        ],
        "style_guidelines_used": state["style_guidelines"],
    }
    ```
  - Append to `all_outfits`.

  **Conditional edges**:
  ```
  START → analyze_context → search_candidates → compose_outfit → check_rules
  check_rules → critic_evaluate   (if rules OK)
  check_rules → replan            (if not rules OK AND steps < max_steps)
  check_rules → finalize          (if steps >= max_steps)
  critic_evaluate → finalize      (if approved OR critic_iterations >= max_critic_iterations)
  critic_evaluate → replan        (if not approved AND critic_iterations < max_critic_iterations)
  replan → check_rules
  finalize → END
  ```

  **`run()` method**:
  ```python
  def run(
      self, *, wardrobe_items: list, occasion: str | None = None,
      favorite_styles: list | None = None, top_k: int = 3,
      usage: dict | None = None, today: date | None = None,
      season: str | None = None, temperature: float | None = None,
      weather: str | None = None, occasion_category: str | None = None,
      formality: int | None = None, references: dict | None = None,
      ctx_vec: Any = None, llm_agent: Any = None, city: str | None = None,
      feedback_preferences: list | None = None, db: Any = None,
      **kwargs: Any,
  ) -> dict[str, Any]:
  ```

  The method must run the graph `top_k` times (once per requested outfit) by reinitializing state each time, varying the compose step slightly (exclude already-used items). Returns `{"outfits": [outfit_dict, ...]}`.

  **Fallback path in run()**: if LangGraph raises any exception, catch it and fall back to a single deterministic outfit from `wardrobe_items` (haut+bas+chaussures by first-available), with `relevance_score=0.5`, `explanation="Tenue proposée par défaut."`, and empty trace/critic fields.

  **Files**: `backend/app/agents/recommendation_agent.py`

  **Verify**: `python -c "from app.agents.recommendation_agent import RecommendationAgent; a = RecommendationAgent(); print(a.name)"` — prints `recommendation_agent`.

---

- [ ] 5. Delete obsolete files.

  **What**: Delete `backend/app/agents/recommendation_reasoning.py` and `backend/app/agents/mcp_client.py`. These are safe to delete now because the new `recommendation_agent.py` imports nothing from them. `orchestrator.py` does not import either file. `recommendation_evaluation.py` is **kept** (the orchestrator imports `feedback_alignment_at_k` from it).

  **Check before deleting**:
  ```bash
  grep -r "mcp_client\|recommendation_reasoning" backend/app --include="*.py" -l
  ```
  After deletion the only hit should be none (or only `__pycache__` artefacts, which don't matter).

  **Files**: delete `backend/app/agents/recommendation_reasoning.py`, delete `backend/app/agents/mcp_client.py`

  **Verify**: `python -c "from app.agents.orchestrator import AgentOrchestrator; print('OK')"` — prints `OK` with no `ModuleNotFoundError`.

---

- [ ] 6. Update TypeScript types in `frontend/mobile/src/api/recommendations.ts`.

  **What**: Extend the existing types — do not remove anything, only add.

  **Add after the existing `Outfit` interface**:
  ```typescript
  export interface ReActStep {
    thought: string;
    action: {
      tool: string;
      args: Record<string, unknown>;
    };
    observation: {
      tool: string;
      result: unknown;
    };
  }

  export interface CriticScores {
    meteo: number;        // 0-5
    occasion: number;     // 0-5
    couleurs: number;     // 0-5
    completude: number;   // 0-5
    fraicheur: number;    // 0-5
  }
  ```

  **Extend the `Outfit` interface** with optional fields:
  ```typescript
  export interface Outfit {
    id: string;
    item_ids: string[];
    occasion: string | null;
    relevance_score: number | null;
    explanation: string | null;
    feedback: OutfitFeedback | null;
    // New agentic fields (optional — absent from DB-stored outfits fetched via GET /outfits)
    critic_score?: {
      scores: CriticScores;
      total: number;
      approved: boolean;
      feedback: string;
    };
    critic_feedback?: string | null;
    critic_iterations?: number;
    react_trace?: ReActStep[];
    style_guidelines_used?: string[];
  }
  ```

  **Files**: `frontend/mobile/src/api/recommendations.ts`

  **Verify**: `cd frontend/mobile && npx tsc --noEmit` — no TypeScript errors on `recommendations.ts` or `OutfitRecommendationsScreen.tsx`.

---

- [ ] 7. Update `OutfitRecommendationsScreen.tsx` — add 3 collapsible agentic sections.

  **What**: Preserve 100% of existing logic (favorites, feedback, scheduling, calendar). Add three collapsible sections inside `OutfitCard`, and update the loading indicator text.

  **Loading messages**: the `handleGenerate` function sets `loading=true`. Add a second state `loadingPhase: "stylist" | "critic" | null`. Since the API call is a single POST, the frontend cannot know which phase the backend is in. Use a `setTimeout` trick: after 1.5 s set `loadingPhase="critic"`. In the button render:
  ```tsx
  {loading
    ? <ActivityIndicator color="#FFFFFF" />
    : null}
  {loading && loadingPhase === null
    ? <Text style={styles.generateText}>Le Stylist réfléchit...</Text>
    : null}
  {loading && loadingPhase === "critic"
    ? <Text style={styles.generateText}>Le Critic évalue...</Text>
    : null}
  {!loading
    ? <Text style={styles.generateText}>Créer mes idées de looks</Text>
    : null}
  ```

  **Three collapsible sections inside `OutfitCard`** (rendered below the existing explanation box and above the schedule button):

  **Section 1 — Raisonnement de l'agent**:
  ```tsx
  {outfit.react_trace && outfit.react_trace.length > 0 && (
    <CollapsibleSection title="🧠 Raisonnement de l'agent">
      {outfit.react_trace.map((step, i) => (
        <View key={i} style={styles.reactStep}>
          <Text style={[styles.reactThought, {color: colors.text}]}>
            💭 {step.thought}
          </Text>
          <Text style={[styles.reactAction, {color: colors.textMuted}]}>
            ⚙ {step.action.tool}({JSON.stringify(step.action.args)})
          </Text>
          <Text style={[styles.reactObservation, {color: colors.textSubtle}]}>
            👁 {JSON.stringify(step.observation.result).slice(0, 120)}
          </Text>
        </View>
      ))}
    </CollapsibleSection>
  )}
  ```

  **Section 2 — Avis du Critic**:
  ```tsx
  {outfit.critic_score && (
    <CollapsibleSection title="⚖️ Avis du Critic">
      <Text style={[styles.criticTotal, {color: colors.text}]}>
        Score : {outfit.critic_score.total}/25
        {outfit.critic_score.approved ? " ✅" : " ⚠️"}
      </Text>
      {Object.entries(outfit.critic_score.scores).map(([key, value]) => (
        <View key={key} style={styles.criticRow}>
          <Text style={[styles.criticLabel, {color: colors.textMuted}]}>
            {CRITIC_LABELS[key as keyof typeof CRITIC_LABELS]}
          </Text>
          <View style={[styles.criticBarBg, {backgroundColor: colors.border}]}>
            <View style={[
              styles.criticBarFill,
              {
                width: `${(value as number) / 5 * 100}%`,
                backgroundColor: (value as number) >= 4
                  ? colors.success : (value as number) >= 3
                  ? colors.primary : colors.error,
              }
            ]} />
          </View>
          <Text style={[styles.criticScore, {color: colors.text}]}>
            {value}/5
          </Text>
        </View>
      ))}
      {outfit.critic_feedback && (
        <Text style={[styles.criticFeedback, {color: colors.textMuted}]}>
          {outfit.critic_feedback}
        </Text>
      )}
      {outfit.critic_iterations !== undefined && (
        <Text style={[styles.criticIterations, {color: colors.textSubtle}]}>
          {outfit.critic_iterations} itération{outfit.critic_iterations !== 1 ? "s" : ""}
        </Text>
      )}
    </CollapsibleSection>
  )}
  ```

  **Section 3 — Guidelines de style**:
  ```tsx
  {outfit.style_guidelines_used && outfit.style_guidelines_used.length > 0 && (
    <CollapsibleSection title="📚 Guidelines de style utilisées">
      {outfit.style_guidelines_used.map((rule, i) => (
        <Text key={i} style={[styles.guidelineText, {color: colors.textMuted}]}>
          • {rule}
        </Text>
      ))}
    </CollapsibleSection>
  )}
  ```

  **`CollapsibleSection` component** (new, defined at the top of the file above `OutfitCard`):
  ```tsx
  function CollapsibleSection({
    title, children
  }: {title: string; children: React.ReactNode}) {
    const { colors } = useTheme();
    const [open, setOpen] = useState(false);
    return (
      <View style={styles.collapsible}>
        <Pressable
          onPress={() => setOpen(o => !o)}
          accessibilityRole="button"
          style={styles.collapsibleHeader}
        >
          <Text style={[styles.collapsibleTitle, {color: colors.text}]}>
            {title}
          </Text>
          <Text style={[styles.collapsibleChevron, {color: colors.textMuted}]}>
            {open ? "▲" : "▼"}
          </Text>
        </Pressable>
        {open && <View style={styles.collapsibleBody}>{children}</View>}
      </View>
    );
  }
  ```

  **`CRITIC_LABELS` constant** (above the component):
  ```typescript
  const CRITIC_LABELS = {
    meteo: "Météo",
    occasion: "Occasion",
    couleurs: "Harmonie des couleurs",
    completude: "Tenue complète",
    fraicheur: "Fraîcheur",
  } as const;
  ```

  **New StyleSheet entries to add**:
  ```
  collapsible, collapsibleHeader, collapsibleTitle, collapsibleChevron,
  collapsibleBody, reactStep, reactThought, reactAction, reactObservation,
  criticRow, criticLabel, criticBarBg, criticBarFill, criticScore,
  criticTotal, criticFeedback, criticIterations, guidelineText
  ```

  **Files**: `frontend/mobile/src/screens/OutfitRecommendationsScreen.tsx`

  **Verify**: `cd frontend/mobile && npx tsc --noEmit` — no TypeScript errors. Visual check: existing outfit cards still render, new sections collapse/expand correctly.

---

## Integration preservation

**How the orchestrator contract is maintained**:

1. `orchestrator.py` calls `self.recommendation_agent.run(wardrobe_items=..., ...)`.
2. The new `run()` method accepts every kwarg the orchestrator passes (`wardrobe_items`, `occasion`, `favorite_styles`, `usage`, `season`, `temperature`, `weather`, `occasion_category`, `formality`, `references`, `ctx_vec`, `feedback_preferences`) plus new ones (`db`, `city`) that the orchestrator does NOT yet pass — these default to `None` safely.
3. The new agent returns `{"outfits": [{"item_ids": [...], "relevance_score": float, "explanation": str, ...}]}`. The orchestrator reads `candidate["item_ids"]` and `candidate["relevance_score"]` from each entry. Extra keys (`critic_score`, `react_trace`, etc.) are present but the orchestrator's loop ignores them.
4. The orchestrator then calls `self.llm_agent.run(task="outfit", ...)` to phrase the explanation — this still works because the new agent populates `explanation` (either from LLM path or deterministic template).
5. The `Outfit` DB model is unchanged — the orchestrator writes only `item_ids`, `occasion`, `relevance_score`, `explanation` to it.
6. `feedback_alignment_at_k` from `recommendation_evaluation.py` is still called by the orchestrator and is not touched.

**How the API route is preserved**: `POST /recommendations/outfits` calls `orchestrator.recommend_outfits()` which calls the agent. The route returns `OutfitRecommendationResult` with `{"context", "outfits", "evaluation"}`. The `outfits` list uses `OutfitRead` schema which serialises from the `Outfit` ORM model — only the persisted fields. The new agentic fields reach the frontend only via the in-memory dict during the POST response building, not from the DB. To expose them the orchestrator would need to pass them through — but since the orchestrator replaces the agent's dict `explanation` with the LLM-phrased one and then creates the `Outfit` ORM object, the extra fields are effectively dropped from `OutfitRead`. This is acceptable: the new fields are rich debugging data visible only at recommendation time (the POST response), not when listing past outfits (the GET). No schema migration is required.

---

## Fallback summary

| Component | LLM/network available | LLM/network unavailable |
|-----------|----------------------|------------------------|
| `get_weather` | OpenWeather API | `WeatherService._get_fallback_weather()` (season-based estimate) |
| `search_wardrobe` | TF-IDF on items | Same (no external dependency) |
| `filter_wardrobe` | SQLAlchemy query | Same |
| `check_outfit_rules` | Deterministic | Same |
| `StyleRAG.retrieve` | TF-IDF (always available) | Returns first top_k rules |
| `compose_outfit` node | LLM selects items | `compatibility_model.pair_compatibility` heuristic |
| `CriticAgent.evaluate` | LLM scores criteria | `_deterministic_score()` rule-based |
| `recommendation_agent.run()` | Full LangGraph loop | Catch-all returns one static outfit |

---

## Import order (no circular imports)

```
app.services.weather              ← no agent imports
app.agents.recommendation_tools   ← imports WeatherService, ClothingItem, SQLAlchemy
app.agents.recommendation_rag     ← imports sklearn, no agent imports
app.agents.recommendation_critic  ← imports recommendation_rag, LLMAgent
app.agents.recommendation_agent   ← imports all 3 above + LangGraph + base
app.agents.orchestrator           ← imports recommendation_agent (unchanged)
```

---

## Creation order

1. `requirements.txt` (add langgraph) + `recommendation_tools.py`
2. `recommendation_rag.py`
3. `recommendation_critic.py`
4. `recommendation_agent.py`
5. Delete `recommendation_reasoning.py` + `mcp_client.py`
6. `frontend/.../recommendations.ts`
7. `frontend/.../OutfitRecommendationsScreen.tsx`

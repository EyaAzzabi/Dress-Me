# Final assessment — deliverables to-do list

Source: Islem Maiti's email, Advanced Data Science Project module. Four deliverables,
defended in Week 10 (exact date TBD — fill in below once known).

| Item | Date |
|---|---|
| Report + code submission | **TBD** (Blackboard, "j-1" before the defense) |
| Slides submission | **TBD** (before the defense) |
| Defense | **TBD** (Week 10, per group's chosen slot on the shared Excel sheet) |

Grading weights: problem statement & approach 20% · methodological rigor & technical
choices 30% · results & critical analysis 20% · code quality & reproducibility 15% ·
communication 15%.

## A. Technical report (≤ 25 pages)

Draft started at [`docs/FINAL_REPORT.md`](FINAL_REPORT.md), built from material already
in the repo (data-understanding results, Vision Agent evaluation, purchase-agent oral
prep notes, integration report). Remaining work, roughly in report order:

- [ ] Fill in exact submission/defense dates above once shared.
- [ ] **Problem statement section** — review the pulled-in personas/objectives table
  against the current app scope (some ideas, e.g. Virtual Try-On, shipped since the
  ideation doc was written — note that explicitly as a *scope change*, not an omission).
- [ ] **Data understanding section** — numbers are from `ml/reports/DATA_UNDERSTANDING_RESULTS.md`
  (56,532 items / 11 sources). Confirm these are still current (scraper counts may have
  grown) — rerun `ml/reports/generate_report.py` if any source changed.
- [ ] **Vision Agent section** — results table and methodology are already solid
  (`ml/reports/vision_agent_evaluation.md`, `docs/VISION_AGENT_EXPLICATION.md`). Mostly
  needs trimming to report length/English.
- [x] **Recommendation Agent section, numbers filled in.** Both notebooks were rerun for
  the report (§5): compatibility model accuracy 0.623 / F1 0.621 / AUC 0.675 vs. a naive
  baseline's 0.586 / 0.606 / 0.615; the contextual ranker's AUC delta is +0.007, below the
  notebook's own +0.02 ship-gate, so it was correctly **not** promoted to production.
  While rerunning `10_ranking_model.py`, a real O(outfits^2) performance bug was found and
  fixed (the random-assembly negative pool was rebuilt from scratch inside the per-outfit
  loop) — now committed as a code fix, not just a report number.
- [ ] **Purchase Agent section** — real, already-run numbers exist in
  `docs/fiche_orale_purchase_prof.html`: with the LoRA adapter, format 100%, tool-choice
  100%, **factual fidelity 0%** on 10 held-out cases (figures don't match tool outputs
  closely enough), all 10 traces follow an identical tool sequence. The base-model
  (no-adapter) comparison run is flagged there as not yet in the repo — run
  `python -m scripts.eval_purchase --mode base` from `backend/` and add that row before
  submitting, so the LoRA-vs-base claim in the report is backed by a real number, not
  just the LoRA side.
- [ ] **LLM/conversational agent section** — `INTEGRATION_REPORT.md` has real latencies,
  test counts, and documented failure modes (fabricated claim about a rendered try-on,
  now caught by a targeted check). Reuse directly, translate to English, keep the
  honesty about what the validation does and doesn't prove.
- [ ] **Critical analysis / limitations** — a first pass already exists, pulled from
  README "Where we are / what's next" + the Vision Agent Q&A + the purchase-agent oral
  notes' own "pièges" (traps/gotchas). Each team member should add one limitation from
  their own agent that isn't already listed.
- [ ] **Ethics / data section** — clothing photos are personal data; note consent
  (self-uploaded, own account), the LLM-agent's privacy note (photos never leave the
  server for the LLM path; only the optional GPT-4o-mini style call sends a photo to
  OpenAI, off by default), and that the Tunisian catalog scraping only used
  `robots.txt`-permitted public pages (checked per-site in `ml/README.md`).
- [ ] **Generative AI disclosure — required by the email, don't skip this.** State which
  tools were used (this report/to-do list was drafted with Claude Code; name whichever
  tools each teammate used for code, writing, or debugging) and for what parts. This is
  a compliance requirement, not boilerplate — the email explicitly says undisclosed use
  is treated as a violation.
- [ ] Page-count pass once all sections are in English and filled: target ≤ 25 pages,
  trim appendix-worthy detail (full scraper list, full test file list) into an appendix
  or just a repo link.
- [ ] Convert final Markdown to PDF for Blackboard submission.

## B. Code & repo (15% — quality + reproducibility)

- [x] `README.md` setup instructions confirmed consistent with current repo layout.
- [x] Root-level `backend/check_*.py`, `fix_*.py`, `reset_*.py`, and the 14 ad-hoc
  `test_*.py` files that were sitting outside `tests/` (not collected by pytest —
  `pytest.ini` restricts to `testpaths = tests`) have been moved into
  `backend/scripts/debug/` via `git mv`, with a short README explaining what the folder
  is. **Staged but not committed** — review `git status` and commit when ready.
- [ ] Backend suite: a plain `cd backend && python -m pytest tests -q` run genuinely
  hangs on `tests/test_dl_integration.py::test_dl_score_key_present_in_every_outfit`
  (and the next test in that file) — confirmed by running twice, with the run stalled at
  the exact same test both times with zero progress for several minutes. That test calls
  `RecommendationAgent().run(...)` with no LLM/network mocking, so it likely blocks on a
  real outbound call (LLM provider or Pinecone) that has no timeout when the relevant API
  key isn't set locally. **Action: whoever owns the Recommendation Agent should check why
  this specific test isn't mocked like its neighbors, and either mock it or skip it when
  the dependency is unavailable** (the same pattern the live-integration tests already use
  to self-skip without Postgres). A full run excluding just those two tests was still in
  progress when this was last checked — update this line with the final count once it
  lands.
- [x] `npx tsc --noEmit` clean on both `frontend/web` and `frontend/mobile`.
- [ ] Make sure `.env.example` files are current and no real secrets are committed
  (`backend/.env` is gitignored — double check it hasn't been accidentally tracked).
- [ ] Tag or branch the exact commit being submitted, so "the code we defend" is
  unambiguous during Q&A. **Do this after `git push` and after §5 of the report is
  rewritten for v2** (see B.6).

### B.6 Branch merge-status audit — `EyaRachdi_Recommendation` merged, `feature/Orchestrator_agent` deliberately NOT

`git fetch origin` + `git rev-list --count main..<branch>` for every branch in the remote,
checked before and after acting:

| Branch | Commits ahead of `main` | Status |
|---|---|---|
| `origin/Eya_Idi` | 0 | Fully merged |
| `origin/sarah/llm-agent` | 0 | Fully merged |
| `origin/tasnim_purchase` | 0 | Fully merged |
| `origin/vision-agent-improvements` | 0 | Fully merged |
| `origin/EyaRachdi_Recommendation` | was 19, now 0 | **Merged into `main`, commit `387e0a5`** |
| `origin/feature/Orchestrator_agent` | 2 | **Deliberately left unmerged — see below, do not merge as-is** |

**`EyaRachdi_Recommendation` — merged (local `main`, not yet pushed).** Brought in
**RecommendationAgentV2** (replaces the v1 LangGraph agent; `AgentOrchestrator` already
pointed to v2), a full **RLHF pipeline** (DB schema/migration, feedback+stats API, a PPO
policy training script, a frontend dashboard with star ratings — a different, larger RLHF
system than the Bradley-Terry `PreferenceRewardModel` the report's §5.1 currently
documents), a **Text-to-Speech** feature (`gTTS`, now in `requirements.txt`), and an
`RecommendationComposerLLM` with LoRA training support.

Four merge conflicts were resolved by hand (`backend/app/api/routes/__init__.py`,
`backend/app/models/__init__.py`, `frontend/web/src/App.tsx`, `frontend/web/src/styles.css`)
by keeping both sides' additions (the boutique/stylist feature already on `main` alongside
the new RLHF/TTS features) — nothing from either side was dropped. One real bug was fixed
in the process: the branch's own `App.tsx` had an `import { TTSSpeaker } ...` statement
accidentally nested inside another `import { ... } from "./api"` block, which is invalid
TypeScript; it's now a separate top-level import. The ~58MB of raw Polyvore JSON the
branch had committed directly (`polyvore_data/*.json`) was **not** brought into `main`:
untracked and added to `.gitignore`, consistent with `ml/data/raw/` already being
gitignored for the same reason. Verified post-merge: backend imports cleanly, 579 tests
collect with no errors (up from ~280 before), both frontends still present. This merge
also surfaced 15 more loose debug/training scripts at `backend/` root (the branch
reintroduced the same clutter pattern as the 34 already cleaned up in B.2) — sorted the
same way: throwaway ones to `backend/scripts/debug/`, the real SFT/RLHF training entry
points to `backend/scripts/`.

This branch still does **not** contain the MCP wiring, Purchase Agent fidelity fix, or
CalendarAgent raised earlier — those remain unverified anywhere in git.

**`feature/Orchestrator_agent` — checked and rejected, do not merge.** This branch is 41
commits *behind* `main` (diverged from a much older point in history). Merging it would
**delete 797,326 lines** of work that now only exists on `main` — LoRA training notebooks,
vision-prompt-version evaluation, the purchase-architecture diagrams, the TypeScript
rewrite of the frontend API client, and more — in exchange for 5,002 insertions (some
cloud-deployment and Android-build config that might be worth cherry-picking
individually, but not worth a full merge). If the cloud-deployment pieces are still
wanted, someone should extract just those specific files by hand rather than merging the
branch.

**Still open: rewrite report §5 for v2.** The report's Recommendation Agent section (§5.1
to §5.4) currently documents the v1 agent, which `main` no longer runs. This needs a
rewrite covering RecommendationAgentV2's actual architecture, the RLHF/PPO pipeline (and
how it relates to the Bradley-Terry model the report already describes), and the TTS
feature, plus updates to §3.1 (technology stack), §8 (limitations) and §11 (future work)
wherever they reference the old agent. Not done yet — flag to Claude/whoever continues
this report that it's the next step.

**Still open: push and communicate.** These two commits (`387e0a5`, `29de274`) are local
to this machine only — `git push` hasn't been run. Whoever has write access should push to
`origin/main` and tell the team the Recommendation Agent changed under them (anyone with a
local branch based on the old v1 agent will need to rebase).

## C. Slides (15' defense, part of the 15%/15% communication+rigor split)

- [ ] Not started. Suggested structure once the report content stabilizes: problem (1-2
  slides) → architecture (1) → per-agent methodology + results, one slide each for
  Vision/Recommendation/Purchase/LLM (4) → live demo cut-in or screenshots (2-3) →
  limitations & honest critical take (1-2) → next steps (1). That's ~12-14 slides for 15
  minutes.
- [ ] Assign who presents which agent — "each member must be able to answer questions on
  the entire project," per the email, so rehearse cross-agent questions too.
- [ ] Reuse the purchase-agent oral prep doc's Q&A style (`docs/fiche_orale_purchase_prof.html`)
  for the other three agents — it's a good template for anticipated-questions prep.

## D. Demo (deployed application)

- [ ] Decide what "deployed" means for the defense: live local run (docker compose) vs.
  an actual hosted deployment. `infra/docker-compose.yml` only runs Postgres + backend
  locally today — if a real deployment is expected, that's new infra work, not covered
  by the current repo.
- [ ] Prepare a seeded demo account (README says "no seed data" today — add a
  `seed_user.py`-driven demo wardrobe so the defense doesn't start from an empty closet).
- [ ] Rehearse the demo path once end-to-end: add photo → wardrobe → get recommendation →
  ask the LLM assistant → packing/purchase check, and time it so it fits inside the demo
  slot.
- [ ] Have a fallback (recorded screen capture) in case live Wi-Fi/API quota (Groq, HF
  try-on free tier) fails during the defense — the try-on provider has a documented free
  daily quota that can run out.

## Open gaps still remaining

1. Purchase-agent base-model (no LoRA) comparison not yet run/committed (§6.3 of the
   report states this plainly rather than hiding it).
2. MCP tool-calling path exists as a standalone demo (`demo_mcp.py`) but is **not** wired
   into the live Purchase Agent loop yet; be ready to say this precisely if asked, per the
   oral-prep doc's own framing.
3. Karim (retailer persona) has no corresponding feature; already identified and stated
   as a conscious scope decision (`docs/IDEATION_RATIONALE.md`, report §1.2).
4. Team names and per-member AI-tool-usage disclosure still need to replace the git
   branch handles in the report's Appendix B and the disclosure table in §10.
5. Current `main` backend test-suite count: rerun in progress for the report (§8.1);
   fill in once it finishes.

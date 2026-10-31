# Data dictionary — Fashion Product Images → `ClothingItem`

Maps the primary dataset's `styles.csv` columns to the backend's `ClothingItem` model
(`backend/app/models/clothing_item.py`), so Vision Agent output lines up with what the
API/database already expect.

| `styles.csv` column | Example values | Maps to `ClothingItem` field | Notes |
|---|---|---|---|
| `id` | `15970` | — | Links to `images/<id>.jpg`; not stored, only used during training |
| `masterCategory` | Apparel, Footwear, Accessories | — | Too coarse to use directly; kept for sanity-checking `subCategory` |
| `subCategory` | Topwear, Bottomwear, Shoes, Bags | — | Candidate for `category` if `articleType` is too fine-grained for the UI |
| `articleType` | Tshirts, Jeans, Sneakers, Handbags | `category` | Primary source for `category` — most useful granularity for wardrobe browsing |
| `baseColour` | Navy Blue, Black, White | `colors` (single-item list) | Dataset gives one dominant color; `ClothingItem.colors` supports multiple — may need a separate color-extraction pass (e.g. k-means on pixels) to get secondary colors |
| `season` | Summer, Winter, Fall, Spring | `season` | Direct match |
| `usage` | Casual, Formal, Sports, Ethnic, Party, Smart Casual | `style` | Direct match — treat `usage` as the `style` label |
| `productDisplayName` | "Turtle Check Men Navy Blue Shirt" | — | Free text, useful for an NLP/multimodal search feature later, not for structured fields |
| — | — | `pattern` | **Not present in this dataset — resolved via weak-labeling, see below.** |
| — | — | `material` | **Not present in this dataset — resolved via text extraction, see below.** |

## Open decisions to make during exploration

- Whether `category` should use `articleType` directly (many distinct values — check
  cardinality and long-tail classes) or a manually collapsed set of ~10-15 buckets.
- Whether `usage` values need remapping (e.g. merge "Smart Casual" into "Casual") to
  match the style vocabulary the Style Profile Agent will use.
- Minimum sample count per class to keep — drop or merge classes with too few images.

---

# `pattern` attribute — resolved via FashionCLIP weak-labeling

No source (Kaggle, any Tunisian scrape, Polyvore) has a ground-truth `pattern` field —
there's no dataset to download this out of. `ml/notebooks/07_pattern_weak_labels.py`
weak-labels it via FashionCLIP zero-shot classification instead, the same mechanism
already validated (with known, real error — see the FashionCLIP section below) for
category. **These are model-inferred labels, not ground truth** — saved separately at
`ml/data/processed/pattern_weak_labels.csv` (joinable by `item_key`), never merged
silently into the main catalog as if scraped fact.

Run on the full downloaded Tunisian image set: **8,929 items labeled.**

| Pattern | Count |
|---|---|
| uni (plain) | 3,520 |
| brode (embroidered) | 1,860 |
| geometrique | 1,107 |
| fleuri (floral) | 887 |
| rayures (striped) | 573 |
| imprime_animal | 426 |
| a_pois (polka dot) | 381 |
| carreaux (checkered) | 175 |

Mean confidence 0.731; 161/8,929 (1.8%) low-confidence (<0.3) predictions — filter these
out or treat as unreliable before using downstream. No ground truth exists to measure
real accuracy against (unlike category) — if `pattern` accuracy becomes important, the
actual fix is manual labeling of a sample, not a bigger model.

---

# `material` attribute — resolved via text extraction

No source has a dedicated material field either, but unlike `pattern`, fabric isn't
reliably distinguishable in a product photo via zero-shot CLIP (cotton vs. polyester vs.
viscose look too similar visually) — weak-labeling isn't a credible fix here.
`preprocessing.map_material()` instead extracts it from free-text product names/titles
via keyword matching (same approach as the category taxonomy's keyword fallback),
checked against real evidence first:

- Tunisian catalogs (9,208 names): cuir/leather 208, coton/cotton 186, laine/wool 108,
  satin 97, lin/linen 98, soie/silk 71, denim 63, dentelle/lace 59, velours/velvet 42.
- Polyvore (251k items, title/url_name): leather 25,624, lace 13,554, suede 10,148,
  denim 7,882, cotton 5,928, wool 5,542, silk 5,513, knit 5,376, velvet 3,214,
  cashmere 2,476.
- Kaggle (44,417 names): leather 723, lace 247, jersey 173, silk 144, cotton 137,
  denim 80, knit 78.

`"jean"`/`"jeans"` deliberately excluded from the keyword list — in French it names the
garment (already a `bas` category keyword), not reliably the fabric, unlike the
unambiguous `"denim"`.

**Result: 86,232/418,686 items (20.6%) get a material value.** (This text-extraction
approach was then reused for `color_family` too — see below, same method, different
vocabulary.) Coverage by source:
Chedly Sisters 27.1%, Polyvore 22.9%, Ileycom 11.6%, Kontakt 8.4%, Noonclo 6.7%, Kaggle
3.5%, Hamadi Abid 1.0%, Lyoum 0.5%, Barsha/MY JEBBA/Rooh Clothing 0%. The rest are
honestly `NaN`, not a bug — coverage is inherently partial since it only catches items
whose name happens to mention fabric. If fuller coverage matters later, the real fix is
manual labeling of a sample (same conclusion as `pattern`), not a bigger model.

---

# `color_family` — closing the Polyvore gap (`preprocessing.map_color_from_text`)

Kaggle and all nine Tunisian sources have a real `colors`/`baseColour` field (color
coverage 99.2-100%), but **the official Polyvore item metadata has no color field at
all** — `color_family` was `NaN` for all 365,054 Polyvore rows (87% of the catalog),
leaving the catalog-wide color coverage at only 12.8%.

Fixed the same way as `material`: `map_color_from_text()` extracts a color from the
Polyvore `title`/`url_name` text, reusing the **existing** `COLOR_FAMILIES` vocabulary
(the same one already validated on Kaggle/Tunisian `colors_raw` values) rather than
inventing a parallel list. A few entries from that vocabulary are excluded for free-text
matching specifically (`_TEXT_COLOR_EXCLUDE`): `"jeans"` names the garment, not
necessarily a blue one; `"raw"` and `"multi"` are common words unrelated to color in most
titles; `"skin"` is more often "skincare" in a fashion title than a color.

**Result: Polyvore color coverage 0% → 22.0%** (55,311/251,008 unique items), bringing
catalog-wide `color_family` coverage from 12.8% to **32.0%**. Distribution is sensible
(noir 20,077, blanc 9,417, rose 8,709, gris 7,842, bleu 7,760 — no single color
implausibly dominant). Like `material`, this is inherently partial — only items whose
title happens to mention a color get one — not a substitute for the full 100% coverage
a dedicated color field would give.

---

# Tunisian catalog → `ClothingItem` (Hamadi Abid + Barsha)

From `ml/data/raw/tunisian_catalog/{hamadi_abid,barsha}.csv` (see `ml/scraping/`).
715 products (Hamadi Abid) + 98 products (Barsha) scraped as of this pass.

| Scraped field | Example | Maps to `ClothingItem` field | Notes |
|---|---|---|---|
| `subcategory` (HA) / `source_url` slug (Barsha) | `t-shirt-fantaisie-mc`, `chaussures-femme` | `category` | 83 distinct subcategories in HA alone — same granularity-collapse decision as `articleType` above; the two taxonomies (Kaggle vs. scraped) must be reconciled into one shared vocabulary |
| `colors` (`;`-joined) | `BLACK;BEIGE;BROWN` | `colors` | Unlike Kaggle's single `baseColour`, this gives *all* available colors per product directly — richer, no color-extraction pass needed. 104 unique color names found in HA data alone; some normalization needed (`GREY` vs `GRAY`, `NAVY` vs `DARK BLUE`) |
| `price` / `price_current` + `price_original` | `"49,99 TND"`, `"59.310 TND" + "65.900 TND"` | — (not on `ClothingItem`, feeds Purchase Agent budget reasoning) | ~62% of HA products and most Barsha products found were on sale — `on_sale` flag is meaningful signal, not noise |
| `image_url` | `https://ha.com.tn/api/image/get/...` | `image_url` | All spot-checked URLs return HTTP 200; these are live CDN URLs, not permanent — re-verify before relying on them at deploy time |
| `section` (HA: femme/homme/fillette/garçon/bébé/ado) | — | — (context for age/gender targeting, not on the model directly) | Barsha covers Femme/Homme only (adult); combined the two brands give the full age range the brief asks for |

## Chedly Sisters → `ClothingItem`

From `ml/data/raw/tunisian_catalog/chedly_sisters.csv` (see `ml/scraping/scrape_chedly_sisters.py`).
269 products — a Shopify store, scraped via the public `/products.json` API (no browser
rendering needed, unlike HA/Barsha).

| Scraped field | Example | Maps to `ClothingItem` field | Notes |
|---|---|---|---|
| `name` | `"The Sahar Dress"`, `"Taupe Lace Whisper Scarf"` | `category` (via `map_keywords`, no direct category field) | Shopify's `product_type` is generic plumbing ("simple"/"variable"), not a garment category — titles are descriptive English names instead, so the existing Polyvore-style keyword fallback applies directly |
| `colors` (`;`-joined) | `Butter Yellow;Turquoise Blue;truffle` | `colors` | Extracted from Shopify variant options named Color/Colour/Couleur; 269/269 products have at least one color |
| `price_current` / `price_original` | `143.4`, `239.0` | — (Purchase Agent budget reasoning) | Min price across variants; many products on sale (`compare_at_price` present) |
| `image_url` | `https://cdn.shopify.com/s/files/...` | `image_url` | Shopify CDN — stable, not a temporary/signed URL unlike Polyvore's |

**Keyword vocabulary extended** from testing this source: added `polo`, `sweatshirt`,
`pullover`, `knit` → `haut`; `puffer` → `veste`; `abaya` → `robe`; `chino` → `bas`. Fixed
a real gap (`"sweatshirt"` doesn't contain a space before `"shirt"`, so the existing
`"shirt"` keyword never matched compound words — needed its own entry). This also
improved Polyvore's keyword fallback for free (shared list): `hors_perimetre` dropped
753→735. Deliberately skipped: generic `"set"` and bare `"robe"` (English "robe" usually
means bathrobe, not dress) — too ambiguous/risky for a shared keyword list, left as
`hors_perimetre` rather than guessed.

## Noonclo → `ClothingItem`

From `ml/data/raw/tunisian_catalog/noonclo.csv` (see `ml/scraping/scrape_noonclo.py`).
90 products — same Shopify mechanism as Chedly Sisters, now shared via
`ml/scraping/shopify_common.py`.

**Real finding**: Noonclo's titles are almost entirely French ("Pantalon Cargo Jogger",
"Jean Baggy Droit"), and `KEYWORDS_TO_DRESSME` was English-only — 56% of items landed in
`hors_perimetre` before any fix. Extended with French terms: `pantalon`, `jean`, `jupe`,
`short` → `bas`; `chemise`, `pull`, `sweat` → `haut`; `manteau`, `kimono`, `surchemise`
→ `veste`. Also found `sac` (French for "bag") was missing from the **`sac` category's
own keyword list** — an oversight from when the list was built English-only. After
fixing: 98.9% in-scope (up from ~44%). Benefits any future French-titled source, not
just Noonclo.

## Kontakt, Lyoum, Rooh Clothing → `ClothingItem`

Three more Shopify sources, all explicitly named in the project's own architecture deck
(`docs/`) as target Tunisian brands, scraped via the same `ml/scraping/shopify_common.py`
mechanism. See `ml/scraping/scrape_{kontakt,lyoum,rooh_clothing}.py`.

| Source | Products | In-scope | Notes |
|---|---|---|---|
| **Kontakt** (kontakt.com.tn) | 3,063 | 76.4% | By far the largest Tunisian source. Word-frequency analysis over unmapped items (not guesswork) drove adding `robe`, `body`, `débardeur`, `jogger`, `bombers`, `legging`, `cargo`, `collier` to the keyword list |
| **Lyoum** (lyoum.co) | 186 | 59.7% | A lifestyle concept-store, not pure clothing (notebooks, beach towels/*fouta* also sold) — a real `hors_perimetre` rate here is partly expected, not all a keyword gap. Added `cabas` (tote bag) and `t-loose` (Lyoum's own loose-tee product line name) |
| **Rooh Clothing** (rooh-clothing.com) | 9 | 0.0% | Small/new storefront; all 9 products use ambiguous "Set" naming (e.g. "Essential Woven Set") deliberately not guessed — an honest result, not a bug |

**The `robe` keyword decision, revisited**: earlier (Chedly Sisters) we deliberately
skipped bare `"robe"` as too ambiguous (English "robe" = bathrobe, not dress). Kontakt's
word-frequency data (103 occurrences, almost all genuine dresses: "Robe portefeuille",
"Robe imprimée"...) justified reversing that decision — real evidence across multiple
French-titled Tunisian catalogs outweighs a hypothetical English-brand edge case for
*this* project's actual data mix. Trade-off acknowledged: a few genuine nightgowns
("Robe de pyjama") now misclassify as `robe` instead of `hors_perimetre` — net positive,
not risk-free.

## MY JEBBA, Ileycom → `ClothingItem`

Traditional Tunisian attire — fills a style gap none of the contemporary/casual brands
above cover. See `ml/scraping/scrape_{myjebba,ileycom}.py`.

| Source | Products | In-scope | Notes |
|---|---|---|---|
| **MY JEBBA** (myjebba.com) | 34 | 100.0% | All traditional jebbas. `"jebba"` itself was missing from `KEYWORDS_TO_DRESSME` entirely — every product failed before the fix (8.8% → 100%) |
| **Ileycom** (ileycom.tn) | 4,744 | 26.1% | **Largest single source found.** Surfaces in jebba searches, but is actually a broad Tunisian artisan marketplace — prickly-pear jam, vinegar, home decor, oil paintings, daily planners, alongside some jebbas/jewelry. The low in-scope rate is a real reflection of that mix, not a keyword gap worth chasing further |

## ✅ Taxonomy reconciled — `ml/src/preprocessing.py`

The three-taxonomy problem above is resolved. `ml/src/preprocessing.py` (ported from the
team's own notebook and extended with `map_hamadi_abid` / `map_barsha` /
`map_chedly_sisters` / `map_noonclo` / `map_kontakt` / `map_lyoum` / `map_rooh_clothing` /
`map_myjebba` / `map_ileycom`) maps **every** source — Fashion Product Images, Hamadi
Abid, Barsha, Chedly Sisters, Noonclo, Kontakt, Lyoum, Rooh Clothing, MY JEBBA, Ileycom,
and Polyvore — into one shared 7-category DressMe vocabulary:
`haut, bas, robe, veste, chaussures, sac, accessoire` (+ `hors_perimetre` for
underwear/home textiles/perfume/lifestyle goods, correctly excluded).

Verified end to end via `ml/notebooks/04_taxonomy_reconciliation.py`, which reads
directly from `ml/src/catalog.py`'s unified builder (single source of truth — both this
notebook and `ml/reports/generate_report.py` pick up new sources automatically; adding a
source to `catalog.py` is the only place that needs touching). In-scope rate per source:
Fashion Product Images 87.5% (matches the team's own 87.3% finding), Hamadi Abid 93.3%,
Barsha 95.9%, Chedly Sisters 89.6%, Noonclo 98.9%, Kontakt 76.6%, Lyoum 60.8%, Rooh
Clothing 0.0% (expected, not a bug), MY JEBBA 100.0%, Ileycom 26.1% (expected — broad
artisan marketplace, see above), Polyvore sample 75.0% (lower due to granular category
names plus the known non-fashion contamination). Chart:
`ml/reports/04_taxonomy_reconciliation.png`.

## ✅ Color normalization reconciled

`COLOR_FAMILIES` in `ml/src/preprocessing.py` now also covers the Tunisian catalog's
vocabulary (French names like `NOIR`/`BLANC`/`MARRON`, denim-wash descriptors like
`JEANS STONE`/`BLEACH`, compound shades like `LIGHT BLUE`/`ROSE BEBE`). Verified against
the real data: 280/813 Tunisian items were unmapped (`autre`) before this fix, 1/813
after (`HARD DIRTY` — genuinely unidentifiable, correctly left as `autre` rather than
guessed). 6 scraped "colors" (`PARFUM`, `PACK 1/2`) were actually data artifacts, not
colors — now honestly `NaN` instead of silently misclassified.

## ✅ `color_family` decision resolved

**Decision**: `color_family` stays a single normalized primary color (matches Kaggle's
single-value convention, simplest for the Vision Agent's classification task). The full
multi-color list is **not lost** — `colors_raw` already preserves it (`;`-joined, e.g.
`"BLACK;BEIGE;BROWN"`) for every Tunisian source. `ClothingItem.colors` should store
`colors_raw` split into a list (richer, matches what the scrapers actually captured);
`color_family` (derived from just the first/primary color) is what feeds classification
and embeddings. No information is thrown away — it's a "which field for which purpose"
decision, not a data-loss tradeoff.

---

# Outfit compatibility data (official Polyvore Outfits, via Hugging Face)

From `ml/data/raw/polyvore_official/` — **365,054 items / 68,306 outfits**, the full
dataset (`nondisjoint_default` split: 53,306 train / 5,000 valid / 10,000 test outfits).
Replaces the earlier partial sample (`polyvore_sample.csv`, 2,900 items / 596 outfits,
rate-limited). See `ml/src/polyvore_official.py` and `ml/scraping/download_polyvore_official.sh`.
Feeds the **Recommendation Agent**, not `ClothingItem` directly.

| Field | Notes |
|---|---|
| `set_id` | Groups items curated together — the positive-pair signal for compatibility training |
| `position` | Item's position within the outfit; not otherwise meaningful |
| `category` | Semantic category (`tops`, `bottoms`, `all-body`, `outerwear`, `shoes`, `bags`, `jewellery`, `accessories`, `sunglasses`, `hats`, `scarves`) — maps directly via `POLYVORE_CATEGORY_TO_DRESSME`, with the shared keyword fallback for anything else |
| `title` / `url_name` | Free-text product name — usable for multimodal/text search later |
| `image` | Embedded in the parquet shards (not pre-extracted to individual files); `extract_image_bytes()` materializes any one item's image on demand |

**Data quality finding carried over from the earlier partial-sample exploration**:
Polyvore was a general mood-board site, not exclusively fashion — some outfit sets
include non-fashion items (home decor, food, toys). `map_polyvore()` routes anything
that doesn't match a DressMe category (via `category` or the text keyword fallback) to
`hors_perimetre` rather than guessing, consistent with how every other source handles
out-of-scope items.

---

# FashionCLIP zero-shot validation — Tunisian catalog photos

Your teammates validated FashionCLIP zero-shot classification on Fashion Product Images /
Clothing Dataset Full / Polyvore (F1 0.73–0.98 per category, see their notebook). This
section closes the gap they didn't test: does it generalize to the Tunisian catalog
photos (Hamadi Abid + Barsha) specifically? Run via
`ml/notebooks/06_fashionclip_tunisian.py`, 761 in-scope images (`hors_perimetre` excluded
— no matching prompt class), ground truth from the already-verified taxonomy mapping.

**Result: 62% accuracy, 0.55 macro F1 — a real, measured domain gap, not a clean pass.**

| Category | Tunisian F1 | Teammates' Kaggle/ClothingFull F1 | Confusion |
|---|---|---|---|
| chaussures | **1.00** | 0.98 | None — perfect, shoes transfer flawlessly |
| bas | 0.67 | 0.96 | 186/225 correct, some bleed to haut/robe |
| sac | 0.60 | 0.87 | 14/14 real bags correct, but accessoire items leak into it |
| accessoire | 0.62 | — | Splits across correct/bas/sac |
| haut | 0.52 | 0.91 | **117/262 misclassified as "bas"** — biggest single failure |
| robe | 0.30 | 0.73 | Only 24/63 correct; more called "haut" (32) than "robe" |
| veste | **0.17** | 0.80 | Nearly broken — 12/21 called "robe", 5/21 called "bas" |

**Root causes identified, not just numbers:**
1. Shoes are visually unambiguous regardless of photography style → perfect transfer.
2. `veste`/`robe` failures partly trace back to our own taxonomy mapping choices:
   `costume` (suit), `tablier-ecolier` (school smock), `grenouillere`/`body-ml` (baby
   onesies), and `ensemble-*` (coordinated 2-piece sets) were mapped to `veste`/`robe`
   for taxonomy consistency, but don't visually resemble FashionCLIP's training notion
   of "a jacket" or "a dress" — these items make the *ground truth* debatable, not just
   the model wrong.
3. The `haut`↔`bas` confusion is harder to explain that way — likely a genuine
   photography-style gap (flat-lay/folded product shots vs. the hanger/mannequin shots
   FashionCLIP trained on).

**Implication for the Vision Agent**: zero-shot FashionCLIP is production-ready for
shoes, usable-with-caution for tops/bottoms/bags, but **not reliable as-is for
jackets/dresses on Tunisian photos**. Fine-tuning on the labeled Tunisian + Kaggle data
(not pure zero-shot) is now a justified next step. Chart:
`ml/reports/06_fashionclip_tunisian_confusion.png`.

---

# Linear-probe classifier — closing the veste/robe gap (`08_category_classifier.py`)

Once all ~8,925 Tunisian product photos were downloaded locally (see image download
status below), a logistic-regression head was trained on top of FashionCLIP's **frozen**
embeddings (no vision-encoder fine-tuning, CPU-feasible) using the catalog's stratified
`split` column. Run on 4,636 in-scope, locally-available items (3,204 train / 735 test;
7 fewer than an earlier pass after `grenouillere`/`tablier-*` were reclassified to
`hors_perimetre`, see the taxonomy follow-up below).

| Category | Zero-shot F1 (06, 761 photos) | Linear-probe F1 (08, 4,636 photos) |
|---|---|---|
| veste | 0.17 | **0.69** |
| robe | 0.30 | **0.71** |
| haut | 0.52 | 0.83 |
| sac | 0.60 | 0.89 |
| accessoire | 0.62 | 0.94 |
| bas | 0.67 | 0.71 |
| chaussures | 1.00 | 0.90 |

Macro F1 0.55 → 0.81, accuracy 62% → 81%.

**This same trained classifier (retrained on all 4,636 labeled items, not just the
train split) is saved to `ml/data/processed/category_classifier.joblib` and is the
artifact `backend/app/agents/vision_agent.py` actually loads** — see the backend
integration section at the end of this file.

**Finding: the veste/robe weak spots were a prompting problem, not an embedding-quality
ceiling.** FashionCLIP's frozen features already separate these categories well enough
for a simple linear head to recover most of the gap zero-shot prompting missed, at zero
GPU cost. veste and robe are still the weakest categories (~0.7) — more likely explained
by the residual taxonomy-mapping ambiguities (suits, kimono, coordinated sets still
mapped to veste/robe for taxonomy consistency but visually atypical — the clearest
mismatches, baby onesies and school smocks, were already fixed; see the taxonomy
follow-up above) than a genuine model limitation. **Full fine-tuning of the vision encoder
(GPU-dependent) is no longer the clear next step** — the linear probe already closes
most of the practical gap for the Vision Agent, cheaply and reproducibly.

**Shipped artifact trains on 8 classes, not 7 — `hors_perimetre` included, on purpose,
despite a real cost.** Without it, the Vision Agent would always have to guess a real
garment category even for a non-clothing photo (haircare bottles, jewelry boxes,
perfume — 4,296 locally-available items, the single largest class). Including it:
macro F1 0.81 → 0.74, accuracy 81% → 79%, veste 0.69 → 0.60, robe 0.71 → 0.64
(`hors_perimetre` is a visually heterogeneous "everything else" bucket that overlaps
more with the already-weakest categories). In exchange, `hors_perimetre` itself scores
0.86 F1 (97% precision / 77% recall) — when it says "not clothing" it's almost always
right. For a wardrobe app, catching garbage uploads outweighs the marginal
category-precision cost, so this version is what's actually saved and shipped.

**Taxonomy follow-up, acted on**: of the ambiguous items flagged above, `grenouillere`
(baby onesie, 3 items) and `tablier-college`/`tablier-ecolier` (school smock, 4 items)
were clear mismatches — neither adult fashion nor visually similar to robe/veste — and
have been moved to `hors_perimetre` in `HAMADI_ABID_SUBCATEGORY_TO_DRESSME`. `costume`
(suit), `kimino`, and the `ensemble-*`/`jogging` coordinated-sets entries were left as
documented tradeoffs: a suit's jacket component is a reasonable visual match for veste,
and there's no single DressMe category that fits a photographed 2-piece coordinated
outfit better than `robe`'s existing "apparel set" convention without splitting each into
two separate rows — a larger schema change not justified by the small counts involved
(≤28 items per subcategory).

---

# Backend integration — the Vision Agent is no longer a stub

Everything above was, until this point, validated only inside `ml/` (notebooks, reports)
— the backend's `VisionAgent.run()` just raised `NotImplementedError`. It now actually
runs this pipeline:

- `backend/app/ml/vision_model.py` — self-contained FashionCLIP inference (loads
  `patrickjohncyh/fashion-clip` directly from Hugging Face, same as `ml/src/features.py`
  but duplicated rather than imported, since `backend/` is built as its own Docker image
  — see `infra/docker-compose.yml` — and doesn't include the `ml/` folder).
- `backend/app/ml/artifacts/category_classifier.joblib` — a **copy** of
  `ml/data/processed/category_classifier.joblib` (the 8-class artifact described above).
  Re-copy this file by hand after retraining in `ml/` — there's no automated sync.
- `backend/app/agents/vision_agent.py` — fetches `image_url` via `httpx`, runs
  `vision_model.analyze_image()`, and best-effort upserts the embedding to Pinecone
  (skipped gracefully if `PINECONE_API_KEY` isn't configured — still returns
  category/colors/pattern/style either way).

Verified end-to-end against real images: 5/5 correct category on a diverse Tunisian
sample including the historically weak veste cases (poncho, baby bomber jacket), and
5/8 correct on a held-out `hors_perimetre` sample (consistent with the reported 77%
recall — small-sample variance; genuinely ambiguous misses like a "chic pouch" item
visually resembling a bag).

Since this was written, `PurchaseAgent`, `RecommendationAgent`, `StyleProfileAgent`,
`LLMAgent`, and `ContextAgent` have all been wired up too — see the compatibility-model
section below for the piece that actually consumes the Polyvore outfit data. The
backend now also has real Alembic migrations and a live-stack integration test
(`backend/tests/test_live_integration.py`, runs against a real Postgres via
`docker compose up -d postgres` — real auth, real DB writes, real FashionCLIP
inference on live image URLs, not mocks).

---

# Outfit compatibility model — the Polyvore data's actual payoff (`09_compatibility_model.py`)

`RecommendationAgent` originally scored candidate outfits by mean pairwise FashionCLIP
embedding *similarity* — a reasonable heuristic, explicitly documented as a stand-in
for a trained compatibility model. This notebook builds that model: a logistic
regression on the element-wise product of two (frozen, L2-normalized) FashionCLIP
embeddings, trained to distinguish real Polyvore outfit pairs (styled together) from
random cross-outfit pairs — the actual use of the 68,306-outfit dataset the
Recommendation Agent was always meant to draw on.

Sampled 2,000 train outfits + 400 held-out test outfits (3-6 items each, genuinely
different Polyvore splits — no outfit overlap), yielding 38,228 train pairs / 7,620
test pairs (50/50 positive/negative) across 11,067 embedded items.

| | Trained model | Naive cosine similarity |
|---|---|---|
| Accuracy | **0.623** | 0.583 |
| F1 | **0.619** | 0.602 |
| AUC | **0.674** | 0.609 |

**Honest finding: a real but modest improvement, not a dramatic one.** The linear
probe captures somewhat more signal than raw similarity (AUC +0.065), consistent with
`08`'s finding that a trained head on frozen embeddings beats the zero-shot/raw-metric
version — but outfit compatibility is a harder, noisier problem than category
classification was, and this is nowhere near the 0.81-0.85 macro F1 that task reached.
A ceiling around 0.62-0.67 suggests frozen FashionCLIP embeddings alone — without
fine-tuning, without non-visual signal like co-purchase or text — only go so far for
*this* task. Shipped anyway: a real, measured improvement over the heuristic it
replaced is still worth having, honestly labeled as modest rather than oversold.

Saved to `ml/data/processed/compatibility_model.joblib`, copied to
`backend/app/ml/artifacts/compatibility_model.joblib` — same manual-copy caveat as the
category classifier. Used by `backend/app/ml/compatibility_model.py` /
`RecommendationAgent`, with a clean fallback to raw cosine similarity if the artifact
is ever missing (e.g. a fresh checkout before copying it over).

# DressMe — Data Understanding

This folder covers the "Data compréhension" step (S3 in the project schedule): identify
data sources, describe them, explore them, and check quality before any modeling starts.

## Data domains

DressMe needs two very different kinds of data:

1. **Clothing visual attributes** (category, color, style, season, pattern) — needed to
   train/evaluate the Vision Agent and to seed the Recommendation/Purchase agents before
   any real user has uploaded a wardrobe. Public datasets are usable here since visual
   attributes are not market-specific.
2. **Tunisian catalog** (local brands: category, price, color, availability) — the
   project brief and architecture deck explicitly call for this, and no public dataset
   covers it. `ml/scraping/` now has a working scraper for this (see below) — no longer
   "en construction".

## Candidate datasets (domain 1)

| Dataset | Size | Use | Access |
|---|---|---|---|
| [Fashion Product Images (Kaggle, paramaggarwal)](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset) | ~44k images + `styles.csv` | **Primary** — category/color/season/style classification | Needs your Kaggle token — still pending |
| [DeepFashion / DeepFashion2](https://github.com/switchablenorms/DeepFashion2) | ~500k images | Secondary — CLIP embedding fine-tuning | Larger/messier; use once the pipeline works on the small dataset |
| [owj0421/polyvore + polyvore-outfits (Hugging Face)](https://huggingface.co/datasets/owj0421/polyvore) | 365,054 items / 68,306 outfits | Outfit compatibility for the Recommendation Agent | **Public, not gated** — see below, no Kaggle needed. Official full dataset, now integrated |

Pattern (stripes/plaid/floral/solid) isn't labeled in any of these — resolved via
FashionCLIP weak-labeling instead (see `ml/notebooks/07_pattern_weak_labels.py` and the
data dictionary). `material` remains an open gap — see Next steps below.

### Outfit compatibility data — official Polyvore Outfits (no auth needed)

Two companion repos by the same author, both verified via the HF API (`"gated": false`):
`owj0421/polyvore-outfits` (outfit structure — which items go together, the
`nondisjoint_default` split) and `owj0421/polyvore` (item metadata + embedded images,
~365k items). Together they're a refactored re-hosting of the original Vasileva et al.
2018 Polyvore Outfits dataset — no need for the gated author mirror
(`mvasil/polyvore-outfits`).

This replaced an earlier partial sample (`Marqo/polyvore`, 2,900 items / 596 outfits,
rate-limited) once the full dataset's size (~2.1GB of item-metadata parquet shards) was
confirmed downloadable without a Kaggle-style auth token.

**Caveat carried over from the earlier exploration**: Polyvore was a general mood-board
site, not exclusively fashion — some outfit sets include non-fashion items. The taxonomy
mapping (`preprocessing.map_polyvore`) routes anything that doesn't match a DressMe
category to `hors_perimetre` rather than guessing.

```bash
./ml/scraping/download_polyvore_official.sh   # ~2.1GB, outfit structure + item metadata/images (curl, resumable)
```

Output: `ml/data/raw/polyvore_official/` (6 parquet shards + the 3 outfit-structure JSON
files). See `ml/src/polyvore_official.py` for the loader — images are embedded in the
parquet shards and read on demand via `extract_image_bytes()`, not pre-extracted to
individual files (365k separate images would add several more GB for no immediate
benefit).

### Pretrained embedding model — FashionCLIP (no auth needed)

[patrickjohncyh/fashion-clip](https://huggingface.co/patrickjohncyh/fashion-clip) —
verified public (`"gated": false`), MIT license, 2M+ downloads. This is the "Modèle
pré-entraîné" named in the architecture deck (p.17). It gives the Vision Agent zero-shot
image embeddings without training anything from scratch, and the same embeddings feed
the Purchase Agent's similarity search. Load via `transformers`:
`CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")`.

## Getting the primary dataset

```bash
pip install kaggle
# requires your own kaggle.json API token in ~/.kaggle/
kaggle datasets download -d paramaggarwal/fashion-product-images-dataset -p ml/data/raw --unzip
```

`ml/data/raw/` is gitignored — nothing here should be committed.

## Tunisian catalog scraper

`ml/scraping/scrape_hamadi_abid.py` scrapes [ha.com.tn](https://ha.com.tn) (Hamadi Abid),
one of the brands named in the architecture deck. The site is a client-rendered SPA, so
the scraper uses Playwright to render pages like a real browser rather than calling its
authenticated `/api/` directly. It only visits public catalogue pages — checked against
`robots.txt` first, which explicitly allows general crawling (`Allow: /`, only
account/cart/checkout disallowed).

```bash
pip install playwright beautifulsoup4
playwright install chromium
python ml/scraping/scrape_hamadi_abid.py
```

Output: `ml/data/raw/tunisian_catalog/hamadi_abid.csv` (gitignored) — **715 unique
products** across femme/homme/fillette/garçon/bébé/ado (all 331 subcategories in the
sitemap; most baby/ado subcategories are genuinely empty/out of stock, not scraper bugs).
`SECTION_SAMPLE_SIZES` in the script defaults to `{}` (full coverage); set values there
to cap it back down if a full sweep ever gets too slow.

`ml/scraping/scrape_barsha.py` scrapes [barsha.com.tn](https://www.barsha.com.tn) the
same way: `robots.txt` has no crawl-disallow directives (only a "content signals" policy
that doesn't restrict this), so Playwright renders category pages like a real browser.
BARSHA is Femme/Homme only (adult sizes) — combined with Hamadi Abid's
femme/homme/fillette/garçon/bébé/ado range, the two brands together cover the "all
genres and ages" the product brief asks for. Its category menu isn't in a sitemap — the
scraper discovers subcategory URLs by clicking through the site's own "POUR ELLE"/"POUR
LUI" tiles first, then scrapes each resulting listing page.

```bash
python ml/scraping/scrape_hamadi_abid.py
python ml/scraping/scrape_barsha.py
```

Output: `ml/data/raw/tunisian_catalog/{hamadi_abid,barsha}.csv` (gitignored) — Barsha
adds **98 products** (fragrances, chaussures, jeans, t-shirts, casquettes). This is
**complete coverage, not partial**: diagnosed via `ml/scraping/barsha_diagnose_tiles.py`
— the category grid shows 13 tiles per section, but it's a looping carousel of only
5 *unique* categories repeated ~2.6× to fill the slots, not 13 distinct subcategories.
Both sections (Femme/Homme) only have these 5 categories each; all 10 were already
scraped. Barsha's small catalog size is real, not a scraper gap.

`ml/scraping/scrape_chedly_sisters.py` scrapes [chedlysisters.com](https://chedlysisters.com)
— a different, much easier case: it's a **Shopify** store, and `robots.txt` explicitly
states public product/collection data is crawlable. Shopify exposes a public
`/products.json` endpoint, so this is pure HTTP (no Playwright needed at all). Category
isn't given directly (Shopify's `product_type` field is generic plumbing, not a garment
category) — titles are descriptive English names, so category comes from
`preprocessing.map_keywords()` (the same fallback already used for Polyvore).

```bash
python ml/scraping/scrape_chedly_sisters.py
```

Output: `ml/data/raw/tunisian_catalog/chedly_sisters.csv` (gitignored) — **269 products**
(scarves, dresses, bags, blazers, abayas). All 269 have colors extracted from Shopify's
variant options.

`ml/scraping/scrape_noonclo.py` scrapes [noonclo.com](https://noonclo.com) the same way
(same Shopify platform/robots.txt). Both Shopify scrapers now share their logic via
`ml/scraping/shopify_common.py` — adding another Shopify-based Tunisian brand is a ~10
line wrapper, not a new scraper from scratch.

```bash
python ml/scraping/scrape_chedly_sisters.py
python ml/scraping/scrape_noonclo.py
```

Output: `ml/data/raw/tunisian_catalog/noonclo.csv` (gitignored) — **90 products**
(jeans/pants/bags, mostly French titles). Noonclo's near-entirely-French titles exposed
a real gap: `KEYWORDS_TO_DRESSME` was English-only, so French items were failing to map
(56% `hors_perimetre` before the fix). Extended with French terms (`pantalon`, `jean`,
`jupe`, `short`, `chemise`, `pull`, `sweat`, `manteau`, `kimono`, `surchemise`, and the
embarrassingly-missing `sac` — French for "bag", absent from the `sac` category's own
keyword list) → 98.9% in-scope after the fix. Benefits every French-titled source, not
just Noonclo.

Three more brands scraped the same way — all explicitly named in the project's own
architecture deck (`docs/`) as target Tunisian data sources:

```bash
python ml/scraping/scrape_kontakt.py        # kontakt.com.tn
python ml/scraping/scrape_lyoum.py          # lyoum.co (international storefront; lyoum.tn is PrestaShop, no public API)
python ml/scraping/scrape_rooh_clothing.py  # rooh-clothing.com
```

- **Kontakt** — **3,063 products**, by far the largest single Tunisian source. Word-
  frequency analysis over its unmapped items (not guesswork) drove adding `robe`, `body`,
  `débardeur`, `jogger`, `bombers`, `legging`, `cargo`, `collier` to the keyword list.
  `robe` was previously skipped as too ambiguous (English "robe" = bathrobe) — real
  evidence across multiple French-titled Tunisian brands (103 occurrences in Kontakt
  alone, nearly all genuine dresses) justified adding it. 76.4% in-scope.
- **Lyoum** — **186 products**. This is a lifestyle concept-store, not pure clothing
  (notebooks, beach towels/*fouta* are also in the catalog) — a real `hors_perimetre`
  rate here is partly expected, not all a keyword gap. Added `cabas` (tote bag) and
  `t-loose` (Lyoum's own loose-tee product line name). 59.7% in-scope.
- **Rooh Clothing** — only **9 products** (small/new storefront). All 9 use ambiguous
  "Set" naming (e.g. "Essential Woven Set") that's deliberately not guessed (see below)
  — 0% in-scope is an honest result for this source, not a bug.

Two more — traditional Tunisian attire (jebbas), filling a style gap the contemporary
brands above don't cover:

```bash
python ml/scraping/scrape_myjebba.py  # myjebba.com
python ml/scraping/scrape_ileycom.py  # ileycom.tn
```

- **MY JEBBA** — **34 products**, all traditional jebbas. `"jebba"` itself was missing
  from the keyword list entirely — every single product failed before the fix (8.8% →
  100% in-scope after adding it).
- **Ileycom** — **4,744 products**, the largest single source found. Despite surfacing in
  jebba searches, this is a **broad Tunisian artisan marketplace** (prickly-pear jam,
  vinegar, home decor, oil paintings, planners — alongside some jebbas/jewelry), not a
  dedicated clothing store. ~26% in-scope is a real reflection of that mix, not a keyword
  gap to chase further.

Other brands checked but not scraped:
- **ZEN** (zen.com.tn) and **Souk El Kahina** (soukelkahina.tn) — both explicitly disallow
  all crawlers via `robots.txt` (`Disallow: /`). Do not scrape. (Note: BARSHA's product
  images are served from `images.zen.com.tn` — same corporate group's CDN — but this
  scraper only ever requests pages under `barsha.com.tn`, never `zen.com.tn`.)
- **YOLO Jeans** and **Bent Essarajine** — no real e-commerce site, only Instagram/
  Facebook/TikTok. Out of scope for scraping (different ToS/risk profile than a brand's
  own website — not pursued even though technically indexed on third-party sites like
  `price.tn`, since that's a small/partial yield for real reverse-engineering effort).
- **Elissar** (elissar.tn), **Hraier** (hraier.com) — WordPress/WooCommerce, no public
  products API.
- **Ma7alli** (ma7alli.tn, lists YOLO products) — unreachable: genuine server-side
  TLS/certificate failure, confirmed through two different TLS stacks (curl + .NET), not
  a local fluke.
- **AwA** (awa.tn) — connection failed during the check; not retried.
- **lyoum.tn** (the local Tunisian storefront, same Lyoum brand) — PrestaShop, no public
  products API; scraped `lyoum.co` (international storefront) instead.
- **Elissar** (elissar.tn) — WordPress, no public products.json.
- **Neyra** (neyra.tn) and **Baraa** (baraa.com, WooCommerce) — checked, no public product
  API found quickly; not pursued further (would need Playwright-style reverse-engineering
  like Hamadi Abid/Barsha — worth it only if these specific brands become a priority).
- **AwA** (awa.tn) — connection failed during the check; not retried.

`ml/scraping/render_page.py` is a reusable inspector: renders any URL with a real browser
and dumps the DOM, useful for finding selectors on a new site before writing a scraper.
The `barsha_explore_*.py` / `barsha_check_*.py` / `barsha_diagnose_tiles.py` scripts in
the same folder are the throwaway exploration steps that led to `scrape_barsha.py`'s
selectors (and confirmed its coverage is complete) — kept for reference on how the
site's Angular menu/routing was reverse-engineered, not meant to be
run again.

## Status

| Source | Rows | Status |
|---|---|---|
| Fashion Product Images (Kaggle) | 44,424 | Done — extracted directly from the downloaded zip |
| Hamadi Abid (scraped) | 715 | Done — full sitemap sweep |
| Barsha (scraped) | 98 | Done — complete (5 unique categories × 2 sections, verified) |
| Chedly Sisters (scraped) | 269 | Done — full catalog via Shopify's public API |
| Noonclo (scraped) | 90 | Done — full catalog via Shopify's public API |
| Kontakt (scraped) | 3,063 | Done — full catalog via Shopify's public API |
| Lyoum (scraped) | 186 | Done — lifestyle concept-store, not pure clothing |
| Rooh Clothing (scraped) | 9 | Done — small storefront, mostly ambiguous "Set" naming |
| MY JEBBA (scraped) | 34 | Done — traditional jebbas, 100% in-scope |
| Ileycom (scraped) | 4,744 | Done — largest Tunisian source; broad artisan marketplace, not pure clothing |
| Polyvore Outfits, official (Hugging Face, `owj0421/polyvore` + `polyvore-outfits`) | 365,054 / 68,306 outfits | Done — full dataset, swapped in for the earlier 2,900/596 partial sample. See `ml/src/polyvore_official.py` |
| FashionCLIP (pretrained model) | Verified public | Zero-shot tested on Tunisian photos — 62% accuracy; a linear probe on the same frozen embeddings raises it to 81% (veste 0.17→0.69 F1, robe 0.30→0.71 F1); this trained classifier is what `backend/app/agents/vision_agent.py` loads — see `DATA_DICTIONARY.md` |
| Tunisian product photos, local copies | 8,925 / 8,958 | Done — `ml/scraping/download_tunisian_images.py`, 25 failures are genuine dead links on Kontakt's own storefront |
| Pattern attribute (all sources) | 8,929 weak-labeled | Done via FashionCLIP zero-shot — no source has ground truth; see `ml/data/processed/pattern_weak_labels.csv` |

## Taxonomy reconciliation — done

`ml/src/preprocessing.py` maps all 11 sources above into one shared 7-category DressMe
vocabulary (`haut, bas, robe, veste, chaussures, sac, accessoire` + `hors_perimetre`).
`ml/notebooks/04_taxonomy_reconciliation.py` and `ml/reports/generate_report.py` both
read from `ml/src/catalog.py` directly, so they pick up new sources automatically —
adding a source here is the only place that needs touching. Details in
`ml/data/DATA_DICTIONARY.md`.

## Unified catalog — done

`ml/src/catalog.py` merges all 11 sources into **one table**, one schema
(`source, item_key, name, dressme_category, color_family, colors_raw, price, season,
style, brand, material, image_location, image_is_local, split`) — **418,686 items total**
(365,054 from the full official Polyvore Outfits dataset, 44,424 Kaggle, ~9,200 across
the nine Tunisian sources). This is the canonical artifact downstream agents should
query, not the eleven raw CSVs individually. `split` is a stratified train/val/test split
by `dressme_category` (`preprocessing.stratified_split`).

```bash
python ml/src/catalog.py   # or ml/notebooks/05_unified_catalog.py for the full breakdown
```

Output: `ml/data/processed/dressme_catalog.parquet` (11.4MB, committed — unlike
`data/raw/`, this is small enough and derived, not scraped bulk data).

## Next steps

1. All four data-understanding notebooks (`01`-`03`) and the taxonomy reconciliation
   (`04`) have been run — see `ml/data/DATA_DICTIONARY.md` and `ml/reports/` for findings.
2. Color-normalization coverage — audited and fixed. Tunisian sources were already fine
   (3,946/3,952 items normalize cleanly; the 6 that don't are correctly-excluded
   non-colors like `PARFUM`/`PACK 1`/`2`). But the official Polyvore dataset has **no**
   color field at all, so `color_family` was 0% for 87% of the catalog. Fixed via
   `preprocessing.map_color_from_text()` — extracts color from the Polyvore title, reusing
   the existing `COLOR_FAMILIES` vocabulary. Catalog-wide coverage: 12.8% → 32.0%.
3. `material` — resolved via text extraction (`preprocessing.map_material`), not
   weak-labeling (fabric isn't reliably visually distinguishable via zero-shot CLIP the
   way pattern is). Matches fabric keywords in the product name/title: 86,232/418,686
   items (20.6%) get a value, the rest honestly `NaN` — coverage is inherently partial
   since it only catches items whose name happens to mention fabric.
4. Only 300/44,424 Kaggle images are stored locally (disk-space tradeoff) — the Tunisian
   sources now have local images for 8,925/8,958 items (see Status table). Re-pull more
   Kaggle images once actually fine-tuning, not just understanding the data.
5. Real wardrobe test photos (actual user clothing, not catalog/product shots) are still
   needed to validate the Vision Agent against realistic phone-camera conditions — this
   requires the team to take and provide them, not something derivable from public data.
6. Only then move to feature engineering / modeling for the Vision Agent.

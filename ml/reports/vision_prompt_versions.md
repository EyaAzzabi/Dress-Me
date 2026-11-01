# Vision LLM prompt versions (CRISPE)

400 random held-out Tunisian garments + 300 Kaggle photos, cut once (seed 1) into a DEV half (used to write prompts) and a TEST half (never read while tuning). `gpt-4o-mini`, image detail low, temperature 0. FashionCLIP columns are the reference on the same photos.


## DEV half

| version | failed | category | (FashionCLIP) | color | (FashionCLIP) | season: answers / acc | style: answers / acc | style fill-in (n): LLM vs FashionCLIP |
|---|---|---|---|---|---|---|---|---|
| v1 | 0.0% | 0.747 (n=194) | 0.825 | 0.659 (n=205) | 0.668 | 57% / 0.430 | 61% / 0.935 | 0.875 vs 0.400 (n=40) |
| v2 | 0.0% | 0.770 (n=187) | 0.856 | 0.632 (n=204) | 0.672 | 59% / 0.506 | 65% / 0.897 | 0.854 vs 0.390 (n=41) |
| v3 | 0.0% | 0.764 (n=199) | 0.819 | 0.624 (n=210) | 0.671 | 58% / 0.483 | 65% / 0.888 | 0.875 vs 0.400 (n=40) |
| v4 | 0.0% | 0.762 (n=193) | 0.829 | 0.670 (n=206) | 0.675 | 52% / 0.500 | 64% / 0.896 | 0.875 vs 0.400 (n=40) |
| v5 | 0.0% | 0.793 (n=174) | 0.868 | 0.677 (n=192) | 0.682 | 59% / 0.427 | 59% / 0.933 | 0.875 vs 0.400 (n=40) |

## TEST half

| version | failed | category | (FashionCLIP) | color | (FashionCLIP) | season: answers / acc | style: answers / acc | style fill-in (n): LLM vs FashionCLIP |
|---|---|---|---|---|---|---|---|---|
| v1 | 0.0% | 0.783 (n=189) | 0.873 | 0.701 (n=211) | 0.706 | 57% / 0.442 | 58% / 0.931 | 0.971 vs 0.353 (n=34) |
| v2 | 0.0% | 0.795 (n=185) | 0.881 | 0.698 (n=212) | 0.698 | 60% / 0.600 | 64% / 0.821 | 0.816 vs 0.342 (n=38) |
| v3 | 0.0% | 0.771 (n=192) | 0.870 | 0.679 (n=215) | 0.698 | 56% / 0.631 | 67% / 0.870 | 0.895 vs 0.342 (n=38) |
| v4 | 0.0% | 0.758 (n=186) | 0.866 | 0.693 (n=215) | 0.698 | 52% / 0.615 | 67% / 0.860 | 0.868 vs 0.342 (n=38) |
| v5 | 0.0% | 0.824 (n=170) | 0.882 | 0.696 (n=204) | 0.706 | 56% / 0.452 | 57% / 0.906 | 0.943 vs 0.371 (n=35) |

## TEST half: each version minus v1 (paired bootstrap, 95% CI)

- **v2 category**: -0.011  95% CI [-0.038, +0.016]  (n=182)
- **v2 color (Kaggle)**: +0.007  95% CI [-0.040, +0.054]  (n=149)
- **v3 category**: -0.011  95% CI [-0.043, +0.016]  (n=187)
- **v3 color (Kaggle)**: -0.006  95% CI [-0.060, +0.047]  (n=149)
- **v4 category**: -0.038  95% CI [-0.077, -0.005]  (n=182)
- **v4 color (Kaggle)**: -0.007  95% CI [-0.060, +0.040]  (n=149)
- **v5 category**: +0.000  95% CI [+0.000, +0.000]  (n=170)
- **v5 color (Kaggle)**: -0.007  95% CI [-0.040, +0.020]  (n=149)

## Versions

| | what it is |
|---|---|
| v1 | the first CRISPE prompt (short; vocabularies, one JSON object) — current default |
| v2 | v1 + per-attribute decision rules and Tunisian context |
| v3 | v2 + fixes found on DEV: "Sports" only for clearly athletic items, "multiple_items" is never a category |
| v4 | v3 + a one-sentence visible-evidence "reasoning" before the answer |
| v5 | v1 + only the "multiple_items" sentence |

## What the measurements say (TEST half)

- **The biggest gain was not a prompt.** The model answers `category: "multiple_items"` on photos of a whole
  outfit, even when told not to (10-13 of 14 failures re-asked, for v1, v3 and v5). Throwing the whole answer
  away cost 2-9% of calls depending on the version; keeping the valid fields (colors, style, season) and
  marking the category unknown brought failures to 0 of 3,500 calls.
- **Style (the only attribute delegated to OpenAI): v1 is still the best** (93.1% accurate, Sports 8/8, 3 Casual
  items called Sports). The extra rules made it worse (v2 -9.5 pts, 95% CI [-16.7, -3.6]); v5 and v3 are within noise
  of v1, never above it. More rules did not mean a better prompt.
- **Season:** v2-v4 beat v1 by 17-19 points (v3: +17.6, CI [+7.5, +27.5]) and beat FashionCLIP-by-type on the same
  photos (v3: +13.1, CI [+1.2, +25.0]) — but none beats "always answer the majority class" on those photos
  (v3 63.1% vs 64.3%), and the Kaggle season labels are collection labels, not something visible. Not adopted.
- **Category:** no prompt beats FashionCLIP alone. As a fallback below FashionCLIP's 0.60 confidence, v4 gives
  +2.0 pts (CI [0.0, +4.5]) — borderline, on only 17 photos. Not adopted.
- **Color:** no version beats FashionCLIP (all within +-2 pts).

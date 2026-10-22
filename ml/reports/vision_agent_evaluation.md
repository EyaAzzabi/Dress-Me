# Vision Agent evaluation (before vs. after)

## Category — held-out Tunisian test photos

1380 photos (735 real garments, 645 non-clothing catalog products). The "hors_perimetre" gate is unchanged: it keeps 98.2% of garments and rejects 78.3% of the non-clothing products, before and after.

Macro-F1 is over the 7 garment labels only (a photo sent to hors_perimetre counts as a miss).

| | accuracy, all garments | macro-F1, all garments | accuracy, garments kept by the gate | macro-F1, garments kept by the gate |
|---|---|---|---|---|
| before: 8-class linear probe | 0.837 | 0.845 | 0.852 | 0.851 |
| after: probe as gate + SVM garment head | 0.854 | 0.864 | 0.870 | 0.871 |

Category head alone (garments kept by the gate): accuracy +0.018 (95% CI [-0.004, +0.042]) — a modest, NOT statistically significant gain.

| class | test photos | F1 before | F1 after |
|---|---|---|---|
| haut | 224 | 0.864 | 0.861 |
| bas | 160 | 0.767 | 0.805 |
| robe | 58 | 0.769 | 0.862 |
| veste | 47 | 0.762 | 0.707 |
| chaussures | 13 | 0.929 | 0.963 |
| sac | 83 | 0.907 | 0.940 |
| accessoire | 137 | 0.957 | 0.957 |

Confidence gate at 0.6: asks the user to confirm 9.8% of garments (4.6% of the correct ones, 40.2% of the wrong ones); accuracy of what is accepted: 0.903.

## Season and style — 300 labeled Kaggle photos

**Season** (always answering the majority class gets 0.507)

| | accuracy | balanced accuracy |
|---|---|---|
| before: zero-shot prompts | 0.460 | 0.352 |
| after: via garment type | 0.480 | 0.477 |

accuracy: +0.020 (95% CI [-0.053, +0.100])

balanced accuracy: +0.126 (95% CI [+0.047, +0.203])

What the agent actually stores (suggest only at confidence >= 0.6): answers 21.3% of photos, accuracy there 0.641 (majority class on that subset: 0.406). The Kaggle season is a collection label, not a visible property — the ceiling is low.

**Style** — Casual / Sports / Ethnic / Formal only (299 photos; majority class 0.779; Smart Casual / Party / Travel / Home are ~0.5% of the labels)

| | accuracy | balanced accuracy |
|---|---|---|
| before: zero-shot prompts (restricted to the 4) | 0.585 | 0.642 |
| after: via garment type | 0.589 | 0.775 |

accuracy: +0.003 (95% CI [-0.070, +0.077])

balanced accuracy: +0.133 (95% CI [+0.053, +0.215])

What the agent stores (style only at confidence >= 0.7): answers 59.5% of photos, accuracy there 0.747, balanced accuracy 0.901.

## Color — zero-shot, unchanged

Tunisian in-scope photos with a usable color label: 1571 — accuracy 0.679.
Kaggle photos: 297 — accuracy 0.704.

Tried and rejected (same labels, val/test discipline): five prompt templates (+0.0 to -3.3 pts), color synonyms (-3 to +1.7 pts, inconsistent across the two datasets), and logistic-regression probes trained on the Tunisian color labels (best 69.5% on Tunisian test vs 64.2% zero-shot, but 47-56% on Kaggle vs 70.4% zero-shot: the labels are few, imbalanced — 7 violet, 9 red, 10 green training photos — and multi-color products carry only their first color).


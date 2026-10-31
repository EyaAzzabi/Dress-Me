# %% [markdown]
# # DressMe — Taxonomy reconciliation across all sources
#
# Verifies `ml/src/preprocessing.py`'s DressMe taxonomy mapping (haut, bas, robe, veste,
# chaussures, sac, accessoire, + hors_perimetre) across every source, by building the
# unified catalog (`ml/src/catalog.py`) and checking per-source coverage. Reads from the
# catalog builder directly — as new sources are added there, this notebook picks them up
# automatically instead of needing its own copy of the per-source loading logic.
#
# Run as a Jupyter/VS Code interactive script (`# %%` cells).

# %%
import sys
from pathlib import Path

import matplotlib
import pandas as pd

RUNNING_INTERACTIVELY = hasattr(sys, "ps1") or "ipykernel" in sys.modules
if not RUNNING_INTERACTIVELY:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import catalog, preprocessing  # noqa: E402

REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## 1. Build the unified catalog (applies every source's DressMe mapping)

# %%
df = catalog.build_unified_catalog()
print(f"{df['source'].nunique()} sources mapped: {sorted(df['source'].unique())}")

# %% [markdown]
# ## 2. Coverage per source — how much of each source lands in-scope vs. hors_perimetre

# %%
coverage = (
    df.groupby("source")["dressme_category"]
    .apply(lambda s: pd.Series({"n": len(s), "in_scope_pct": round(100 * s.isin(preprocessing.DRESSME_CATEGORIES).mean(), 1)}))
    .unstack()
)
print(coverage.to_string())

# %% [markdown]
# ## 3. Combined distribution across all sources — one shared vocabulary, verified

# %%
cross_tab = pd.crosstab(df["dressme_category"], df["source"])
cross_tab = cross_tab.reindex(preprocessing.DRESSME_CATEGORIES + [preprocessing.OUT_OF_SCOPE]).fillna(0).astype(int)
print(cross_tab)

fig, ax = plt.subplots(figsize=(11, 6))
cross_tab.plot.barh(stacked=True, ax=ax)
ax.set_title("DressMe category distribution across all reconciled sources")
ax.set_xlabel("count")
fig.tight_layout()
if RUNNING_INTERACTIVELY:
    plt.show()
else:
    fig.savefig(REPORTS / "04_taxonomy_reconciliation.png", dpi=120)
    plt.close(fig)
    print(f"Saved {REPORTS / '04_taxonomy_reconciliation.png'}")

# %% [markdown]
# ## 4. Findings
#
# - Every source in `ml/src/catalog.py` maps into the same 7-category DressMe vocabulary
#   (haut, bas, robe, veste, chaussures, sac, accessoire) + hors_perimetre.
# - `hors_perimetre` rate per source tells you how much of that source is unusable for
#   wardrobe features (underwear, home textiles, perfume, lifestyle goods, etc.) —
#   expected to be non-zero, not a bug. Lyoum in particular is a lifestyle concept-store
#   (notebooks, beach towels), so a higher rate there is partly real, not a keyword gap.
# - Next step if this needs refining: review any source with unexpectedly high
#   hors_perimetre and extend the relevant mapping dict in `ml/src/preprocessing.py` —
#   ideally via word-frequency analysis over the unmapped items, not guessing.

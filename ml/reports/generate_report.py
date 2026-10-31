"""Generates persistent chart files + a markdown report from the data-understanding
work, so there's an actual artifact to open instead of only terminal output from an
interactive run.

Pulls from the unified catalog (ml/src/catalog.py) as the source of truth for anything
source-generic (counts, DressMe categories, colors), so this report stays in sync as new
sources are added there — plus a few source-specific deep-dives (Kaggle attributes,
Polyvore outfit structure) that aren't part of the unified schema.

Usage: python ml/reports/generate_report.py
Output: ml/reports/*.png, ml/reports/DATA_UNDERSTANDING_RESULTS.md
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display needed, just save files
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import catalog, preprocessing  # noqa: E402

RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "reports"


def bar_chart(series: pd.Series, title: str, filename: str, top_n: int = 15) -> None:
    data = series.value_counts().head(top_n)
    fig, ax = plt.subplots(figsize=(8, 5))
    data.sort_values().plot.barh(ax=ax, color="#c2185b")
    ax.set_title(title)
    ax.set_xlabel("count")
    fig.tight_layout()
    fig.savefig(REPORTS / filename, dpi=120)
    plt.close(fig)


def main() -> None:
    lines = ["# Data Understanding — Results\n"]

    # --- Unified catalog overview (all sources, reconciled taxonomy) ---
    df = catalog.build_unified_catalog()
    counts = df.groupby("source").size().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(8, 5))
    counts.sort_values().plot.barh(ax=ax, color="#c2185b")
    ax.set_title("Items per source")
    ax.set_xlabel("count")
    fig.tight_layout()
    fig.savefig(REPORTS / "catalog_sources.png", dpi=120)
    plt.close(fig)

    cross_tab = pd.crosstab(df["dressme_category"], df["source"])
    cross_tab = cross_tab.reindex(preprocessing.DRESSME_CATEGORIES + [preprocessing.OUT_OF_SCOPE]).fillna(0).astype(int)
    fig, ax = plt.subplots(figsize=(11, 6))
    cross_tab.plot.barh(stacked=True, ax=ax)
    ax.set_title("DressMe category distribution across all sources")
    ax.set_xlabel("count")
    fig.tight_layout()
    fig.savefig(REPORTS / "catalog_categories.png", dpi=120)
    plt.close(fig)

    bar_chart(df["color_family"].dropna(), "Color family distribution (all sources)", "catalog_colors.png")

    coverage = df.groupby("source")["dressme_category"].apply(
        lambda s: round(100 * s.isin(preprocessing.DRESSME_CATEGORIES).mean(), 1)
    ).sort_values(ascending=False)

    lines += [
        "## Unified catalog — all sources\n",
        f"- **{len(df)} items** across **{df['source'].nunique()} sources**\n",
        f"- Per source: {', '.join(f'{s} ({n})' for s, n in counts.items())}\n",
        f"- In-scope rate (maps to a real DressMe category, not `hors_perimetre`): "
        f"{', '.join(f'{s} {p}%' for s, p in coverage.items())}\n",
        "\n![items per source](catalog_sources.png)\n",
        "\n![categories](catalog_categories.png)\n",
        "\n![colors](catalog_colors.png)\n",
    ]

    # --- Fashion Product Images (Kaggle) — attributes not in the unified schema ---
    styles_path = RAW / "styles.csv"
    if styles_path.exists():
        fp = pd.read_csv(styles_path, on_bad_lines="skip")
        bar_chart(fp["articleType"], "Fashion Product Images — top article types", "fp_article_types.png")

        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        fp["season"].value_counts().plot.bar(ax=axes[0], color="#c2185b")
        axes[0].set_title("By season")
        fp["usage"].value_counts().plot.bar(ax=axes[1], color="#c2185b")
        axes[1].set_title("By usage")
        fig.tight_layout()
        fig.savefig(REPORTS / "fp_season_usage.png", dpi=120)
        plt.close(fig)

        images_dir = RAW / "images"
        n_local_images = len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0
        rare = (fp["articleType"].value_counts() < 50).sum()

        lines += [
            "## Fashion Product Images (Kaggle) — attribute detail\n",
            f"- {fp['articleType'].nunique()} article types, {rare} with fewer than 50 samples "
            f"(long-tail, candidates to merge)\n",
            f"- {n_local_images} / {len(fp)} images available locally "
            f"(sampled to save disk space — see `ml/README.md`)\n",
            "\n![article types](fp_article_types.png)\n",
            "\n![season and usage](fp_season_usage.png)\n",
        ]

    # --- Polyvore — outfit structure not in the unified schema ---
    poly_path = RAW / "polyvore_sample.csv"
    if poly_path.exists():
        poly = pd.read_csv(poly_path)
        outfit_sizes = poly.groupby("outfit_id").size()

        fig, ax = plt.subplots(figsize=(8, 5))
        outfit_sizes.value_counts().sort_index().plot.bar(ax=ax, color="#c2185b")
        ax.set_title("Polyvore — outfit size distribution")
        ax.set_xlabel("items per outfit")
        ax.set_ylabel("number of outfits")
        fig.tight_layout()
        fig.savefig(REPORTS / "polyvore_outfit_sizes.png", dpi=120)
        plt.close(fig)

        lines += [
            "## Outfit compatibility — Polyvore structure detail\n",
            f"- **{poly['outfit_id'].nunique()} outfits**, mean {outfit_sizes.mean():.2f} / "
            f"median {outfit_sizes.median():.0f} items per outfit\n",
            "\n![outfit sizes](polyvore_outfit_sizes.png)\n",
        ]

    report_path = REPORTS / "DATA_UNDERSTANDING_RESULTS.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved report to {report_path}")
    print(f"Saved charts to {REPORTS}/*.png")


if __name__ == "__main__":
    main()

"""Resolves the exact, still-online product page of the catalog's non-Shopify products.

The catalog only keeps a product id for these brands (item_key `ha_<id>` / `barsha_<id>`),
and some products have since been taken down, so the pages are resolved once and
bundled (app/data/product_urls.json) — no request to the stores at runtime:

- Hamadi Abid: pages sit under their category path; the site's public sitemap lists
  every product online.
- Barsha: pages are /fr/produit/<id>-<slug>, but the site is a single-page app that
  answers 200 for any URL and only shows its 404 once rendered — so each page is
  rendered with headless Edge/Chrome and kept only if it shows the product.

Run from backend/:  python -m scripts.build_product_urls
"""

import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from app.services.ecommerce import _load_catalog
from app.services.tunisian_brands import PRODUCT_URLS_PATH, by_name

HAMADI_ABID_SITEMAP = "https://ha.com.tn/sitemap.xml"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge", "google-chrome", "chromium",
]
RENDER_WORKERS = 4  # stay gentle with the store


def hamadi_abid(ids: list[str]) -> dict[str, str]:
    sitemap = httpx.get(HAMADI_ABID_SITEMAP, timeout=30).text
    by_id = {}
    for url in re.findall(r"<loc>([^<]+)</loc>", sitemap):
        match = re.search(r"/(\d+)-[^/]*$", url)
        if match:
            by_id[match.group(1)] = url
    return {f"ha_{i}": by_id[i] for i in ids if i in by_id}


def barsha(products: list[tuple[str, str]]) -> dict[str, str]:
    website = by_name("Barsha").website
    candidates = {f"barsha_{i}": f"{website}/fr/produit/{i}-{_slug(name)}".rstrip("-") for i, name in products}
    with ThreadPoolExecutor(RENDER_WORKERS) as pool:
        online = list(pool.map(_shows_a_product, candidates.values()))
    return {key: url for (key, url), ok in zip(candidates.items(), online) if ok}


def _shows_a_product(url: str) -> bool:
    browser = next((b for b in BROWSERS if Path(b).exists() or shutil.which(b)), None)
    if browser is None:
        raise RuntimeError("Edge or Chrome is needed to check Barsha's pages")
    for _ in range(2):  # a render occasionally comes back empty
        html = subprocess.run(
            [browser, "--headless=new", "--disable-gpu", f"--user-data-dir={tempfile.mkdtemp()}",
             "--virtual-time-budget=20000", "--dump-dom", url],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120,
        ).stdout
        if "ERREUR 404" in html:
            return False
        if re.search(r"<title>[^<]*\| Barsha", html):
            return True
    return False


def _slug(text: str) -> str:
    """The slug Barsha's own site builds from a product title."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def main() -> None:
    catalog = _load_catalog()
    ha_ids = catalog.loc[catalog["brand"] == "Hamadi Abid", "item_key"].dropna().str.removeprefix("ha_").tolist()
    barsha_rows = catalog.loc[catalog["brand"] == "Barsha", ["item_key", "name"]].dropna(subset=["item_key"])
    barsha_products = [(k.removeprefix("barsha_"), n) for k, n in barsha_rows.values]

    urls = {**hamadi_abid(ha_ids), **barsha(barsha_products)}
    PRODUCT_URLS_PATH.write_text(json.dumps(urls, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    found_ha = sum(k.startswith("ha_") for k in urls)
    print(f"Hamadi Abid: {found_ha}/{len(ha_ids)} online — Barsha: {len(urls) - found_ha}/{len(barsha_products)} online")


if __name__ == "__main__":
    main()

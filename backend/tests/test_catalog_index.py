import numpy as np
import pandas as pd
import pytest

from app.services import catalog_index, tunisian_brands
from app.services.catalog_index import CatalogIndex, parse_price


@pytest.mark.parametrize("raw, expected", [
    ("49,99 TND", 49.99),
    ("44.9", 44.9),
    ("1 299,00 DT", 1299.0),
    ("Prix: 120 dt", 120.0),
    ("", None),
    (None, None),
    ("0", None),
])
def test_parse_price_handles_the_scraped_formats(raw, expected):
    assert parse_price(raw) == expected


@pytest.fixture
def fake_index(monkeypatch):
    products = pd.DataFrame([
        {"item_key": "kontakt_top-noir", "name": "Top noir", "dressme_category": "haut", "brand": "Kontakt",
         "price_tnd": 40.0, "image_location": "u1"},
        {"item_key": "lyoum_top-blanc", "name": "Top blanc", "dressme_category": "haut", "brand": "Lyoum",
         "price_tnd": 60.0, "image_location": "u2"},
        {"item_key": "ha_123", "name": "Jean", "dressme_category": "bas", "brand": "Hamadi Abid",
         "price_tnd": None, "image_location": "u3"},
    ]).astype(object)
    vectors = np.eye(3, 512, dtype=np.float32)
    monkeypatch.setattr(catalog_index, "_load_index", lambda: (products, vectors))


def test_search_ranks_by_visual_similarity_within_the_category(fake_index):
    query = np.zeros(512)
    query[1], query[0] = 0.9, 0.1

    results = CatalogIndex().search(query, category="haut")

    assert [r.name for r in results] == ["Top blanc", "Top noir"]
    assert results[0].similarity == pytest.approx(0.9)


def test_matches_link_to_the_product_page_on_the_brand_site(fake_index):
    query = np.zeros(512)
    query[0] = 1.0

    top = CatalogIndex().search(query, category="haut")[0].to_dict()

    assert top["product_url"] == "https://kontakt.com.tn/products/top-noir"
    assert top["store_url"] == "https://kontakt.com.tn"
    assert top["buyable"] is True


def test_unlocated_non_shopify_product_falls_back_to_the_brand_site(fake_index, monkeypatch):
    monkeypatch.setattr(tunisian_brands, "_resolved_product_urls", lambda: {})
    jean = CatalogIndex().get("ha_123").to_dict()

    assert jean["product_url"] is None
    assert jean["store_url"] == "https://ha.com.tn"
    assert jean["buyable"] is False


def test_hamadi_abid_product_links_to_its_own_page_but_is_not_buyable(fake_index, monkeypatch):
    url = "https://ha.com.tn/catalogue/homme/jeans/pantalon/123-jean-slim"
    monkeypatch.setattr(tunisian_brands, "_resolved_product_urls", lambda: {"ha_123": url})
    jean = CatalogIndex().get("ha_123").to_dict()

    assert jean["product_url"] == url
    assert jean["buyable"] is False


def test_taken_down_barsha_product_has_no_product_link(monkeypatch):
    url = "https://www.barsha.com.tn/fr/produit/2017-ballerine"
    monkeypatch.setattr(tunisian_brands, "_resolved_product_urls", lambda: {"barsha_2017": url})

    assert tunisian_brands.links("barsha_2017", "Barsha")["product_url"] == url
    assert tunisian_brands.links("barsha_1415", "Barsha") == {
        "product_url": None, "store_url": "https://www.barsha.com.tn", "buyable": False}


def test_get_unknown_product_returns_none(fake_index):
    assert CatalogIndex().get("kontakt_nope") is None


def test_brands_are_ranked_by_their_closest_products(fake_index, monkeypatch):
    monkeypatch.setattr(catalog_index, "BRAND_MIN_PRODUCTS", 1)
    query = np.zeros(512)
    query[1], query[0] = 0.9, 0.1

    brands = CatalogIndex().brand_affinity(query, category="haut")

    assert [b["name"] for b in brands] == ["Lyoum", "Kontakt"]
    assert brands[0]["website"] == "https://lyoum.co"
    assert brands[0]["showcase"][0]["product_url"] == "https://lyoum.co/products/top-blanc"


def test_brands_with_too_few_products_are_not_judged(fake_index):
    assert CatalogIndex().brand_affinity(np.ones(512), category="haut") == []


def test_search_unknown_category_returns_nothing(fake_index):
    assert CatalogIndex().search(np.ones(512), category="robe") == []


def test_missing_index_is_reported_unavailable(monkeypatch):
    monkeypatch.setattr(catalog_index, "_load_index",
                        lambda: (pd.DataFrame(), np.empty((0, 512), dtype=np.float32)))

    assert not CatalogIndex().is_available()
    assert CatalogIndex().search(np.ones(512)) == []

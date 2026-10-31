import pandas as pd
import pytest

from app.services.ecommerce import EcommerceService

FAKE_CATALOG = pd.DataFrame([
    {"name": "Robe noire en soie", "dressme_category": "robe", "price": "90",
     "brand": "Ileycom", "image_location": "https://x/1.jpg"},
    {"name": "Ceinture en cuir", "dressme_category": "accessoire", "price": "50",
     "brand": "Hamadi Abid", "image_location": "https://x/2.jpg"},
    {"name": "Robe rouge longue", "dressme_category": "robe", "price": "120",
     "brand": "Barsha", "image_location": "https://x/3.jpg"},
])


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    monkeypatch.setattr("app.services.ecommerce._load_catalog", lambda: FAKE_CATALOG)


def test_empty_query_returns_nothing():
    assert EcommerceService().search_products("") == []


def test_matches_rank_above_non_matches():
    results = EcommerceService().search_products("robe noire")

    assert len(results) >= 1
    assert results[0]["name"] == "Robe noire en soie"  # matches both query words


def test_category_filter_excludes_other_categories():
    results = EcommerceService().search_products("robe", category="accessoire")

    assert results == []


def test_no_match_returns_empty_list():
    assert EcommerceService().search_products("pantalon introuvable xyz") == []

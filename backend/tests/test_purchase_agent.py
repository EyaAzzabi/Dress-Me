import uuid

import numpy as np
import pytest

from app.agents.purchase_agent import PurchaseAgent

USER_ID = uuid.uuid4()


def _attrs(category: str = "haut") -> dict:
    return {"category": category, "colors": ["noir"], "pattern": "uni", "style": "Casual",
            "embedding": np.zeros(512)}


@pytest.fixture(autouse=True)
def fake_ecommerce(monkeypatch):
    """Isolates these tests from the real bundled catalog — EcommerceService has its
    own tests (test_ecommerce_service.py)."""
    monkeypatch.setattr(
        "app.agents.purchase_agent.EcommerceService.search_products",
        lambda self, *a, **k: [{"name": "fake alternative"}],
    )


def test_rejects_out_of_scope_without_a_similarity_or_catalog_search(monkeypatch):
    wardrobe_search_called = False
    catalog_search_called = False

    def fail_wardrobe(*a, **k):
        nonlocal wardrobe_search_called
        wardrobe_search_called = True
        return []

    def fail_catalog(self, *a, **k):
        nonlocal catalog_search_called
        catalog_search_called = True
        return []

    monkeypatch.setattr("app.agents.purchase_agent.vector_store.find_similar_items", fail_wardrobe)
    monkeypatch.setattr("app.agents.purchase_agent.EcommerceService.search_products", fail_catalog)

    result = PurchaseAgent().run(image_url="x", attributes=_attrs("hors_perimetre"), user_id=USER_ID)

    assert result["verdict"] == "not_recommended"
    assert result["compatibility_score"] == 0.0
    assert result["catalog_alternatives"] == []
    assert not wardrobe_search_called  # no point searching the wardrobe for a non-clothing photo
    assert not catalog_search_called  # ...or the catalog, for the same reason


def test_empty_wardrobe_is_recommended_by_default(monkeypatch):
    monkeypatch.setattr("app.agents.purchase_agent.vector_store.find_similar_items", lambda *a, **k: [])

    result = PurchaseAgent().run(image_url="x", attributes=_attrs(), user_id=USER_ID)

    assert result["verdict"] == "recommended"
    assert result["similar_item_ids"] == []
    assert result["catalog_alternatives"] == [{"name": "fake alternative"}]


def test_near_duplicate_in_same_category_is_not_recommended(monkeypatch):
    existing_id = str(uuid.uuid4())
    matches = [{"item_id": existing_id, "score": 0.97, "category": "haut"}]
    monkeypatch.setattr("app.agents.purchase_agent.vector_store.find_similar_items", lambda *a, **k: matches)

    result = PurchaseAgent().run(image_url="x", attributes=_attrs("haut"), user_id=USER_ID)

    assert result["verdict"] == "not_recommended"
    assert result["similar_item_ids"] == [existing_id]


def test_high_similarity_different_category_is_not_flagged_as_duplicate(monkeypatch):
    # Same score as the duplicate test, but a different category — shouldn't trip the
    # duplicate check (a near-identical embedding to a bag isn't "the same top").
    matches = [{"item_id": str(uuid.uuid4()), "score": 0.97, "category": "sac"}]
    monkeypatch.setattr("app.agents.purchase_agent.vector_store.find_similar_items", lambda *a, **k: matches)

    result = PurchaseAgent().run(image_url="x", attributes=_attrs("haut"), user_id=USER_ID)

    assert result["verdict"] != "not_recommended" or result["compatibility_score"] != 0.97


def test_low_similarity_wardrobe_gives_think_twice(monkeypatch):
    matches = [{"item_id": str(uuid.uuid4()), "score": 0.2, "category": "haut"}]
    monkeypatch.setattr("app.agents.purchase_agent.vector_store.find_similar_items", lambda *a, **k: matches)

    result = PurchaseAgent().run(image_url="x", attributes=_attrs("haut"), user_id=USER_ID)

    assert result["verdict"] == "think_twice"
    assert result["similar_item_ids"] == []

import uuid

import numpy as np
import pytest

from app.agents import purchase_agent as pa
from app.agents.purchase_agent import PurchaseAgent
from app.models.clothing_item import ClothingItem
from app.services.catalog_index import CatalogMatch

RNG = np.random.default_rng(0)


def _unit(vec) -> np.ndarray:
    vec = np.asarray(vec, dtype=float)
    return vec / np.linalg.norm(vec)


def _random_unit() -> np.ndarray:
    return _unit(RNG.normal(size=512))


def _near(vec: np.ndarray, similarity: float) -> np.ndarray:
    """A unit vector with exactly `similarity` cosine similarity to `vec`."""
    noise = RNG.normal(size=vec.shape)
    noise -= (noise @ vec) * vec
    noise = _unit(noise)
    return similarity * vec + np.sqrt(1 - similarity**2) * noise


def _item(category: str) -> ClothingItem:
    return ClothingItem(id=uuid.uuid4(), owner_id=uuid.uuid4(), image_url=f"https://x/{category}.jpg",
                        category=category)


def _attrs(embedding: np.ndarray, category: str = "haut") -> dict:
    return {"category": category, "colors": ["noir"], "pattern": "uni", "style": "Casual",
            "embedding": embedding}


def _run(attrs, wardrobe: list[tuple[ClothingItem, np.ndarray]], price=None) -> dict:
    return PurchaseAgent().run(
        attributes=attrs,
        wardrobe_items=[item for item, _ in wardrobe],
        embeddings={str(item.id): vec.tolist() for item, vec in wardrobe},
        price=price,
    )


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    """Isolates these tests from the real catalog index (CatalogIndex has its own tests)."""
    matches = [CatalogMatch(item_key=f"kontakt_produit-{int(p)}", name=f"Produit {p}", brand="Kontakt",
                            category="haut", price=p, image_url=f"https://x/{p}.jpg", similarity=0.9 - i * 0.01)
               for i, p in enumerate([40.0, 60.0, 80.0, 100.0, 120.0])]
    monkeypatch.setattr("app.agents.purchase_agent.CatalogIndex.search", lambda self, *a, **k: matches)
    monkeypatch.setattr("app.agents.purchase_agent.CatalogIndex.brand_affinity", lambda self, *a, **k: [])


@pytest.fixture
def compat_always(monkeypatch):
    def set_value(value: float):
        monkeypatch.setattr(pa.compatibility_model, "pair_compatibility", lambda a, b: value)
    return set_value


def test_out_of_scope_photo_is_rejected_without_searching_anything(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("should not search for a non-clothing photo")

    monkeypatch.setattr("app.agents.purchase_agent.CatalogIndex.search", fail)

    result = _run(_attrs(_random_unit(), "hors_perimetre"), [])

    assert result["verdict"] == "not_recommended"
    assert result["catalog_alternatives"] == []


def test_empty_wardrobe_without_price_is_recommended_by_default():
    result = _run(_attrs(_random_unit()), [])

    assert result["verdict"] == "recommended"
    assert result["score"] == pa.NO_EVIDENCE_SCORE
    assert result["factors"] == []
    assert result["outfits_unlocked"] == 0


def test_near_duplicate_is_never_recommended(compat_always):
    compat_always(0.9)
    candidate = _random_unit()
    owned_top = (_item("haut"), _near(candidate, 0.97))
    wardrobe = [owned_top, (_item("bas"), _random_unit()), (_item("bas"), _random_unit())]

    result = _run(_attrs(candidate), wardrobe)

    assert result["verdict"] == "not_recommended"
    assert result["score"] < pa.THINK_TWICE_SCORE
    assert result["duplicates"][0]["id"] == str(owned_top[0].id)


def test_similar_item_in_another_category_is_not_a_duplicate(compat_always):
    compat_always(0.9)
    candidate = _random_unit()
    wardrobe = [(_item("sac"), _near(candidate, 0.97)), (_item("bas"), _random_unit())]

    result = _run(_attrs(candidate), wardrobe)

    assert result["duplicates"] == []
    assert result["verdict"] != "not_recommended"


def test_each_compatible_bas_unlocks_one_outfit_for_a_haut(monkeypatch):
    good_bas = [_item("bas"), _item("bas")]
    bad_bas = _item("bas")
    vectors = {id(i): _random_unit() for i in [*good_bas, bad_bas]}
    good_vectors = {tuple(vectors[id(i)]) for i in good_bas}
    monkeypatch.setattr(pa.compatibility_model, "pair_compatibility",
                        lambda a, b: 0.8 if tuple(b) in good_vectors else 0.2)
    wardrobe = [(i, vectors[id(i)]) for i in [*good_bas, bad_bas]]

    result = _run(_attrs(_random_unit(), "haut"), wardrobe)

    assert result["outfits_unlocked"] == 2
    unlocked_ids = {o["items"][0]["id"] for o in result["outfit_examples"]}
    assert unlocked_ids == {str(i.id) for i in good_bas}


def test_optional_piece_completes_existing_haut_bas_bases(compat_always):
    compat_always(0.8)
    wardrobe = [(_item("haut"), _random_unit()), (_item("haut"), _random_unit()),
                (_item("bas"), _random_unit())]

    result = _run(_attrs(_random_unit(), "chaussures"), wardrobe)

    assert result["outfits_unlocked"] == 2  # 2 hauts x 1 bas
    assert all(len(o["items"]) == 2 for o in result["outfit_examples"])


def test_versatile_piece_scores_higher_than_incompatible_one(compat_always):
    wardrobe = [(_item("bas"), _random_unit()) for _ in range(4)]
    candidate = _random_unit()

    compat_always(0.9)
    versatile = _run(_attrs(candidate), wardrobe)
    compat_always(0.1)
    incompatible = _run(_attrs(candidate), wardrobe)

    assert versatile["score"] > incompatible["score"]
    assert incompatible["outfits_unlocked"] == 0


def test_factor_weights_are_renormalized_over_available_factors(compat_always):
    compat_always(0.8)
    wardrobe = [(_item("bas"), _random_unit())]  # no haut owned -> no uniqueness factor

    result = _run(_attrs(_random_unit()), wardrobe)

    keys = {f["key"] for f in result["factors"]}
    assert keys == {"versatility", "style_fit"}
    assert sum(f["weight"] for f in result["factors"]) == pytest.approx(1.0, abs=0.01)


def test_price_insight_compares_against_visually_similar_products():
    result = _run(_attrs(_random_unit()), [], price=50.0)

    insight = result["price_insight"]
    assert insight["market_median"] == 80.0
    assert insight["percentile"] == 0.2  # only the 40 TND product is cheaper
    assert insight["label"] == "bon_prix"
    assert [f["key"] for f in result["factors"]] == ["price"]


def test_expensive_price_lowers_the_score():
    cheap = _run(_attrs(_random_unit()), [], price=30.0)
    expensive = _run(_attrs(_random_unit()), [], price=300.0)

    assert expensive["price_insight"]["label"] == "cher"
    assert cheap["score"] > expensive["score"]


def test_cheaper_alternatives_come_first_when_a_price_is_given():
    result = _run(_attrs(_random_unit()), [], price=70.0)

    flags = [a["cheaper"] for a in result["catalog_alternatives"]]
    assert flags[:2] == [True, True]
    assert all(a["price"] < 70.0 for a in result["catalog_alternatives"][:2])


def test_alternatives_link_to_the_brand_product_page():
    result = _run(_attrs(_random_unit()), [])

    alt = result["catalog_alternatives"][0]
    assert alt["product_url"].startswith("https://kontakt.com.tn/products/produit-")
    assert alt["buyable"] is True


def test_cost_per_wear_needs_a_price():
    assert _run(_attrs(_random_unit()), [])["cost_per_wear"] is None


def test_versatile_piece_costs_less_per_wear(compat_always):
    wardrobe = [(_item("bas"), _random_unit()) for _ in range(4)]
    compat_always(0.9)
    versatile = _run(_attrs(_random_unit()), wardrobe, price=60.0)["cost_per_wear"]
    compat_always(0.1)
    isolated = _run(_attrs(_random_unit()), wardrobe, price=60.0)["cost_per_wear"]

    assert versatile["wears_per_year"] > isolated["wears_per_year"]
    assert versatile["cost_per_wear"] < isolated["cost_per_wear"]


def test_cost_per_wear_without_wardrobe_uses_the_typical_rate():
    cpw = _run(_attrs(_random_unit()), [], price=60.0)["cost_per_wear"]

    assert cpw == {"wears_per_year": pa.TYPICAL_WEARS_PER_YEAR["haut"], "cost_per_wear": 2.0, "label": "excellent"}


def test_brands_are_matched_on_the_piece_pulled_towards_the_wardrobe_style(monkeypatch, compat_always):
    compat_always(0.5)
    queries = []
    monkeypatch.setattr("app.agents.purchase_agent.CatalogIndex.brand_affinity",
                        lambda self, query, **k: queries.append(query) or [{"name": "Lyoum"}])
    candidate, style = _random_unit(), _random_unit()

    result = _run(_attrs(candidate), [(_item("bas"), style)])

    assert result["tunisian_brands"] == [{"name": "Lyoum"}]
    query = queries[0]
    assert np.linalg.norm(query) == pytest.approx(1.0)
    assert query @ candidate > query @ style > 0

import httpx
import pytest

from app.services import store_checkout, tunisian_brands

SHOPIFY_PRODUCT = {
    "title": "Pull olive",
    "price": 8900,
    "compare_at_price": 11900,
    "available": True,
    "featured_image": "//cdn.shopify.com/pull.jpg",
    "variants": [
        {"id": 11, "title": "S / Vert", "available": True, "price": 8900},
        {"id": 12, "title": "M / Vert", "available": False, "price": 8900},
    ],
}


class _Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def empty_cache():
    store_checkout._cache.clear()


def test_brand_is_found_from_the_item_key_prefix():
    assert tunisian_brands.by_item_key("chedly_sisters_black-lace").name == "Chedly Sisters"
    assert tunisian_brands.by_item_key("rooh_clothing_set").name == "Rooh Clothing"
    assert tunisian_brands.by_item_key("unknown_thing") is None


def test_live_product_reads_sizes_stock_and_builds_checkout_links(monkeypatch):
    calls = []
    monkeypatch.setattr(store_checkout.httpx, "get",
                        lambda url, **k: calls.append(url) or _Response(SHOPIFY_PRODUCT))

    product = store_checkout.live_product("lyoum_pull-olive")

    assert calls == ["https://lyoum.co/products/pull-olive.js"]
    assert product["price"] == 89.0
    assert product["compare_at_price"] == 119.0
    assert product["image_url"] == "https://cdn.shopify.com/pull.jpg"
    assert [(v["title"], v["available"]) for v in product["variants"]] == [("S / Vert", True), ("M / Vert", False)]
    assert product["variants"][0]["checkout_url"] == "https://lyoum.co/cart/11:1"


def test_live_product_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(store_checkout.httpx, "get",
                        lambda url, **k: calls.append(url) or _Response(SHOPIFY_PRODUCT))

    store_checkout.live_product("lyoum_pull-olive")
    store_checkout.live_product("lyoum_pull-olive")

    assert len(calls) == 1


def test_products_of_unknown_or_non_shopify_brands_are_never_fetched(monkeypatch):
    monkeypatch.setattr(store_checkout.httpx, "get", lambda *a, **k: pytest.fail("no request expected"))

    for key in ["ha_0038787", "evil.example.com_x"]:
        with pytest.raises(store_checkout.ProductUnavailable):
            store_checkout.live_product(key)


def test_store_errors_become_unavailable(monkeypatch):
    monkeypatch.setattr(store_checkout.httpx, "get", lambda *a, **k: _Response({}, status=404))

    with pytest.raises(store_checkout.ProductUnavailable):
        store_checkout.live_product("kontakt_gone")
    assert store_checkout.live_prices(["kontakt_gone"]) == {"kontakt_gone": None}

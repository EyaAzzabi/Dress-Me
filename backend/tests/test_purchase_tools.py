import pytest

from app.services.purchase_tools import PurchaseToolSandbox, UnknownPurchaseTool


def test_sandbox_rejects_unknown_tools():
    with pytest.raises(UnknownPurchaseTool):
        PurchaseToolSandbox().call("os_system", command="rm -rf /")


def test_sandbox_only_exposes_purchase_tools():
    names = set(PurchaseToolSandbox().names())

    assert names == {
        "inspect_wardrobe", "search_tunisian_catalog", "compare_market_price",
        "rank_tunisian_brands", "estimate_cost_per_wear",
    }

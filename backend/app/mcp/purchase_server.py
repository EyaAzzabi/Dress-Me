"""MCP server for DressMe Purchase tools (stdio).

Wraps the existing PurchaseToolSandbox: same names, same sandbox.call.
Does not change the ReAct loop in purchase_llm.py.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
from mcp.server.fastmcp import FastMCP

from app.services.purchase_tools import TOOL_SPECS, PurchaseToolSandbox, UnknownPurchaseTool

mcp = FastMCP("dressme-purchase")
_sandbox = PurchaseToolSandbox()
_DESCRIPTIONS = {spec["name"]: spec["description"] for spec in TOOL_SPECS}


def _bind_demo_context() -> None:
    embedding = np.zeros(512, dtype=float)
    embedding[0] = 1.0
    _sandbox.bind(
        embedding=embedding,
        category="haut",
        owned=[],
        price=75.0,
        item={"category": "haut", "color": "bleu"},
    )


def _invoke(name: str, **kwargs: Any) -> Any:
    try:
        result = _sandbox.call(name, **kwargs)
    except UnknownPurchaseTool as exc:
        return {"error": str(exc)}
    return json.loads(json.dumps(result, default=str))


_bind_demo_context()


@mcp.tool(name="inspect_wardrobe", description=_DESCRIPTIONS["inspect_wardrobe"])
def inspect_wardrobe() -> Any:
    return _invoke("inspect_wardrobe")


@mcp.tool(name="search_tunisian_catalog", description=_DESCRIPTIONS["search_tunisian_catalog"])
def search_tunisian_catalog(limit: int = 20) -> Any:
    return _invoke("search_tunisian_catalog", limit=limit)


@mcp.tool(name="compare_market_price", description=_DESCRIPTIONS["compare_market_price"])
def compare_market_price() -> Any:
    return _invoke("compare_market_price")


@mcp.tool(name="rank_tunisian_brands", description=_DESCRIPTIONS["rank_tunisian_brands"])
def rank_tunisian_brands() -> Any:
    return _invoke("rank_tunisian_brands")


@mcp.tool(name="estimate_cost_per_wear", description=_DESCRIPTIONS["estimate_cost_per_wear"])
def estimate_cost_per_wear() -> Any:
    return _invoke("estimate_cost_per_wear")


if __name__ == "__main__":
    mcp.run(transport="stdio")

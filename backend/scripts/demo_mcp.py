"""Démo MCP Purchase : liste, appels, puis format modèle → parse_action → MCP.

Ne charge pas Qwen. Depuis backend/ :
    python -m scripts.demo_mcp
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.mcp.purchase_client import open_session  # noqa: E402
from app.ml.purchase_llm import parse_action  # noqa: E402
from app.services.purchase_tools import TOOL_SPECS  # noqa: E402


def _dump(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    elif hasattr(value, "content"):
        value = getattr(value, "content", value)
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


async def main() -> int:
    async with open_session() as client:
        print("=" * 60)
        print("Étape a) Liste des 5 outils (schéma MCP)")
        print("=" * 60)
        tools = await client.list_tools()
        for tool in tools:
            name = getattr(tool, "name", None)
            description = getattr(tool, "description", None)
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
            print(f"\n- {name}")
            print(f"  description : {description}")
            print(f"  schema      : {_dump(schema)}")
        print(f"\nAttendu : {len(TOOL_SPECS)} outils = {[s['name'] for s in TOOL_SPECS]}")
        print(f"Reçu    : {len(tools)} outils")

        print()
        print("=" * 60)
        print("Étape b) Appel de chaque outil via le client MCP")
        print("=" * 60)
        for spec in TOOL_SPECS:
            name = spec["name"]
            arguments = {"limit": 3} if name == "search_tunisian_catalog" else {}
            print(f"\n>>> call_tool({name!r}, {arguments})")
            result = await client.call_tool(name, arguments)
            print(_dump(result))

        print()
        print("=" * 60)
        print("Étape c) Format modèle → parse_action → MCP + outil inconnu")
        print("=" * 60)
        raw = '<tool_call>{"name": "inspect_wardrobe"}</tool_call>'
        print(f"texte modèle : {raw}")
        action = parse_action(raw)
        print(f"parse_action : {action}")
        if action and action.get("type") == "tool":
            result = await client.call_tool(action["name"], action.get("args") or {})
            print("résultat MCP :")
            print(_dump(result))

        unknown = '<tool_call>{"name": "os_system"}</tool_call>'
        print(f"\ntexte modèle (interdit) : {unknown}")
        bad = parse_action(unknown)
        print(f"parse_action : {bad}")
        try:
            denied = await client.call_tool(bad["name"], bad.get("args") or {})
            print("résultat MCP (doit être une erreur) :")
            print(_dump(denied))
        except Exception as exc:
            print(f"refusé (security) : {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

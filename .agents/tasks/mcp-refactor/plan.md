# Implementation Plan - MCP Refactor for RecommendationAgent

## Overview
Refactor RecommendationAgent to use MCP (Model Context Protocol - JSON-RPC 2.0) for tool calls with automatic fallback to direct Python functions. This preserves backward compatibility while enabling dynamic MCP tool invocation.

## Decision Rationale
- **MCPClient pattern**: Singleton instance stored as instance attribute for simplicity
- **Fallback strategy**: Silent fallback on connection error or when `mcp_enabled=False`
- **Sync over async**: Since recommendation_agent.py is synchronous, MCPClient uses sync httpx but exposes async-compatible interface
- **JSON-RPC 2.0**: Standard format with "jsonrpc": "2.0", "method", "params", "id"

---

- [ ] 1. Ajouter les paramètres de configuration MCP dans Settings (config.py).
      Fichiers: e:\Téléchargements\Dress-Me-main\Dress-Me-main\backend\app\core\config.py
      Vérification: `python -c "from app.core.config import get_settings; s=get_settings(); print(s.mcp_enabled, s.mcp_server_urls)"` — les nouvelles propriétés existent.

- [ ] 2. Créer la classe MCPClient avec fallback vers recommendation_tools.
      Fichiers: e:\Téléchargements\Dress-Me-main\Dress-Me-main\backend\app\agents\mcp_client.py
      Vérification: `python -c "from app.agents.mcp_client import MCPClient; c = MCPClient(); print(c)"` — l'import réussit.

- [ ] 3. Ajouter les schémas MCP pour chaque tool dans recommendation_tools.py.
      Fichiers: e:\Téléchargements\Dress-Me-main\Dress-Me-main\backend\app\agents\recommendation_tools.py
      Vérification: `python -c "from app.agents.recommendation_tools import MCP_TOOL_SCHEMAS; print(len(MCP_TOOL_SCHEMAS))"` — affiche 5.

- [ ] 4. Modifier recommendation_agent.py pour utiliser MCPClient.call_tool().
      Fichiers: e:\Téléchargements\Dress-Me-main\Dress-Me-main\backend\app\agents\recommendation_agent.py
      Vérification: `python -c "from app.agents.recommendation_agent import RecommendationAgent; print(RecommendationAgent.name)"` — l'agent se charge sans erreur.

---

## Détails des changements

### 1. config.py — Ajouter les paramètres MCP

Ajouter dans la classe `Settings` (après `llm_cache_max_entries`):

```python
# MCP (Model Context Protocol) configuration - opt-in, no breaking change
mcp_enabled: bool = False
mcp_server_urls: str = "{}"  # JSON string: '{"get_weather": "http://localhost:8001", ...}'
```

Ajouter une propriété property parsing:

```python
@property
def mcp_server_urls_dict(self) -> dict[str, str]:
    import json
    return json.loads(self.mcp_server_urls or "{}")
```

### 2. mcp_client.py — Classe MCPClient complète

**Structure:**
- `__init__`: lit Settings, stocke `_mcp_enabled`, `_server_urls`
- `call_tool(tool_name: str, params: dict) -> dict`: méthode principale
  - Si `_mcp_enabled` et URL existe pour tool → fait requête JSON-RPC
  - Sinon → appelle `_dispatch_fallback(tool_name, params)`
- `_dispatch_fallback(tool_name: str, params: dict) -> dict`: mappe tool name vers fonction Python
- `_call_mcp(tool_name: str, params: dict) -> dict`: effectue requête HTTP JSON-RPC
- Logging: ogni chiamata logguée avec "via MCP" ou "via fallback"

**Tools supportés:**
- `get_weather` → `recommendation_tools.get_weather`
- `fetch_wardrobe` → `recommendation_tools.fetch_wardrobe`
- `calculate_compatibility` → `recommendation_tools.calculate_compatibility`
- `retrieve_past_outfits` → `recommendation_tools.retrieve_past_outfits`
- `evaluate_outfit` → `recommendation_tools.evaluate_outfit`

### 3. recommendation_tools.py — Ajouter les schémas MCP

Ajouter à la fin du fichier (après `_season_compatible`):

```python
MCP_TOOL_SCHEMAS = {
    "get_weather": {
        "name": "get_weather",
        "description": "Fetch current weather for a city",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    "fetch_wardrobe": {
        "name": "fetch_wardrobe",
        "description": "Filter wardrobe items by season and constraints",
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "season": {"type": ["string", "null"]},
                "occasion_category": {"type": ["string", "null"]},
                "formality": {"type": ["integer", "null"]}
            },
            "required": ["items"]
        }
    },
    "calculate_compatibility": {
        "name": "calculate_compatibility",
        "description": "Calculate pairwise compatibility score for outfit items",
        "inputSchema": {
            "type": "object",
            "properties": {
                "outfit_items": {"type": "array"},
                "vectors": {"type": "array"},
                "season": {"type": ["string", "null"]},
                "occasion": {"type": ["string", "null"]}
            },
            "required": ["outfit_items", "vectors"]
        }
    },
    "retrieve_past_outfits": {
        "name": "retrieve_past_outfits",
        "description": "Retrieve historical outfits similar to current outfit",
        "inputSchema": {
            "type": "object",
            "properties": {
                "references": {"type": ["object", "null"]},
                "outfit_mean_vec": {"type": "array"}
            },
            "required": ["references", "outfit_mean_vec"]
        }
    },
    "evaluate_outfit": {
        "name": "evaluate_outfit",
        "description": "Evaluate outfit quality and confidence",
        "inputSchema": {
            "type": "object",
            "properties": {
                "outfit": {"type": "array"},
                "score": {"type": "number"},
                "context": {"type": ["object", "null"]},
                "references": {"type": ["object", "null"]}
            },
            "required": ["outfit", "score"]
        }
    }
}
```

### 4. recommendation_agent.py — Utiliser MCPClient

**Modifications:**
1. Ajouter import: `from app.agents.mcp_client import MCPClient`
2. Dans `run()`, avant le premier appel tool:
   ```python
   mcp_client = getattr(self, '_mcp_client', None)
   if mcp_client is None:
       mcp_client = MCPClient()
       self._mcp_client = mcp_client
   ```
3. Remplacer les 5 appels directs:
   - `get_weather(city)` → `mcp_client.call_tool("get_weather", {"city": city})`
   - `fetch_wardrobe(wardrobe_items, ...)` → `mcp_client.call_tool("fetch_wardrobe", {"items": wardrobe_items, ...})`
   - `calculate_compatibility(outfit, outfit_vecs, ...)` → `mcp_client.call_tool("calculate_compatibility", {"outfit_items": outfit, "vectors": outfit_vecs, ...})`
   - `retrieve_past_outfits(references, outfit_mean)` → `mcp_client.call_tool("retrieve_past_outfits", {"references": references, "outfit_mean_vec": outfit_mean.tolist() if hasattr(outfit_mean, 'tolist') else outfit_mean})`
   - `evaluate_outfit(outfit, score, eval_context, references)` → `mcp_client.call_tool("evaluate_outfit", {"outfit": outfit, "score": score, "context": eval_context, "references": references})`

**Contraintes absolues respectées:**
- Sortie de `run()` inchangée (mêmes clés dans le dict retourné)
- Signature `run()` identique
- Fallback automatique si MCP non disponible
- Pas de modification des autres agents
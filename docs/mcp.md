# MCP Purchase (DressMe)

Le LLM Purchase ne parle pas au sandbox Python directement dans cette démo :
il émet une balise, le parseur lit le nom, le **client MCP** l’envoie au
**serveur MCP**, qui appelle `PurchaseToolSandbox.call` (liste blanche).

```
Qwen2.5-1.5B + LoRA
        │
        │  génère
        ▼
<tool_call>{"name": "inspect_wardrobe"}</tool_call>
        │
        │  parse_action  (app/ml/purchase_llm.py)
        ▼
{type: "tool", name: "inspect_wardrobe", args: {}}
        │
        │  PurchaseMCPClient.call_tool
        ▼
client MCP  ──stdio──►  serveur FastMCP "dressme-purchase"
                              │
                              │  sandbox.call(name, **args)
                              ▼
                    PurchaseToolSandbox
                    (5 noms, UnknownPurchaseTool sinon)
```

La boucle ReAct (`run_agent`) n’est pas modifiée. MCP est une façade sur les
mêmes 5 outils (`TOOL_SPECS`).

## Lancer

Depuis `Dress-Me/backend/`, avec le venv :

```powershell
.\.venv\Scripts\python.exe -m pip install "mcp[cli]"
.\.venv\Scripts\python.exe -m scripts.demo_mcp
```

Serveur seul (stdio, pour un client MCP externe) :

```powershell
.\.venv\Scripts\python.exe -m app.mcp.purchase_server
```

## Fichiers

- `backend/app/mcp/purchase_server.py` — FastMCP, 5 tools, `sandbox.call`
- `backend/app/mcp/purchase_client.py` — `list_tools` / `call_tool`
- `backend/scripts/demo_mcp.py` — liste, appels, parse_action, outil inconnu
- `backend/app/services/purchase_tools.py` — sandbox (inchangé)

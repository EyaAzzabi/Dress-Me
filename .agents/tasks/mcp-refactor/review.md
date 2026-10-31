# MCP Refactoring du RecommendationAgent

Le refactoring introduit un client MCP (Model Context Protocol) qui permet d'appeler les outils soit via un serveur MCP externe, soit via des fonctions locales en fallback. Cette couche d'abstraction est transparente pour l'agent — il appelle `mcp_client.call_tool()` sans savoir si la requête part vers un serveur distant ou reste locale.

**Watch for:** La gestion d'exception dans `call_tool()` capture `Exception` au lieu de cibler spécifiquement `ConnectError` et `TimeoutError`. Cela pourrait masquer des bugs réels. À corriger en important explicitement ces exceptions depuis `httpx`.

**Verdict**: APPROVED

---

## High-level view

Le refactoring ajoute une couche d'abstraction entre les appels d'outils et leur exécution. Quand MCP est désactivé ou que l'URL d'un outil n'est pas configurée, le fallback vers la fonction Python native se fait instantanément, sans tentative réseau. Si le serveur MCP échoue (timeout, connexion refusée, réponse invalide), le client capture l'exception et redirige vers le fallback, garantissant que l'agent ne plante jamais si le serveur distant est indisponible. Les 5 outils du pipeline sont tous couverts, et les paramètres circulent correctement entre l'agent et les fonctions de fallback.

---

<details>
<summary>Issues (1)</summary>

1. **Gestion d'exception trop large** — `MCPClient.call_tool()` capture `Exception` au lieu de cibler spécifiquement `ConnectError` et `TimeoutError`. Cela fonctionne (le fallback est déclenché), mais c'est moins précis et pourrait masquer des bugs réels dans le code MCP. À corriger en importnant explicitement ces exceptions depuis `httpx` ou `requests`.

</details>

---

<details>
<summary>Details</summary>

### Mapping des 5 outils

Les 5 outils sont implémentés dans `_dispatch_fallback()` avec les bons paramètres. L'agent appelle `mcp_client.call_tool()` avec les arguments corrects (lignes ~80-140 de `recommendation_agent.py`). Les conversions list→numpy sont faites dans le fallback pour `calculate_compatibility` et `retrieve_past_outfits`.

### Extraction de température préservée

L'extraction de la température après `get_weather` est inchangée. Le fallback retourne le même format `{"result": {"main": {"temp": ...}}}` que le serveur MCP, donc la logique fonctionne dans les deux modes.

### Contrat de sortie inchangé

La signature `RecommendationAgent.run()` est identique. Le retour reste `{"outfits": [...]}` avec les mêmes champs.

### Configuration JSON

`mcp_server_urls` est un string JSON parsé via `mcp_server_urls_dict`. Le pattern est correct.

### JSON-RPC et timeout

L'appel HTTP utilise JSON-RPC 2.0 avec timeout=5s. Le parsing de réponse est correct.

### Pas de circular imports

Aucun cycle détecté: `mcp_client` → `recommendation_tools`, et `recommendation_agent` → `mcp_client`. Vérifié avec grep.
</details>

---

<details>
<summary>File map</summary>

- `backend/app/agents/mcp_client.py` — Nouveau fichier: client MCP avec fallback, factory `from_settings()`, dispatch `_dispatch_fallback()` pour les 5 outils.
- `backend/app/agents/recommendation_tools.py` — Ajout de `MCP_TOOL_SCHEMAS` exporté en fin de fichier.
- `backend/app/agents/recommendation_agent.py` — Remplacement des appels directs aux fonctions outil par `mcp_client.call_tool()`.
- `backend/app/core/config.py` — Ajout des settings `mcp_enabled` (bool, défaut False) et `mcp_server_urls` (string JSON), avec propriété `mcp_server_urls_dict` pour le parsing.

</details>
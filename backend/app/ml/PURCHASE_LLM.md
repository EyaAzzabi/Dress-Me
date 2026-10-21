# Purchase LLM — agent à outils + fine-tuning

## Ce que la prof demande

Un **LLM fine-tuné** qui **appelle des tools dans un sandbox**, pas un texte écrit après coup.

## Modèle

**Qwen2.5-1.5B-Instruct** — français, Apache-2.0, assez petit pour un LoRA sur Colab T4.

FashionCLIP / SegFormer restent la vision. Le LLM **ne voit jamais l’image ni l’embedding**.

## Sandbox (tools)

Fichier : `app/services/purchase_tools.py`

Le modèle n’a ni Python, ni SQL, ni internet. Il ne peut émettre que :

| Tool | Ce qu’il calcule |
|---|---|
| `inspect_wardrobe` | doublons, tenues, style (FashionCLIP + Polyvore) |
| `search_tunisian_catalog` | k plus proches voisins du catalogue tunisien |
| `compare_market_price` | percentile du prix parmi ces voisins |
| `rank_tunisian_brands` | affinité des marques tunisiennes |
| `estimate_cost_per_wear` | coût par port |

Un autre nom → `UnknownPurchaseTool`. L’embedding reste **dans le sandbox**, pas dans le prompt.

## Boucle agent

```text
LLM  →  <tool_call>{"name": "inspect_wardrobe"}</tool_call>
Sandbox → <tool_result>{…scores…}</tool_result>
LLM  →  <tool_call>{"name": "search_tunisian_catalog"}</tool_call>
…
LLM  →  <final>{"explanation": "Bon achat : …"}</final>
```

Code : `app/ml/purchase_llm.py` (`run_agent`). Max 6 appels.

## Fine-tuning (adaptation)

On n’entraîne pas les 1,5B poids. **LoRA r=16** sur l’attention.

Données : trajectoires d’outils (`app/data/purchase_llm_sft.jsonl`), pas des phrases isolées.
Le modèle apprend **quand appeler quel tool**, puis à rédiger uniquement à partir des `<tool_result>`.

```bash
pip install -r requirements-purchase-llm.txt
python -m scripts.build_purchase_llm_dataset
python -m scripts.finetune_purchase_llm    # GPU (Colab T4)
```

Sans GPU : même format d’outils via Groq / Mistral / Ollama (`LLM_PROVIDER`). L’adapter LoRA remplace l’API une fois entraîné.

## Phrase pour la prof

> On a adapté Qwen2.5-1.5B-Instruct par LoRA pour en faire un agent d’achat à outils. Le modèle apprend à interroger un sandbox fermé (garde-robe, catalogue tunisien, prix, marques). Les scores restent calculés par les modèles de vision ; le LLM décide des tools et rédige le conseil.

# %% [markdown]
# # DressMe — Fine-tune LoRA du LLM Purchase (agent à outils)
#
# **À lancer sur Google Colab avec GPU T4** (Runtime → Change runtime type → GPU).
#
# ## Idée
# - Modèle de base : `Qwen/Qwen2.5-1.5B-Instruct` (français, 1,5B paramètres).
# - On **ne réentraîne pas** les 1,5 milliard de poids.
# - **LoRA** : on apprend de petites matrices (`r=16`) sur l’attention.
# - Le modèle apprend à **appeler des tools** dans un sandbox, puis à rédiger
#   un conseil d’achat **uniquement** à partir des résultats.
#
# FashionCLIP / SegFormer restent la vision. Le LLM ne voit jamais l’image.

# %%
# Colab : Runtime → GPU (T4)
import json
from pathlib import Path

import torch

print("GPU :", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "aucun (lent)")

# %%
# %pip install -q peft datasets accelerate transformers

# %% [markdown]
# ## 1. Sandbox : les seuls tools autorisés
#
# Le LLM n’a ni Python, ni internet. Il ne peut émettre que ces noms.

# %%
TOOLS = [
    "inspect_wardrobe",          # doublons, tenues, style (garde-robe)
    "search_tunisian_catalog",   # voisins visuels FashionCLIP
    "compare_market_price",      # percentile du prix tunisien
    "rank_tunisian_brands",      # marques proches
    "estimate_cost_per_wear",    # coût par port
]

SYSTEM = f"""Tu es l'agent d'achat DressMe. Tu n'inventes ni prix, ni score, ni marque.
Tu appelles d'abord un outil du sandbox, un seul à la fois.

Outils : {", ".join(TOOLS)}

Format :
<tool_call>{{"name": "inspect_wardrobe"}}</tool_call>

Quand tu as assez de faits :
<final>{{"explanation": "2 à 4 phrases, tutoiement."}}</final>
"""

print(SYSTEM)

# %% [markdown]
# ## 2. Dataset : trajectoires d’outils (pas des phrases isolées)
#
# Chaque exemple = dialogue complet : appels de tools → résultats → explication.

# %%
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
ADAPTER_DIR = Path("/content/purchase_llm") if Path("/content").exists() else Path("purchase_llm_adapter")


def example(task: dict, tools: dict, explanation: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Analyse cet achat.\n" + json.dumps(task, ensure_ascii=False)},
    ]
    for name, result in tools.items():
        messages.append({"role": "assistant", "content": f'<tool_call>{{"name": "{name}"}}</tool_call>'})
        messages.append({"role": "user", "content": "<tool_result>" + json.dumps(result, ensure_ascii=False) + "</tool_result>"})
    messages.append({
        "role": "assistant",
        "content": "<final>" + json.dumps({"explanation": explanation}, ensure_ascii=False) + "</final>",
    })
    return {"messages": messages}


rows = [
    example(
        {"category": "haut", "price": 59, "wardrobe_size": 0},
        {
            "inspect_wardrobe": {"wardrobe_size": 0, "duplicates": [], "outfits_unlocked": 0},
            "search_tunisian_catalog": [{"name": "Tee", "brand": "Kontakt", "price": 49}],
            "compare_market_price": {"price": 59, "market_median": 70, "label": "bon_prix"},
            "rank_tunisian_brands": [{"name": "Kontakt", "affinity": 0.71}],
        },
        "Ta garde-robe est encore vide, rien ne s'oppose à ce haut. "
        "À 59 TND tu es sous la médiane du marché tunisien (70 TND).",
    ),
    example(
        {"category": "bas", "price": 89, "wardrobe_size": 8},
        {
            "inspect_wardrobe": {"wardrobe_size": 8, "duplicates": [{"similarity": 0.96}], "outfits_unlocked": 2},
            "search_tunisian_catalog": [{"name": "Jean", "brand": "Barsha", "price": 65}],
            "compare_market_price": {"price": 89, "market_median": 70, "label": "cher"},
            "rank_tunisian_brands": [{"name": "Barsha", "affinity": 0.68}],
        },
        "Tu as déjà une pièce presque identique : garde ton budget. "
        "89 TND dépasse la médiane (70 TND) — Barsha a un modèle à 65 TND.",
    ),
    example(
        {"category": "robe", "price": 75, "wardrobe_size": 12},
        {
            "inspect_wardrobe": {"wardrobe_size": 12, "duplicates": [], "outfits_unlocked": 5},
            "search_tunisian_catalog": [{"name": "Linen", "brand": "Chedly Sisters", "price": 79}],
            "compare_market_price": {"price": 75, "market_median": 80, "label": "prix_marche"},
            "rank_tunisian_brands": [{"name": "Chedly Sisters", "affinity": 0.73}],
        },
        "Bon achat : cette robe crée 5 tenues avec ce que tu as déjà. "
        "Le prix (75 TND) est dans la norme du marché (médiane 80 TND).",
    ),
]

print(len(rows), "exemples — un message assistant ressemble à :")
print(rows[0]["messages"][2]["content"])

# %% [markdown]
# ## 3. Tokenisation

# %%
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token


def tokenize(example):
    text = tokenizer.apply_chat_template(example["messages"], tokenize=False)
    tokens = tokenizer(text, truncation=True, max_length=1024, padding="max_length")
    tokens["labels"] = tokens["input_ids"].copy()
    return tokens


dataset = Dataset.from_list(rows).map(tokenize, remove_columns=["messages"])
print(dataset)

# %% [markdown]
# ## 4. LoRA : on gèle Qwen, on apprend ~quelques millions de paramètres
#
# `r=16` = rang des matrices LoRA (petit = léger, suffisant pour adapter le style + les tools).

# %%
from peft import LoraConfig, TaskType, get_peft_model

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    device_map="auto",
)
model = get_peft_model(model, LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
))
model.print_trainable_parameters()

# %% [markdown]
# ## 5. Entraînement (environ 10–20 min sur T4)

# %%
from transformers import Trainer, TrainingArguments

ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

trainer = Trainer(
    model=model,
    args=TrainingArguments(
        output_dir=str(ADAPTER_DIR / "runs"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        num_train_epochs=3,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        fp16=torch.cuda.is_available(),
    ),
    train_dataset=dataset,
)
trainer.train()
model.save_pretrained(ADAPTER_DIR)
tokenizer.save_pretrained(ADAPTER_DIR)
print("Adapter enregistré dans", ADAPTER_DIR)

# %% [markdown]
# ## 6. Après Colab
#
# Télécharge le dossier `purchase_llm` (fichiers `adapter_config.json` + poids LoRA)
# et copie-le ici sur ton PC :
#
# `Dress-Me/backend/app/ml/artifacts/purchase_llm/`
#
# Relance le backend. L’agent Purchase chargera ce LoRA et appellera les tools du sandbox.
#
# Code runtime : `backend/app/ml/purchase_llm.py` et `backend/app/services/purchase_tools.py`.

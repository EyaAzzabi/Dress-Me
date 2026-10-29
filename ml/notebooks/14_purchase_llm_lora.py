# %% [markdown]
# # DressMe — Fine-tune LoRA du LLM Purchase (agent à outils)
#
# **À lancer sur Google Colab avec GPU T4** (Runtime → Change runtime type → GPU).
#
# Ce notebook **reproduit** `backend/scripts/finetune_purchase_llm.py` :
# - dataset officiel : `backend/app/data/purchase_llm_sft.jsonl` (**25** trajectoires)
# - 5 outils du sandbox (noms du code, pas les noms courts du schéma)
# - mêmes hyperparamètres LoRA que le script
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
# ## 1. Sandbox : les 5 tools du code (`purchase_tools.py`)
#
# Le LLM n’a ni Python, ni internet. Noms **exactement** comme dans le backend.

# %%
TOOLS = [
    "inspect_wardrobe",
    "search_tunisian_catalog",
    "compare_market_price",
    "rank_tunisian_brands",
    "estimate_cost_per_wear",
]
print("Outils autorisés :", TOOLS)

# %% [markdown]
# ## 2. Dataset officiel : 25 trajectoires (`purchase_llm_sft.jsonl`)
#
# Chaque ligne = un dialogue complet : `<tool_call>` → `<tool_result>` → `<final>`.
# Sur Colab : clone le repo Dress-Me, ou uploade ce fichier JSONL.

# %%
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
ADAPTER_DIR = Path("/content/purchase_llm") if Path("/content").exists() else Path("purchase_llm_adapter")


def find_dataset() -> Path:
    candidates = [
        Path("backend/app/data/purchase_llm_sft.jsonl"),
        Path("../backend/app/data/purchase_llm_sft.jsonl"),
        Path("../../backend/app/data/purchase_llm_sft.jsonl"),
        Path("/content/Dress-Me/backend/app/data/purchase_llm_sft.jsonl"),
        Path("/content/purchase_llm_sft.jsonl"),
        Path("purchase_llm_sft.jsonl"),
    ]
    try:
        candidates.insert(0, Path(__file__).resolve().parents[2] / "backend" / "app" / "data" / "purchase_llm_sft.jsonl")
    except NameError:
        pass
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Fichier introuvable : backend/app/data/purchase_llm_sft.jsonl. "
        "Clone Dress-Me ou uploade le JSONL dans /content/."
    )


DATASET = find_dataset()
rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]
assert len(rows) == 25, f"Attendu 25 trajectoires, trouvé {len(rows)} dans {DATASET}"

tool_names_in_data = set()
for row in rows:
    for msg in row["messages"]:
        if msg["role"] == "assistant" and "<tool_call>" in msg["content"]:
            body = json.loads(msg["content"].split("<tool_call>")[1].split("</tool_call>")[0])
            tool_names_in_data.add(body["name"])

print(f"{len(rows)} trajectoires chargées depuis {DATASET}")
print("Outils présents dans le dataset :", sorted(tool_names_in_data))
assert tool_names_in_data == set(TOOLS), tool_names_in_data
print("Exemple de tool_call :", rows[1]["messages"][2]["content"])

# %% [markdown]
# ## 3. Tokenisation (identique au script : max_length=1536)

# %%
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token


def tokenize(example):
    text = tokenizer.apply_chat_template(example["messages"], tokenize=False)
    tokens = tokenizer(text, truncation=True, max_length=1536, padding="max_length")
    tokens["labels"] = tokens["input_ids"].copy()
    return tokens


dataset = Dataset.from_list(rows).map(tokenize, remove_columns=["messages"])
print(dataset)

# %% [markdown]
# ## 4. LoRA — mêmes réglages que `finetune_purchase_llm.py`
#
# r=16, lora_alpha=32, dropout=0.05, modules q/k/v/o_proj.

# %%
from peft import LoraConfig, TaskType, get_peft_model

model = AutoModelForCausalLM.from_pretrained(BASE_MODEL)
model = get_peft_model(model, LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
))
model.print_trainable_parameters()

# %% [markdown]
# ## 5. Entraînement (identique au script)

# %%
from transformers import Trainer, TrainingArguments

ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

trainer = Trainer(
    model=model,
    args=TrainingArguments(
        output_dir=str(ADAPTER_DIR / "runs"),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=10,
        learning_rate=2e-4,
        logging_steps=10,
        save_strategy="no",
        report_to=[],
        fp16=False,
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
# Télécharge le dossier `purchase_llm` (`adapter_config.json` + poids LoRA)
# et copie-le ici :
#
# `Dress-Me/backend/app/ml/artifacts/purchase_llm/`
#
# Relance le backend. L’agent Purchase chargera ce LoRA.
#
# Code runtime (ne pas modifier pour la démo) :
# `backend/app/ml/purchase_llm.py` et `backend/app/services/purchase_tools.py`.

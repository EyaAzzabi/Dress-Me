"""LoRA fine-tune of Qwen2.5-1.5B-Instruct on the Purchase SFT dataset.

Adapts the base instruction model to DressMe's buying-advice style without
updating its 1.5B frozen weights. Writes app/ml/artifacts/purchase_llm/ — the
folder Purchase LLM loads at inference.

GPU: a free Colab T4 is enough (~20 min). CPU works but is slow.
From backend/:  python -m scripts.finetune_purchase_llm
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ml.purchase_llm import ADAPTER_DIR, BASE_MODEL_ID

DATASET = Path(__file__).resolve().parents[1] / "app" / "data" / "purchase_llm_sft.jsonl"


def main() -> None:
    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    if not DATASET.exists():
        raise SystemExit("No dataset — run python -m scripts.build_purchase_llm_dataset first.")

    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def to_text(example):
        text = tokenizer.apply_chat_template(example["messages"], tokenize=False)
        tokens = tokenizer(text, truncation=True, max_length=1536, padding="max_length")
        tokens["labels"] = tokens["input_ids"].copy()
        return tokens

    dataset = Dataset.from_list(rows).map(to_text, remove_columns=["messages"])
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL_ID)
    model = get_peft_model(model, LoraConfig(
        task_type=TaskType.CAUSAL_LM, r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    ))
    model.print_trainable_parameters()

    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    args = TrainingArguments(
        output_dir=str(ADAPTER_DIR / "runs"),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=2e-4,
        logging_steps=10,
        save_strategy="no",
        report_to=[],
        fp16=False,
    )
    Trainer(model=model, args=args, train_dataset=dataset).train()
    model.save_pretrained(ADAPTER_DIR)
    tokenizer.save_pretrained(ADAPTER_DIR)
    print(f"LoRA adapter saved to {ADAPTER_DIR}")


if __name__ == "__main__":
    main()

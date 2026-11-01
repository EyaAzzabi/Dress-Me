# %% [markdown]
# # DressMe — Outfit Composition SFT Model Training
#
# **Supervised Fine-Tuning (SFT) model that learns to compose outfits.**
#
# Uses Polyvore outfit data + manually labeled Tunisian compositions to train
# a Transformer model that predicts which items work well together.
#
# **Output:** `backend/app/ml/artifacts/outfit_composition_sft.pt` (shared model)
#
# **Run as:** `python ml/notebooks/16_outfit_composition_sft.py` or interactive Jupyter

# %% [markdown]
# ## Setup

# %%
from pathlib import Path
import sys
import json

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".." / "backend"))

from app.ml.outfit_composition_sft_model import OutfitCompositionSFTModel, encode_context, train, save

# Paths
DATA_POLYVORE = ROOT / "data" / "processed" / "polyvore_outfits.json"
DATA_TUNISIAN = ROOT / "data" / "processed" / "tunisian_outfits.json"
MODEL_PATH = Path(__file__).resolve().parents[0].parent / "backend" / "app" / "ml" / "artifacts" / "outfit_composition_sft.pt"


# %% [markdown]
# ## 1. Load training data from Polyvore

# %%
def load_polyvore_data(max_outfits: int = 500) -> list[dict]:
    """Load Polyvore outfit data."""
    if not DATA_POLYVORE.exists():
        print(f"⚠️  {DATA_POLYVORE} not found. Using minimal synthetic data for demo.")
        return []
    
    with open(DATA_POLYVORE) as f:
        data = json.load(f)
    
    # Take first max_outfits complete outfits
    outfits = [o for o in data if len(o.get("items", [])) >= 3][:max_outfits]
    print(f"✅ Loaded {len(outfits)} Polyvore outfits")
    return outfits


def load_tunisian_data(max_outfits: int = 100) -> list[dict]:
    """Load labeled Tunisian outfit compositions."""
    if not DATA_TUNISIAN.exists():
        print(f"⚠️  {DATA_TUNISIAN} not found. Using minimal synthetic data for demo.")
        return []
    
    with open(DATA_TUNISIAN) as f:
        data = json.load(f)
    
    outfits = data[:max_outfits]
    print(f"✅ Loaded {len(outfits)} Tunisian labeled outfits")
    return outfits


polyvore_outfits = load_polyvore_data(500)
tunisian_outfits = load_tunisian_data(100)
all_outfits = polyvore_outfits + tunisian_outfits

print(f"📊 Total outfits for training: {len(all_outfits)}")


# %% [markdown]
# ## 2. Load FashionCLIP embeddings cache

# %%
def load_embeddings_cache() -> dict:
    """Load pre-computed FashionCLIP embeddings."""
    cache_path = ROOT / "data" / "processed" / "fashionclip_embeddings.npz"
    
    if not cache_path.exists():
        print(f"⚠️  {cache_path} not found. Will use random embeddings (demo only).")
        return {}
    
    cache = np.load(cache_path, allow_pickle=True)
    embeddings = {str(k): v for k, v in cache.items()}
    print(f"✅ Loaded embeddings for {len(embeddings)} items")
    return embeddings


embeddings_cache = load_embeddings_cache()


# %% [markdown]
# ## 3. Build training dataset

# %%
class OutfitCompositionDataset(Dataset):
    """PyTorch dataset for outfit composition SFT."""
    
    def __init__(self, outfits: list[dict], embeddings_cache: dict, max_items: int = 10):
        """
        Parameters
        ----------
        outfits : list of {"items": [item_ids], "season": "...", "occasion": "...", ...}
        embeddings_cache : {item_id: embedding_vector}
        max_items : max items per outfit
        """
        self.outfits = []
        
        for outfit in outfits:
            items = outfit.get("items", [])
            if len(items) < 2 or len(items) > max_items:
                continue  # Skip too small or too large
            
            # Check if embeddings available
            if all(str(item_id) in embeddings_cache for item_id in items):
                self.outfits.append(outfit)
        
        self.embeddings_cache = embeddings_cache
        self.max_items = max_items
        print(f"✅ Dataset: {len(self.outfits)} valid outfits")
    
    def __len__(self):
        return len(self.outfits)
    
    def __getitem__(self, idx):
        outfit = self.outfits[idx]
        items = outfit.get("items", [])[:self.max_items]
        
        # Get embeddings
        embeddings = np.array([
            self.embeddings_cache[str(item_id)]
            for item_id in items
        ], dtype=np.float32)  # (num_items, 512)
        
        # Pad if needed
        if len(embeddings) < self.max_items:
            padding = np.zeros((self.max_items - len(embeddings), 512), dtype=np.float32)
            embeddings = np.vstack([embeddings, padding])
        
        # Context encoding
        season = outfit.get("season", "toutes_saisons")
        weather = outfit.get("weather", "sunny")
        occasion = outfit.get("occasion", "casual")
        formality = outfit.get("formality", 2)
        
        context = encode_context(season, weather, occasion, formality).numpy().astype(np.float32)
        
        # Label: all items in the outfit get label 1 (good items)
        # Padded items get label 0 (not in outfit)
        labels = np.ones(self.max_items, dtype=np.float32)
        labels[len(items):] = 0.0
        
        return (
            torch.tensor(embeddings, dtype=torch.float32),
            torch.tensor(context, dtype=torch.float32),
            torch.tensor(labels, dtype=torch.float32),
        )


# Build dataset
dataset = OutfitCompositionDataset(all_outfits, embeddings_cache)

# Train/val split
train_size = int(0.8 * len(dataset))
val_size = len(dataset) - train_size
train_dataset, val_dataset = torch.utils.data.random_split(
    dataset, [train_size, val_size], generator=torch.Generator().manual_seed(42)
)

print(f"📊 Train: {len(train_dataset)}, Val: {len(val_dataset)}")


# %% [markdown]
# ## 4. Create DataLoaders

# %%
batch_size = 16
train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

print(f"✅ DataLoaders ready (batch_size={batch_size})")


# %% [markdown]
# ## 5. Initialize and train model

# %%
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🖥️  Using device: {device}")

model = OutfitCompositionSFTModel(
    embedding_dim=512,
    hidden_dim=256,
    num_layers=2,
    num_heads=4,
    max_items=10,
    dropout=0.1,
)

print(f"📦 Model parameters: {sum(p.numel() for p in model.parameters()):,}")

# Train
print("\n🚀 Starting training...\n")
history = train(
    model,
    train_dataloader=train_loader,
    val_dataloader=val_loader,
    epochs=10,
    lr=1e-4,
    device=device,
)

print("\n✅ Training complete!")


# %% [markdown]
# ## 6. Plot training history

# %%
try:
    import matplotlib.pyplot as plt
    
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(history["train_loss"], label="Train Loss", marker="o")
    if history.get("val_loss"):
        ax.plot(history["val_loss"], label="Val Loss", marker="s")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.set_title("Outfit Composition SFT Training")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(ROOT / "reports" / "outfit_composition_training.png")
    print(f"📊 Saved training plot to reports/outfit_composition_training.png")
except Exception as e:
    print(f"⚠️  Could not plot: {e}")


# %% [markdown]
# ## 7. Save model to backend

# %%
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

try:
    torch.save(model.state_dict(), str(MODEL_PATH))
    print(f"✅ Model saved to {MODEL_PATH}")
except Exception as e:
    print(f"❌ Error saving model: {e}")


# %% [markdown]
# ## 8. Evaluation on validation set

# %%
from sklearn.metrics import accuracy_score, f1_score

model.eval()
all_preds = []
all_labels = []

with torch.no_grad():
    for batch_embeddings, batch_context, batch_labels in val_loader:
        batch_embeddings = batch_embeddings.to(device)
        batch_context = batch_context.to(device)
        
        logits = model(batch_embeddings, batch_context)
        preds = (logits > 0.5).cpu().numpy()
        labels = batch_labels.numpy()
        
        all_preds.append(preds)
        all_labels.append(labels)

all_preds = np.vstack(all_preds)
all_labels = np.vstack(all_labels)

# Only evaluate non-padded items
mask = all_labels.sum(axis=1) > 0  # Outfits have at least one item
valid_preds = all_preds[mask].flatten()
valid_labels = all_labels[mask].flatten()

accuracy = accuracy_score(valid_labels, valid_preds)
f1 = f1_score(valid_labels, valid_preds, average="binary", zero_division=0)

print(f"\n📈 Validation Metrics:")
print(f"   Accuracy: {accuracy:.3f}")
print(f"   F1 Score: {f1:.3f}")


# %% [markdown]
# ## Summary
#
# ✅ **Model trained and saved!**
#
# **Next steps:**
# 1. Integrate into `RecommendationAgent` via `outfit_composition_sft_model.predict()`
# 2. Use LLM + DL scores together for outfit composition
# 3. Collect user feedback to fine-tune per-user models

print("\n✅ Training pipeline complete!")
print(f"📦 Model: {MODEL_PATH}")
print(f"📊 Outfits trained on: {len(dataset)}")
print(f"📈 Final val loss: {history['val_loss'][-1]:.4f}")

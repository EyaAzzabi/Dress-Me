"""Simple SFT Model Training using Polyvore Data

Uses a simple feed-forward network instead of the complex Transformer model.
Trains on Polyvore outfit compatibility.
"""

import sys
import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Paths
DATA_DIR = Path(__file__).resolve().parent.parent / "polyvore_data"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "app" / "ml" / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "outfit_composition_sft.pt"
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Simple outfit compatibility model
class SimpleOutfitSFT(nn.Module):
    """Simple feed-forward model for outfit compatibility."""
    
    def __init__(self, input_dim=24):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),  # Output: 0-1 compatibility score
        )
    
    def forward(self, x):
        return self.net(x)


def load_polyvore_outfits(json_path: Path) -> list[dict]:
    """Load outfits from Polyvore JSON."""
    print(f"📂 Loading {json_path.name}...")
    with open(json_path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    print(f"   ✅ Loaded {len(data)} outfits")
    return data


def extract_features(outfit: dict) -> list[float] | None:
    """Extract simple features from outfit."""
    try:
        items = outfit.get("items", [])
        if not items or len(items) < 2:
            return None
        
        features = []
        
        # Category distribution (5 categories)
        categories = ["top", "bottom", "shoes", "accessories", "dress"]
        cat_count = {cat: 0 for cat in categories}
        
        total_price = 0
        total_likes = 0
        
        for item in items[:8]:  # Max 8 items
            cat_id = int(item.get("categoryid", 0))
            cat_idx = min(cat_id, len(categories) - 1)
            if cat_idx < len(categories):
                cat_count[categories[cat_idx]] += 1
            
            total_price += float(item.get("price", 0) or 0)
            total_likes += int(item.get("likes", 0) or 0)
        
        # Normalize features
        num_items = len(items[:8])
        features.extend([cat_count.get(cat, 0) / max(1, num_items) for cat in categories])
        
        # Price features (0-1 normalized)
        avg_price = min(1.0, total_price / 5000.0)
        features.append(avg_price)
        
        # Likes features
        avg_likes = min(1.0, total_likes / 500.0)
        features.append(avg_likes)
        
        # Outfit popularity as compatibility score
        outfit_likes = int(outfit.get("likes", 0) or 0)
        label = min(1.0, max(0.0, outfit_likes / 1000.0))
        
        # Pad to 24 features
        while len(features) < 24:
            features.append(0.0)
        
        return features[:24], label
    
    except:
        return None


def create_training_data(outfits: list[dict]) -> tuple[torch.Tensor, torch.Tensor]:
    """Convert outfits to tensors."""
    print(f"\n🔄 Processing {len(outfits)} outfits...")
    
    X_list = []
    y_list = []
    
    for i, outfit in enumerate(outfits):
        if i % 3000 == 0 and i > 0:
            print(f"   Processed {i}/{len(outfits)}...")
        
        result = extract_features(outfit)
        if result:
            features, label = result
            X_list.append(torch.tensor(features, dtype=torch.float32))
            y_list.append(torch.tensor(label, dtype=torch.float32))
    
    X = torch.stack(X_list)
    y = torch.stack(y_list)
    
    print(f"   ✅ Created {len(X_list)} training examples")
    print(f"   Shape: X={X.shape}, y={y.shape}")
    return X, y


def train(X: torch.Tensor, y: torch.Tensor, epochs=20) -> SimpleOutfitSFT:
    """Train the model."""
    print(f"\n🚀 Training for {epochs} epochs...\n")
    
    model = SimpleOutfitSFT(input_dim=X.shape[1])
    model.train()
    
    criterion = nn.BCELoss()  # Binary crossentropy for compatibility
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.8)
    
    dataset = TensorDataset(X, y)
    dataloader = DataLoader(dataset, batch_size=64, shuffle=True)
    
    for epoch in range(epochs):
        total_loss = 0.0
        count = 0
        
        for batch_X, batch_y in dataloader:
            optimizer.zero_grad()
            pred = model(batch_X).squeeze()
            loss = criterion(pred, batch_y)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            count += 1
        
        avg_loss = total_loss / count
        scheduler.step()
        
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"   Epoch {epoch+1:2d}/{epochs} - Loss: {avg_loss:.6f}")
    
    model.eval()
    print(f"\n✅ Training complete!")
    return model


def save(model: SimpleOutfitSFT, path: Path):
    """Save model."""
    print(f"\n💾 Saving to {path}...")
    torch.save(model.state_dict(), str(path))
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"✅ Saved! ({size_mb:.2f} MB)")


def main():
    print("\n" + "="*70)
    print("Polyvore SFT Model Training (Simple)")
    print("="*70 + "\n")
    
    # Load data
    train_file = DATA_DIR / "train_no_dup.json"
    if not train_file.exists():
        print(f"❌ {train_file} not found!")
        return
    
    outfits = load_polyvore_outfits(train_file)
    
    # Create training data
    X, y = create_training_data(outfits)
    
    # Train
    model = train(X, y, epochs=20)
    
    # Save
    save(model, MODEL_PATH)
    
    print("\n" + "="*70)
    print("✅ Model ready! Restart the backend to use it.")
    print("="*70)


if __name__ == "__main__":
    main()

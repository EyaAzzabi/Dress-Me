"""Train SFT Model using Real Data from Supabase Database

Extracts real outfit combinations from the database and uses them
to train the SFT model. Uses feedback (like/dislike/worn) as labels.
"""

import sys
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ClothingItem, Outfit, OutfitFeedback
from app.ml.outfit_composition_sft_model import OutfitCompositionSFTModel

settings = get_settings()
ARTIFACTS_DIR = Path(__file__).resolve().parent / "app" / "ml" / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "outfit_composition_sft.pt"
ARTIFACTS_DIR.mkdir(exist_ok=True)


def get_db_session():
    """Create database session."""
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"} if "psycopg2" in settings.database_url else {},
    )
    return Session(engine)


def extract_training_data(db: Session) -> tuple[list[dict], int]:
    """Extract outfits and feedback from database."""
    print("📊 Extracting data from Supabase...")
    
    try:
        # Get all outfits
        outfits_query = select(Outfit)
        outfits = db.execute(outfits_query).scalars().all()
        print(f"  Found {len(outfits)} outfits in database")
        
        training_data = []
        feedback_count = 0
        
        for outfit in outfits:
            try:
                # Get items in outfit
                items = []
                for item_id in outfit.item_ids or []:
                    item_query = select(ClothingItem).where(ClothingItem.id == item_id)
                    item = db.execute(item_query).scalar_one_or_none()
                    if item:
                        items.append({
                            "id": str(item.id),
                            "category": item.category or "unknown",
                            "colors": item.colors or [],
                            "style": item.style or "unknown",
                            "season": item.season or "unknown",
                            "pattern": item.pattern or "unknown",
                        })
                
                if not items:
                    continue
                
                # Assign label based on feedback
                label = 0.5  # Default neutral
                if outfit.feedback:
                    if outfit.feedback == "like":
                        label = 1.0  # Good outfit
                        feedback_count += 1
                    elif outfit.feedback == "dislike":
                        label = 0.0  # Bad outfit
                        feedback_count += 1
                    elif outfit.feedback == "worn":
                        label = 0.9  # Very good (user wore it)
                        feedback_count += 1
                elif outfit.relevance_score:
                    # Use relevance score if available
                    label = min(1.0, max(0.0, float(outfit.relevance_score)))
                
                training_data.append({
                    "id": str(outfit.id),
                    "items": items,
                    "occasion": outfit.occasion or "casual",
                    "label": label,
                    "feedback": outfit.feedback,
                })
            
            except Exception as e:
                print(f"  ⚠️  Error processing outfit {outfit.id}: {e}")
                continue
        
        print(f"  ✅ Extracted {len(training_data)} valid outfits with {feedback_count} feedback")
        return training_data, feedback_count
    
    except Exception as e:
        print(f"❌ Database extraction error: {e}")
        return [], 0


def create_embeddings(outfits: list[dict]) -> tuple[torch.Tensor, torch.Tensor]:
    """Convert outfits to embeddings for training."""
    print(f"\n🔄 Creating embeddings for {len(outfits)} outfits...")
    
    embeddings = []
    labels = []
    
    # Feature dictionaries for hashing
    category_map = {"top": 0, "bottom": 1, "shoes": 2, "accessories": 3, "dress": 1, "unknown": 4}
    color_map = {color: i for i, color in enumerate([
        "red", "blue", "black", "white", "beige", "brown", "navy", "pink", "grey", "green",
        "purple", "yellow", "orange", "gold", "silver", "multicolor"
    ])}
    style_map = {style: i for i, style in enumerate([
        "casual", "formal", "sporty", "vintage", "modern", "bohemian", "classic", "minimalist"
    ])}
    
    for outfit in outfits:
        try:
            embedding_list = []
            
            # Add outfit context
            occasion = outfit.get("occasion", "casual")
            occasion_idx = hash(occasion) % 20 / 20
            embedding_list.append(occasion_idx)
            
            # Add features for each item (up to 5 items)
            for item in outfit["items"][:5]:
                # Category encoding
                category = item.get("category", "unknown").lower()
                cat_idx = category_map.get(category, 4) / 5.0
                embedding_list.append(cat_idx)
                
                # Color encoding (take first color if multiple)
                colors = item.get("colors", [])
                if colors:
                    color = str(colors[0]).lower()
                    col_idx = color_map.get(color, 0) / 16.0
                else:
                    col_idx = 0.0
                embedding_list.append(col_idx)
                
                # Style encoding
                style = item.get("style", "unknown").lower()
                style_idx = style_map.get(style, 0) / 8.0
                embedding_list.append(style_idx)
            
            # Pad to 21 features (1 context + 5 items × 4 features)
            while len(embedding_list) < 21:
                embedding_list.append(0.0)
            
            embedding = torch.tensor(embedding_list[:21], dtype=torch.float32)
            embeddings.append(embedding)
            
            # Label
            label = outfit.get("label", 0.5)
            labels.append(torch.tensor(label, dtype=torch.float32))
        
        except Exception as e:
            print(f"  ⚠️  Error creating embedding: {e}")
            continue
    
    if not embeddings:
        print("  ❌ No embeddings created!")
        return None, None
    
    X = torch.stack(embeddings)
    y = torch.stack(labels)
    
    print(f"  ✅ Created {len(embeddings)} embeddings: X={X.shape}, y={y.shape}")
    return X, y


def train_model(X: torch.Tensor, y: torch.Tensor, epochs: int = 20) -> OutfitCompositionSFTModel:
    """Train SFT model on real data."""
    print(f"\n🚀 Training SFT model on {len(X)} real outfits for {epochs} epochs...")
    
    model = OutfitCompositionSFTModel()
    model.train()
    
    # Loss function and optimizer
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)
    
    # Data loader
    dataset = TensorDataset(X, y)
    dataloader = DataLoader(dataset, batch_size=16, shuffle=True)
    
    # Training loop
    for epoch in range(epochs):
        total_loss = 0.0
        batch_count = 0
        
        for batch_X, batch_y in dataloader:
            optimizer.zero_grad()
            
            # Forward pass
            predictions = model.predict(batch_X)
            
            # Handle predictions shape
            if predictions.dim() > 1:
                predictions = predictions.squeeze()
            
            # Compute loss
            loss = criterion(predictions, batch_y)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            batch_count += 1
        
        avg_loss = total_loss / batch_count if batch_count > 0 else 0
        scheduler.step()
        
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  Epoch {epoch + 1:2d}/{epochs} - Loss: {avg_loss:.6f} - LR: {scheduler.get_last_lr()[0]:.6f}")
    
    model.eval()
    print(f"✅ Training complete!")
    return model


def save_model(model: OutfitCompositionSFTModel, path: Path) -> bool:
    """Save trained model to disk."""
    print(f"\n💾 Saving model to {path}...")
    try:
        torch.save(model.state_dict(), str(path))
        file_size = path.stat().st_size / 1024 / 1024
        print(f"✅ Model saved successfully! (Size: {file_size:.2f} MB)")
        return True
    except Exception as e:
        print(f"❌ Error saving model: {e}")
        return False


def main():
    """Main training pipeline."""
    print("\n" + "=" * 70)
    print("DressMe SFT Model Training — Using Real Database Data")
    print("=" * 70)
    
    # 1. Connect to database
    print("\n🔗 Connecting to Supabase...")
    db = get_db_session()
    
    # 2. Extract training data
    training_data, feedback_count = extract_training_data(db)
    db.close()
    
    if not training_data:
        print("\n❌ No training data found in database!")
        print("   Please add some outfits and feedback first.")
        return
    
    print(f"\n📈 Dataset Summary:")
    print(f"   Total outfits: {len(training_data)}")
    print(f"   With feedback: {feedback_count}")
    
    # Count labels
    good = sum(1 for o in training_data if o["label"] >= 0.9)
    bad = sum(1 for o in training_data if o["label"] <= 0.1)
    neutral = sum(1 for o in training_data if 0.1 < o["label"] < 0.9)
    print(f"   Good outfits (worn): {good}")
    print(f"   Bad outfits: {bad}")
    print(f"   Neutral: {neutral}")
    
    # 3. Create embeddings
    X, y = create_embeddings(training_data)
    
    if X is None:
        print("\n❌ Failed to create embeddings!")
        return
    
    # 4. Train model
    trained_model = train_model(X, y, epochs=20)
    
    # 5. Save model
    success = save_model(trained_model, MODEL_PATH)
    
    if success:
        print("\n" + "=" * 70)
        print("🎉 SFT Model Training Complete!")
        print("=" * 70)
        print(f"\n📁 Model saved at: {MODEL_PATH}")
        print(f"📊 Trained on {len(training_data)} real outfits from your database")
        print(f"\n✅ The model will now generate better recommendations!")
        print(f"   Restart the backend to load the trained model:")
        print(f"   → Backend will automatically load {MODEL_PATH}")
        print(f"   → SFT scores will be more accurate")
        print(f"   → Outfit combinations will be better matched")
    else:
        print("\n⚠️  Model was not saved properly.")


if __name__ == "__main__":
    main()

"""OutfitCompositionSFTModel — Supervised Fine-Tuning model for outfit composition.

Learns to compose outfits by imitating good combinations from training data.
Uses Transformer Encoder to understand which items work well together.

Training data: Polyvore outfits + Tunisian wardrobe compositions (labeled good/bad)
Loss: CrossEntropyLoss (multi-class item selection)
Per-user: artifacts/outfit_composition_sft_{user_id[:8]}.pt
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

# Optional torch import
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader

    _TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    _TORCH_AVAILABLE = False


# Model definition
if _TORCH_AVAILABLE:

    class OutfitCompositionSFTModel(nn.Module):
        """Transformer-based model for outfit composition (SFT).
        
        Learns which items combine well based on:
        - Item embeddings (FashionCLIP 512-d)
        - Context (season, weather, occasion)
        - Historical good/bad outfit examples
        """

        def __init__(
            self,
            embedding_dim: int = 512,
            hidden_dim: int = 256,
            num_layers: int = 2,
            num_heads: int = 4,
            max_items: int = 10,
            dropout: float = 0.1,
        ) -> None:
            super().__init__()
            self._trained = False
            self.embedding_dim = embedding_dim
            self.max_items = max_items

            # Context encoder: season, weather, occasion, formality → 128-d vector
            self.context_encoder = nn.Sequential(
                nn.Linear(4, 64),
                nn.ReLU(),
                nn.Linear(64, 128),
            )

            # Positional embedding for items
            self.pos_embedding = nn.Embedding(max_items, embedding_dim)

            # Transformer encoder to learn item relationships
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=embedding_dim,
                nhead=num_heads,
                dim_feedforward=hidden_dim,
                dropout=dropout,
                batch_first=True,
            )
            self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

            # Output head: item-wise scoring (which items to include in outfit?)
            self.item_classifier = nn.Sequential(
                nn.Linear(embedding_dim + 128, 256),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(256, 1),
                nn.Sigmoid(),  # Probability for each item
            )

        def forward(
            self,
            item_embeddings: "torch.Tensor",
            context_vector: "torch.Tensor",
            item_mask: "torch.Tensor | None" = None,
        ) -> "torch.Tensor":
            """
            Parameters
            ----------
            item_embeddings : (batch, num_items, 512)
            context_vector : (batch, 128)
            item_mask : (batch, num_items) optional mask for padding
            
            Returns
            -------
            scores : (batch, num_items) - probability each item should be in outfit
            """
            batch_size, num_items, _ = item_embeddings.shape

            # Add positional embeddings
            positions = torch.arange(num_items, device=item_embeddings.device).unsqueeze(0)
            pos_emb = self.pos_embedding(positions)  # (1, num_items, 512)
            x = item_embeddings + pos_emb  # (batch, num_items, 512)

            # Transformer encoding
            if item_mask is not None:
                x = self.transformer(x, src_key_padding_mask=~item_mask.bool())
            else:
                x = self.transformer(x)  # (batch, num_items, 512)

            # Context expansion
            context_expanded = context_vector.unsqueeze(1).expand(batch_size, num_items, -1)

            # Combine item encoding + context
            combined = torch.cat([x, context_expanded], dim=-1)  # (batch, num_items, 640)

            # Item scores
            scores = self.item_classifier(combined)  # (batch, num_items, 1)
            return scores.squeeze(-1)  # (batch, num_items)

else:  # pragma: no cover

    class OutfitCompositionSFTModel:  # type: ignore[no-redef]
        """Stub when torch is unavailable."""

        def __init__(self, **_):
            self._trained = False


# Public API
def load_or_init(user_id: str | None = None) -> OutfitCompositionSFTModel:
    """Load or create outfit composition SFT model.
    
    Parameters
    ----------
    user_id : str, optional for per-user models
    
    Returns
    -------
    OutfitCompositionSFTModel with _trained flag
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return OutfitCompositionSFTModel()

    if user_id:
        artifact_path = (
            Path(__file__).resolve().parent
            / "artifacts"
            / f"outfit_composition_sft_{user_id[:8]}.pt"
        )
        model = OutfitCompositionSFTModel()
        if artifact_path.exists():
            try:
                state = torch.load(str(artifact_path), map_location="cpu", weights_only=True)
                model.load_state_dict(state)
                model._trained = True
            except Exception:
                pass
        model.eval()
        return model

    return OutfitCompositionSFTModel()


def save(model: OutfitCompositionSFTModel, user_id: str) -> None:
    """Save outfit composition SFT model."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return
    artifact_path = (
        Path(__file__).resolve().parent / "artifacts" / f"outfit_composition_sft_{user_id[:8]}.pt"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), str(artifact_path))


def encode_context(
    season: str | None, weather: str | None, occasion: str | None, formality: int | None
) -> "torch.Tensor":
    """Encode categorical context to numerical vector (4,)."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return torch.zeros(4)

    season_map = {"ete": 0.75, "hiver": 0.0, "mi_saison": 0.5, "toutes_saisons": 0.5}
    weather_map = {"sunny": 0.75, "rainy": 0.25, "windy": 0.5, "cold": 0.0, "hot": 1.0}
    occasion_map = {"casual": 0.33, "travail": 0.66, "ceremonie": 1.0}

    season_val = torch.tensor([season_map.get(season or "toutes_saisons", 0.5)])
    weather_val = torch.tensor([weather_map.get(weather or "sunny", 0.5)])
    occasion_val = torch.tensor([occasion_map.get(occasion or "casual", 0.33)])
    formality_val = torch.tensor([(formality or 2) / 5.0])

    return torch.cat([season_val, weather_val, occasion_val, formality_val])


def predict(
    model: OutfitCompositionSFTModel,
    item_embeddings: list[np.ndarray],
    item_ids: list[str],
    season: str | None = None,
    weather: str | None = None,
    occasion: str | None = None,
    formality: int | None = None,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Predict which items should be in the outfit using SFT model.
    
    Parameters
    ----------
    model : OutfitCompositionSFTModel
    item_embeddings : list of (512,) FashionCLIP embeddings
    item_ids : list of item IDs
    season, weather, occasion, formality : context
    threshold : minimum score to include item
    
    Returns
    -------
    dict with "item_ids", "scores", "explanation"
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return {"item_ids": [], "scores": [], "explanation": "Torch unavailable"}

    if not item_embeddings or not item_ids:
        return {"item_ids": [], "scores": [], "explanation": "No items"}

    # Stack embeddings
    embeddings = torch.tensor(np.stack(item_embeddings), dtype=torch.float32).unsqueeze(0)

    # Encode context
    context = encode_context(season, weather, occasion, formality).unsqueeze(0)
    context_encoded = model.context_encoder(context)

    # Get scores
    with torch.no_grad():
        scores = model(embeddings, context_encoded)  # (1, num_items)

    scores_np = scores[0].detach().numpy()

    # Select items above threshold
    selected_mask = scores_np >= threshold
    selected_ids = [item_ids[i] for i in range(len(item_ids)) if selected_mask[i]]
    selected_scores = [float(scores_np[i]) for i in range(len(item_ids)) if selected_mask[i]]

    explanation = f"Composition SFT pour {occasion or 'casual'}, {season or 'saison'}."

    return {
        "item_ids": selected_ids,
        "scores": selected_scores,
        "explanation": explanation,
    }


def train(
    model: OutfitCompositionSFTModel,
    train_dataloader,
    val_dataloader=None,
    epochs: int = 10,
    lr: float = 1e-4,
    device: str = "cpu",
) -> dict[str, list[float]]:
    """Train SFT model on outfit composition task.
    
    Parameters
    ----------
    model : OutfitCompositionSFTModel
    train_dataloader : torch DataLoader
    val_dataloader : optional validation loader
    epochs : int
    lr : learning rate
    device : "cpu" or "cuda"
    
    Returns
    -------
    dict with "train_loss", "val_loss" history
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return {}

    model.to(device)
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.BCELoss()

    history = {"train_loss": [], "val_loss": []}

    for epoch in range(epochs):
        # Training
        train_loss = 0.0
        for batch_embeddings, batch_context, batch_labels in train_dataloader:
            batch_embeddings = batch_embeddings.to(device)
            batch_context = batch_context.to(device)
            batch_labels = batch_labels.to(device)

            optimizer.zero_grad()
            logits = model(batch_embeddings, batch_context)
            loss = criterion(logits, batch_labels)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()

        train_loss /= len(train_dataloader)
        history["train_loss"].append(train_loss)

        # Validation
        if val_dataloader:
            val_loss = 0.0
            model.eval()
            with torch.no_grad():
                for batch_embeddings, batch_context, batch_labels in val_dataloader:
                    batch_embeddings = batch_embeddings.to(device)
                    batch_context = batch_context.to(device)
                    batch_labels = batch_labels.to(device)

                    logits = model(batch_embeddings, batch_context)
                    loss = criterion(logits, batch_labels)
                    val_loss += loss.item()

            val_loss /= len(val_dataloader)
            history["val_loss"].append(val_loss)
            model.train()

        if (epoch + 1) % 2 == 0:
            print(f"Epoch {epoch + 1}/{epochs} - train_loss: {train_loss:.4f}")
            if val_dataloader:
                print(f"  val_loss: {val_loss:.4f}")

    model._trained = True
    model.eval()
    return history

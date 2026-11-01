"""OutfitCompatibilityTransformer — Deep Learning module for outfit coherence scoring.

Receives FashionCLIP embeddings for each garment in an outfit and learns their
pairwise and group-level relationships via a Transformer Encoder.  Outputs a
compatibility score in [0, 1].

Training: BCELoss + Adam on positive/negative Polyvore-style pairs.
Inference: score_outfit(embeddings) → float.
Persistence: artifacts/outfit_transformer.pt, loaded once via load_or_init().
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "outfit_transformer.pt"

# ---------------------------------------------------------------------------
# Optional torch import — degrades gracefully if unavailable
# ---------------------------------------------------------------------------
try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    _TORCH_AVAILABLE = False

# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE:

    class OutfitCompatibilityTransformer(nn.Module):
        """Transformer Encoder that predicts outfit compatibility from a variable-length
        sequence of 512-d garment embeddings."""

        def __init__(self, d_model: int = 512, nhead: int = 4,
                     dim_feedforward: int = 1024, num_layers: int = 2,
                     max_items: int = 10, dropout: float = 0.1) -> None:
            super().__init__()
            self.d_model = d_model
            # Learnable positional embedding for up to max_items garments
            self.pos_embedding = nn.Embedding(max_items, d_model)

            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=dim_feedforward,
                dropout=dropout,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

            # MLP classification head
            self.head = nn.Sequential(
                nn.Linear(d_model, 256),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(256, 1),
                nn.Sigmoid(),
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            # x: (batch, seq_len, d_model)
            batch_size, seq_len, _ = x.shape
            positions = torch.arange(seq_len, device=x.device).unsqueeze(0).expand(batch_size, -1)
            x = x + self.pos_embedding(positions)
            encoded = self.encoder(x)        # (batch, seq_len, d_model)
            pooled = encoded.mean(dim=1)     # mean pooling → (batch, d_model)
            return self.head(pooled)         # (batch, 1)

else:  # pragma: no cover

    class OutfitCompatibilityTransformer:  # type: ignore[no-redef]
        """Stub when torch is unavailable."""

        def __init__(self, **_):
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_or_init() -> "OutfitCompatibilityTransformer":
    """Return a trained model from disk if the artifact exists, otherwise a fresh
    randomly-initialised model.  Always runs on CPU."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return OutfitCompatibilityTransformer()

    model = OutfitCompatibilityTransformer()
    if ARTIFACT_PATH.exists():
        try:
            state = torch.load(str(ARTIFACT_PATH), map_location="cpu", weights_only=True)
            model.load_state_dict(state)
        except Exception:
            pass  # Return fresh model if artifact is corrupt
    model.eval()
    return model


def save_model(model: "OutfitCompatibilityTransformer") -> None:
    """Persist the model's state dict to ARTIFACT_PATH."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), str(ARTIFACT_PATH))


def score_outfit(embeddings: "list[np.ndarray]") -> float:
    """Return a compatibility score in [0, 1] for an outfit given its garment embeddings.

    Parameters
    ----------
    embeddings : list of np.ndarray, each shape (512,)

    Returns
    -------
    float in [0, 1].  Falls back to 0.5 if torch is unavailable or on error.
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return 0.5
    try:
        model = load_or_init()
        n = len(embeddings)
        if n == 0:
            return 0.5
        # Stack embeddings → (1, N, 512)
        tensor = torch.tensor(
            np.stack(embeddings, axis=0), dtype=torch.float32
        ).unsqueeze(0)
        with torch.no_grad():
            score = model(tensor)  # (1, 1)
        return float(score.squeeze())
    except Exception:
        return 0.5


def train_on_polyvore_style_data(
    positive_pairs: "list[list[np.ndarray]]",
    negative_pairs: "list[list[np.ndarray]]",
    epochs: int = 10,
    batch_size: int = 32,
) -> "OutfitCompatibilityTransformer":
    """Train (or fine-tune) OutfitCompatibilityTransformer on labelled outfit pairs.

    Parameters
    ----------
    positive_pairs : list of outfits, each outfit is a list of np.ndarray (512,).
        These are labelled 1.0 (compatible).
    negative_pairs : list of outfits, each outfit is a list of np.ndarray (512,).
        These are labelled 0.0 (incompatible).

    Returns
    -------
    Trained OutfitCompatibilityTransformer (CPU).
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return OutfitCompatibilityTransformer()

    model = load_or_init()
    model.train()

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    criterion = nn.BCELoss()

    # Build dataset: list of (tensor (1, N, 512), label)
    samples: list[tuple["torch.Tensor", float]] = []
    for outfit in positive_pairs:
        if len(outfit) == 0:
            continue
        t = torch.tensor(np.stack(outfit, axis=0), dtype=torch.float32).unsqueeze(0)
        samples.append((t, 1.0))
    for outfit in negative_pairs:
        if len(outfit) == 0:
            continue
        t = torch.tensor(np.stack(outfit, axis=0), dtype=torch.float32).unsqueeze(0)
        samples.append((t, 0.0))

    if not samples:
        return model

    effective_bs = min(batch_size, len(samples))

    for _epoch in range(epochs):
        # Shuffle
        indices = torch.randperm(len(samples))
        for start in range(0, len(samples), effective_bs):
            batch_indices = indices[start: start + effective_bs]
            optimizer.zero_grad()
            loss_total = torch.tensor(0.0)
            for idx in batch_indices:
                x, label = samples[idx.item()]
                pred = model(x).squeeze()
                target = torch.tensor(label)
                loss_total = loss_total + criterion(pred, target)
            (loss_total / len(batch_indices)).backward()
            optimizer.step()

    model.eval()
    return model

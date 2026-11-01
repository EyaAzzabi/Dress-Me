"""PreferenceRewardModel — RLHF reward model that learns user outfit preferences.

Trained with Bradley-Terry pairwise loss on (preferred, rejected) outfit pairs
collected from user A/B feedback.  Outputs an unbounded scalar reward for any outfit.

Training: Adam lr=1e-4, 20 epochs, Bradley-Terry loss.
Inference: predict_reward(embeddings) → float (unbounded).
Persistence: artifacts/reward_model_{user_id[:8]}.pt per user.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

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

    class PreferenceRewardModel(nn.Module):
        """MLP reward model: receives a mean-pooled 512-d outfit embedding, outputs a
        raw (unbounded) scalar reward."""

        def __init__(self, input_dim: int = 512) -> None:
            super().__init__()
            self._trained: bool = False
            self.net = nn.Sequential(
                nn.Linear(input_dim, 256),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(256, 128),
                nn.ReLU(),
                nn.Linear(128, 1),
                # No final activation — raw reward score
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            return self.net(x)

else:  # pragma: no cover

    class PreferenceRewardModel:  # type: ignore[no-redef]
        """Stub when torch is unavailable."""

        def __init__(self, **_):
            self._trained = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _mean_pool_embeddings(embeddings: "list[np.ndarray]") -> "torch.Tensor":
    """Mean-pool a list of 512-d arrays into a single (512,) tensor."""
    stacked = np.stack(embeddings, axis=0)          # (N, 512)
    pooled = stacked.mean(axis=0)                   # (512,)
    return torch.tensor(pooled, dtype=torch.float32)


def load_or_init(user_id: str) -> "PreferenceRewardModel":
    """Load an existing per-user reward model from disk, or create a fresh one.

    Parameters
    ----------
    user_id : str  — used to construct the artifact filename (first 8 chars).

    Returns
    -------
    PreferenceRewardModel on CPU.  _trained is True iff loaded from disk.
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return PreferenceRewardModel()

    artifact_path = (
        Path(__file__).resolve().parent / "artifacts" / f"reward_model_{user_id[:8]}.pt"
    )
    model = PreferenceRewardModel()
    if artifact_path.exists():
        try:
            state = torch.load(str(artifact_path), map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            model._trained = True
        except Exception:
            pass  # Return fresh model if artifact is corrupt
    model.eval()
    return model


def save(model: "PreferenceRewardModel", user_id: str) -> None:
    """Persist the reward model's state dict for the given user."""
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return
    artifact_path = (
        Path(__file__).resolve().parent / "artifacts" / f"reward_model_{user_id[:8]}.pt"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), str(artifact_path))


def train_from_feedback(
    model: "PreferenceRewardModel",
    feedback_pairs: "list[tuple[list[np.ndarray], list[np.ndarray]]]",
    epochs: int = 20,
) -> None:
    """Train the reward model in-place using Bradley-Terry pairwise loss.

    Parameters
    ----------
    model : PreferenceRewardModel to train (modified in-place).
    feedback_pairs : list of (preferred_embeddings, rejected_embeddings).
        Each element is a list of np.ndarray shape (512,).
    epochs : int, default 20.

    Sets model._trained = True on successful completion.
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return
    if not feedback_pairs:
        return

    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)

    for _epoch in range(epochs):
        optimizer.zero_grad()
        total_loss = torch.tensor(0.0)
        for preferred_embs, rejected_embs in feedback_pairs:
            if not preferred_embs or not rejected_embs:
                continue
            pref_vec = _mean_pool_embeddings(preferred_embs).unsqueeze(0)   # (1, 512)
            rej_vec = _mean_pool_embeddings(rejected_embs).unsqueeze(0)     # (1, 512)

            r_pref = model(pref_vec).squeeze()     # scalar
            r_rej = model(rej_vec).squeeze()       # scalar

            # Bradley-Terry: L = -log(sigmoid(R_pref - R_rej))
            loss = -torch.log(torch.sigmoid(r_pref - r_rej) + 1e-8)
            total_loss = total_loss + loss

        if total_loss.item() != 0.0:
            total_loss.backward()
            optimizer.step()

    model._trained = True
    model.eval()


def predict_reward(
    model: "PreferenceRewardModel",
    embeddings: "list[np.ndarray]",
) -> float:
    """Return the raw (unbounded) reward scalar for an outfit.

    Parameters
    ----------
    model : PreferenceRewardModel.
    embeddings : list of np.ndarray shape (512,).

    Returns
    -------
    float.  Returns 0.0 if torch is unavailable or on error.
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        return 0.0
    try:
        if not embeddings:
            return 0.0
        pooled = _mean_pool_embeddings(embeddings).unsqueeze(0)  # (1, 512)
        with torch.no_grad():
            reward = model(pooled).squeeze()
        return float(reward)
    except Exception:
        return 0.0

"""rlhf_policy_model — PPO-clipped policy model for outfit scoring.

Implements proper PPO with clipping (FIX-2):
  ratio = exp(new_log_prob - old_log_prob)
  advantage = (reward - baseline) * weight
  loss = -min(ratio * advantage, clamp(ratio, 1-eps, 1+eps) * advantage)
  + entropy bonus: -entropy_coef * (p*log(p+1e-8) + (1-p)*log(1-p+1e-8))

Artifact path (FIX-3): artifacts/outfit_composition_rlhf_policy.pt (single global policy).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional torch import — degrades gracefully if unavailable (torch guard)
# ---------------------------------------------------------------------------
try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCH_AVAILABLE = False

# ---------------------------------------------------------------------------
# Artifact path (constant, FIX-3)
# ---------------------------------------------------------------------------
_ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "outfit_composition_rlhf_policy.pt"

# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE:

    class RLHFPolicyModel(nn.Module):
        """MLP policy model: 512 → 256 → 128 → 1, no final activation.

        Input : mean-pooled (512,) outfit embedding.
        Output: raw scalar logit (use sigmoid to get probability).
        """

        def __init__(self, input_dim: int = 512) -> None:
            super().__init__()
            self._trained: bool = False
            self.net = nn.Sequential(
                nn.Linear(input_dim, 256),
                nn.ReLU(),
                nn.Linear(256, 128),
                nn.ReLU(),
                nn.Linear(128, 1),
                # No final activation (FIX-2: use log_sigmoid in PPO)
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            return self.net(x)

else:  # pragma: no cover

    class RLHFPolicyModel:  # type: ignore[no-redef]
        """Stub when torch is unavailable."""

        def __init__(self, **_):
            self._trained = False

        def forward(self, x):  # noqa: ANN
            return 0.0


# ---------------------------------------------------------------------------
# PPO training (FIX-2)
# ---------------------------------------------------------------------------

def train_policy_ppo(
    policy_model: "RLHFPolicyModel",
    reward_model,
    pairs: "list[tuple[np.ndarray, np.ndarray, float]]",
    epochs: int = 3,
    lr: float = 1e-5,
    eps: float = 0.2,
    entropy_coef: float = 0.01,
) -> dict:
    """Train policy model with proper PPO + clipping (FIX-2).

    Parameters
    ----------
    policy_model : RLHFPolicyModel to train in-place.
    reward_model : PreferenceRewardModel (frozen, not updated).
    pairs : list of (emb_a, emb_b, weight) — emb_a is preferred, emb_b is rejected.
    epochs : PPO training epochs.
    lr : Adam learning rate.
    eps : PPO clip epsilon (0.2 by default).
    entropy_coef : coefficient for entropy bonus term.

    Returns
    -------
    dict with "epoch_losses", "epoch_accuracies", "total_epochs".
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        logger.warning("torch not available — skipping PPO training")
        return {"epoch_losses": [], "epoch_accuracies": [], "total_epochs": 0}

    if not pairs:
        logger.warning("train_policy_ppo: no pairs provided — skipping")
        return {"epoch_losses": [], "epoch_accuracies": [], "total_epochs": 0}

    policy_model.train()
    reward_model.eval()  # keep frozen

    optimizer = torch.optim.Adam(policy_model.parameters(), lr=lr)

    # ------------------------------------------------------------------
    # Step (a): collect old log-probs with no_grad (frozen reference)
    # ------------------------------------------------------------------
    old_log_probs_a: list[torch.Tensor] = []
    old_log_probs_b: list[torch.Tensor] = []

    with torch.no_grad():
        for emb_a, emb_b, _weight in pairs:
            t_a = torch.tensor(emb_a, dtype=torch.float32).unsqueeze(0)  # (1, 512)
            t_b = torch.tensor(emb_b, dtype=torch.float32).unsqueeze(0)

            old_lp_a = torch.nn.functional.logsigmoid(policy_model(t_a)).detach()
            old_lp_b = torch.nn.functional.logsigmoid(policy_model(t_b)).detach()
            old_log_probs_a.append(old_lp_a)
            old_log_probs_b.append(old_lp_b)

    epoch_losses: list[float] = []
    epoch_accuracies: list[float] = []

    for _epoch in range(epochs):
        epoch_loss = 0.0
        correct = 0

        for idx, (emb_a, emb_b, weight) in enumerate(pairs):
            t_a = torch.tensor(emb_a, dtype=torch.float32).unsqueeze(0)  # (1, 512)
            t_b = torch.tensor(emb_b, dtype=torch.float32).unsqueeze(0)
            w = torch.tensor(weight, dtype=torch.float32)

            # ----------------------------------------------------------
            # Step (b): reward signal from frozen reward model
            # ----------------------------------------------------------
            with torch.no_grad():
                reward_a = reward_model(t_a).squeeze().detach()
                reward_b = reward_model(t_b).squeeze().detach()

            baseline = (reward_a + reward_b) / 2.0
            advantage_a = (reward_a - baseline) * w        # preferred: positive
            advantage_b = -(reward_b - baseline) * w       # rejected: negative

            # ----------------------------------------------------------
            # Step (c): recompute new log-probs (requires grad)
            # ----------------------------------------------------------
            new_lp_a = torch.nn.functional.logsigmoid(policy_model(t_a))
            new_lp_b = torch.nn.functional.logsigmoid(policy_model(t_b))

            # ----------------------------------------------------------
            # Step (d): PPO ratios and clipped objectives (FIX-2)
            # ----------------------------------------------------------
            old_lp_a = old_log_probs_a[idx].detach()
            old_lp_b = old_log_probs_b[idx].detach()

            ratio_a = torch.exp(new_lp_a - old_lp_a)
            ratio_b = torch.exp(new_lp_b - old_lp_b)

            clip_a = torch.clamp(ratio_a, 1.0 - eps, 1.0 + eps)
            clip_b = torch.clamp(ratio_b, 1.0 - eps, 1.0 + eps)

            ppo_loss_a = -torch.min(ratio_a * advantage_a, clip_a * advantage_a)
            ppo_loss_b = -torch.min(ratio_b * advantage_b, clip_b * advantage_b)

            # ----------------------------------------------------------
            # Step (e): entropy bonus (encourages exploration)
            # FIX-2 formula: -(p*log(p+1e-8) + (1-p)*log(1-p+1e-8))
            # ----------------------------------------------------------
            p_a = torch.sigmoid(policy_model(t_a))
            entropy = -(
                p_a * torch.log(p_a + 1e-8)
                + (1.0 - p_a) * torch.log(1.0 - p_a + 1e-8)
            )

            # ----------------------------------------------------------
            # Step (f): combined loss
            # ----------------------------------------------------------
            loss = ppo_loss_a + ppo_loss_b - entropy_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()

            # Accuracy: policy prefers a over b if score_a > score_b
            with torch.no_grad():
                score_a = policy_model(t_a).item()
                score_b = policy_model(t_b).item()
            if score_a > score_b:
                correct += 1

        avg_loss = epoch_loss / len(pairs) if pairs else 0.0
        accuracy = correct / len(pairs) if pairs else 0.0
        epoch_losses.append(avg_loss)
        epoch_accuracies.append(accuracy)
        logger.info(
            f"PPO epoch {_epoch + 1}/{epochs} — loss={avg_loss:.4f} acc={accuracy:.3f}"
        )

    policy_model._trained = True
    policy_model.eval()

    return {
        "epoch_losses": epoch_losses,
        "epoch_accuracies": epoch_accuracies,
        "total_epochs": epochs,
    }


# ---------------------------------------------------------------------------
# Persistence (FIX-3: single global path regardless of user_id)
# ---------------------------------------------------------------------------

def load_policy_model(user_id: str) -> "RLHFPolicyModel | None":
    """Load policy model from artifact path, or return None if not found / load fails.

    Always loads from artifacts/outfit_composition_rlhf_policy.pt (FIX-3).
    Uses strict=False to tolerate minor architecture mismatches.

    Parameters
    ----------
    user_id : str — accepted for API symmetry but NOT used in path construction.

    Returns
    -------
    RLHFPolicyModel with _trained=True, or None on failure.
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        logger.warning("torch not available — cannot load policy model")
        return None

    if not _ARTIFACT_PATH.exists():
        logger.info(f"Policy model artifact not found at {_ARTIFACT_PATH}")
        return None

    try:
        model = RLHFPolicyModel()
        state = torch.load(str(_ARTIFACT_PATH), map_location="cpu", weights_only=True)
        model.load_state_dict(state, strict=False)
        model._trained = True
        model.eval()
        logger.info(f"Loaded RLHF policy model from {_ARTIFACT_PATH}")
        return model
    except Exception as exc:
        logger.error(f"Failed to load policy model from {_ARTIFACT_PATH}: {exc}")
        return None


def save_policy_model(model: "RLHFPolicyModel", user_id: str) -> None:
    """Save policy model to artifact path.

    Always saves to artifacts/outfit_composition_rlhf_policy.pt (FIX-3).
    user_id is accepted for API symmetry but NOT used in path construction.

    Parameters
    ----------
    model : RLHFPolicyModel to save.
    user_id : str — accepted but not used.
    """
    if not _TORCH_AVAILABLE:  # pragma: no cover
        logger.warning("torch not available — cannot save policy model")
        return

    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), str(_ARTIFACT_PATH))
    logger.info(f"Saved RLHF policy model to {_ARTIFACT_PATH}")

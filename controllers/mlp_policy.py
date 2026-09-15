from __future__ import annotations

import numpy as np


class MLPPolicy:
    """Small NumPy MLP placeholder for future PPO baselines."""

    def __init__(self, obs_dim: int = 11, hidden_dim: int = 32, seed: int | None = None) -> None:
        rng = np.random.default_rng(seed)
        self.w1 = rng.normal(scale=0.1, size=(obs_dim, hidden_dim))
        self.b1 = np.zeros(hidden_dim)
        self.w2 = rng.normal(scale=0.1, size=(hidden_dim, 1))
        self.b2 = np.zeros(1)

    def act(self, obs: np.ndarray) -> np.ndarray:
        hidden = np.tanh(np.asarray(obs) @ self.w1 + self.b1)
        action = np.tanh(hidden @ self.w2 + self.b2)
        return action.astype(np.float32)

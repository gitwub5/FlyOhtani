from __future__ import annotations

import numpy as np


class BallStateEncoder:
    """Rate encoder for compact ball state observations."""

    def __init__(self, max_rate_hz: float = 200.0, dt: float = 0.002, seed: int | None = None) -> None:
        self.max_rate_hz = max_rate_hz
        self.dt = dt
        self.rng = np.random.default_rng(seed)

    def encode(self, obs: np.ndarray) -> np.ndarray:
        ball_state = np.asarray(obs[:6], dtype=float)
        normalized = 1.0 / (1.0 + np.exp(-ball_state))
        spike_prob = np.clip(normalized * self.max_rate_hz * self.dt, 0.0, 1.0)
        return (self.rng.random(spike_prob.shape) < spike_prob).astype(np.float32)

from __future__ import annotations

import numpy as np


class SNNPolicy:
    """Minimal leaky integrate-and-fire policy interface.

    This intentionally starts small: encoded spikes drive a population of hidden
    neurons, and the output action is based on the final membrane voltage.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 32,
        dt: float = 0.002,
        tau_mem: float = 0.02,
        threshold: float = 1.0,
        seed: int | None = None,
    ) -> None:
        rng = np.random.default_rng(seed)
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.dt = dt
        self.tau_mem = tau_mem
        self.threshold = threshold
        self.w_in = rng.normal(scale=0.2, size=(input_dim, hidden_dim))
        self.w_out = rng.normal(scale=0.2, size=(hidden_dim, 1))
        self.v = np.zeros(hidden_dim)
        self.last_spikes = np.zeros(hidden_dim)

    def reset(self) -> None:
        self.v.fill(0.0)
        self.last_spikes.fill(0.0)

    def act(self, spikes: np.ndarray) -> np.ndarray:
        current = np.asarray(spikes, dtype=float) @ self.w_in
        decay = np.exp(-self.dt / self.tau_mem)
        self.v = decay * self.v + current
        self.last_spikes = (self.v >= self.threshold).astype(float)
        self.v[self.last_spikes > 0] = 0.0
        action = np.tanh(self.last_spikes @ self.w_out)
        return action.astype(np.float32)

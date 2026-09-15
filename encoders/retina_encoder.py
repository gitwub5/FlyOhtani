from __future__ import annotations

import numpy as np


class RetinaEncoder:
    """Simple retina-like grid encoder from ball position to spikes."""

    def __init__(
        self,
        width: int = 12,
        height: int = 8,
        fov_x: tuple[float, float] = (-2.5, 0.7),
        fov_z: tuple[float, float] = (0.1, 1.2),
        sigma: float = 1.2,
        max_rate_hz: float = 250.0,
        dt: float = 0.002,
        seed: int | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fov_x = fov_x
        self.fov_z = fov_z
        self.sigma = sigma
        self.max_rate_hz = max_rate_hz
        self.dt = dt
        self.rng = np.random.default_rng(seed)
        xs, zs = np.meshgrid(np.arange(width), np.arange(height))
        self.grid = np.stack([xs, zs], axis=-1)

    @property
    def output_dim(self) -> int:
        return self.width * self.height

    def encode(self, obs: np.ndarray) -> np.ndarray:
        ball_x = float(obs[0])
        ball_z = float(obs[2])
        px = np.interp(ball_x, self.fov_x, (0, self.width - 1))
        pz = np.interp(ball_z, self.fov_z, (0, self.height - 1))
        dist2 = (self.grid[..., 0] - px) ** 2 + (self.grid[..., 1] - pz) ** 2
        rates = self.max_rate_hz * np.exp(-dist2 / (2.0 * self.sigma**2))
        spike_prob = np.clip(rates * self.dt, 0.0, 1.0)
        return (self.rng.random(spike_prob.shape) < spike_prob).astype(np.float32).ravel()

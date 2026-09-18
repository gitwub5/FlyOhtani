"""Eye image -> the drive that reaches LC4 and LPLC2.

PLAN Phase 3 asks for "ON/OFF contrast channels plus a temporal derivative".
That is what this is, and it is the smallest thing that can carry looming:
an approaching object darkens (or brightens) the pixels its edge sweeps
across, and the number of pixels changing per frame grows as it gets closer.

What is real here and what is ours:

  REAL      that LC4 and LPLC2 are looming-sensitive visual projection
            neurons, and that each pools over a patch of the visual field
  OURS      the encoding below (Weber contrast between consecutive frames,
            half-wave rectified into ON and OFF), the receptive-field
            layout, and every constant in this file

A fly's photoreceptors do not compute frame differences, and its LC cells do
not pool over square tiles. This is a stand-in chosen to be legible and
cheap, and it is labelled as one -- when it is replaced, the thing to check
is whether the replacement changes the answer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

EPS = 8.0
"""Added to the denominator of the contrast, in grey levels. Keeps a dark
patch from producing enormous contrast out of sensor-floor differences; at
this value a change of one level on a black background reads as ~12%."""


@dataclass(frozen=True)
class ReceptiveFields:
    """Which pixels each cell pools over.

    The tiling is OURS (see the module docstring): cells are laid out on as
    square a grid as their number allows, each with a Gaussian weighting so
    neighbouring fields overlap the way real ones do rather than tiling the
    image like a chessboard.
    """

    weights: np.ndarray
    """(n_cells, n_pixels), each row summing to 1."""
    centres: np.ndarray
    """(n_cells, 2) in pixel coordinates -- kept for plotting and tests."""
    resolution: int

    @property
    def n_cells(self) -> int:
        return self.weights.shape[0]

    def pool(self, image: np.ndarray) -> np.ndarray:
        return self.weights @ image.reshape(-1)


def build_receptive_fields(n_cells: int, resolution: int, sigma_px: float | None = None) -> ReceptiveFields:
    """`n_cells` Gaussian fields spread over a `resolution` square image."""
    if n_cells < 1:
        raise ValueError("a cell type with no cells has no receptive fields")
    side = math.ceil(math.sqrt(n_cells))
    step = resolution / side
    sigma = sigma_px if sigma_px is not None else step * 0.6
    ys, xs = np.mgrid[0:resolution, 0:resolution]
    centres = np.empty((n_cells, 2))
    weights = np.empty((n_cells, resolution * resolution))
    for i in range(n_cells):
        row, col = divmod(i, side)
        cy = (row + 0.5) * step
        cx = (col + 0.5) * step
        centres[i] = (cy, cx)
        g = np.exp(-(((ys - cy) ** 2 + (xs - cx) ** 2) / (2 * sigma ** 2)))
        weights[i] = (g / g.sum()).reshape(-1)
    return ReceptiveFields(weights=weights, centres=centres, resolution=resolution)


@dataclass
class Retina:
    """Holds the previous frame, so `encode` can take a difference."""

    resolution: int
    _previous: np.ndarray | None = None

    def reset(self) -> None:
        self._previous = None

    def encode(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns (ON, OFF) maps in [0, 1]: where the image got brighter and
        where it got darker since the last call. The first frame of an
        episode has nothing to compare against and yields zeros -- a fly
        arriving mid-pitch would also have no motion signal yet."""
        now = image.astype(np.float32)
        if self._previous is None or self._previous.shape != now.shape:
            self._previous = now
            return np.zeros_like(now), np.zeros_like(now)
        contrast = (now - self._previous) / (self._previous + EPS)
        self._previous = now
        return np.clip(contrast, 0, None), np.clip(-contrast, 0, None)

"""Classical (non-learned) single-frame ball detector. Operates ONLY on
pixel data -- an RGB frame array -- and the ball's known static RENDER
color (a material/appearance property, not a per-frame ground-truth
position read). No env/mujoco import here at all; this module cannot leak
simulator state even by accident because it has no access to it.

Method: per-pixel "redness" score (how close each pixel's RGB is to the
known ball color, in a scale-invariant hue-like sense so shading/lighting
intensity does not by itself defeat detection) thresholded, then the
weighted centroid and pixel count of every pixel that passes the
threshold. No scipy/skimage dependency; this project does not otherwise
depend on either.

TWO ASSUMPTIONS CARRIED OVER FROM THE v1 SCENE, both to be re-confirmed
against the Phase 2 world (docs/PLAN.md) before any detection numbers are
reported:
  1. BALL_COLOR_RGB below is the v1 ball material's rgba. The Phase 2
     ball's material must either match it or this constant must change.
  2. The centroid is correct only when at most ONE object of that color is
     in view. The v1 scene satisfied that; the new scene must be checked.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BALL_COLOR_RGB = np.array([0.95, 0.18, 0.18]) * 255.0
MIN_BLOB_PIXELS = 1  # a single-pixel (or sub-pixel-antialiased) detection still counts as "detected"
REDNESS_THRESHOLD = 0.35  # "excess red" score in [0, 1] (see _redness_score), pre-registered before any detection run


@dataclass(frozen=True)
class Detection:
    detected: bool
    centroid_xy_px: tuple[float, float] | None
    n_pixels: int
    uncertainty_px: float


def _redness_score(frame_rgb: np.ndarray) -> np.ndarray:
    """Per-pixel "excess red" score in [0, 1]: R minus the average of G and
    B, normalized to [0, 255] -> [0, 1]. A first version of this function
    used cosine similarity to the ball's RGB vector, which is fooled by
    white/gray objects (the scene's own foul line, rgba (0.95,0.95,0.95,1))
    -- cosine similarity between pure white and the ball's red is ~0.77
    (ABOVE the threshold that version used), because cosine similarity only
    measures direction, not saturation, and does not penalize a
    desaturated (gray/white) pixel for having "no particular color". This
    was caught empirically on v1's first render run, which showed 60-170px
    mean position error at wide FOV, traced to the foul line's large white
    blob dominating the weighted centroid, not the actual (sub-pixel) ball. "Excess red" correctly scores true white/gray
    pixels near 0 (R-G/B difference ~0) while still scoring the ball's own
    color highly (R=242 vs G=B=46 after scaling -> ~0.77)."""
    frame = frame_rgb.astype(np.float32)
    excess_red = frame[..., 0] - 0.5 * (frame[..., 1] + frame[..., 2])
    score = np.clip(excess_red / 255.0, 0.0, 1.0)
    bright_enough = frame[..., 0] > 20.0
    return np.where(bright_enough, score, 0.0)


class BallDetector:
    def __init__(self, threshold: float = REDNESS_THRESHOLD, min_blob_pixels: int = MIN_BLOB_PIXELS) -> None:
        self.threshold = threshold
        self.min_blob_pixels = min_blob_pixels

    def detect(self, frame_rgb: np.ndarray) -> Detection:
        if frame_rgb.ndim != 3 or frame_rgb.shape[-1] != 3:
            raise ValueError(f"expected an HxWx3 RGB frame, got shape {frame_rgb.shape}")
        score = _redness_score(frame_rgb)
        mask = score >= self.threshold
        n_pixels = int(mask.sum())
        if n_pixels < self.min_blob_pixels:
            return Detection(detected=False, centroid_xy_px=None, n_pixels=n_pixels, uncertainty_px=float("inf"))

        ys, xs = np.nonzero(mask)
        weights = score[ys, xs]
        cx = float(np.average(xs, weights=weights))
        cy = float(np.average(ys, weights=weights))

        # Heuristic uncertainty: a compact blob spanning `n_pixels` gives a
        # centroid precision roughly proportional to its own radius divided
        # by sqrt(n_pixels) (more pixels -> a better-averaged centroid); a
        # 1-pixel "blob" (the sub-pixel regime docs/records/PRIOR-FINDINGS.md
        # section 3 predicts dominates most of the flight) is reported with
        # a full-pixel uncertainty, not a false sub-pixel confidence. This
        # is a heuristic, not a calibrated noise model -- no sensor-noise
        # simulation is implemented this round.
        radius_px = float(np.sqrt(n_pixels / np.pi))
        uncertainty = max(0.5, radius_px / np.sqrt(n_pixels)) if n_pixels > 0 else float("inf")
        return Detection(detected=True, centroid_xy_px=(cx, cy), n_pixels=n_pixels, uncertainty_px=uncertainty)

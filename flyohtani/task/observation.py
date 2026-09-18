"""What the policy is allowed to see. Nothing else reaches it.

v1's `sense/observation.py` is a classical-CV contract: a detector finds a red
ball, a tracker holds a pixel-space estimate, and the observation carries that
estimate plus proprioception from a three-axis rig that no longer exists. The
current design does not have those parts -- the eye's image goes to a retina
and a circuit (PLAN Phase 3/4) -- so this is a new contract rather than an
edit of that one, and the old one stays where v1's tests still use it.

What carries over is the rule, not the fields: the observation is a frozen
dataclass with an explicit field list, so adding a channel that reads
simulator state takes a visible edit here. `_FORBIDDEN_FIELD_NAMES` is
imported from the v1 module so there is one list, not two.

Two things a policy might reasonably expect are deliberately absent:

  the ball's position       ground truth; the eye image is the only source
  the time since release    every episode starts at release, so a clock
                            would let a policy swing on a stopwatch without
                            ever looking. A fly has no such clock either.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flyohtani.sense.observation import _FORBIDDEN_FIELD_NAMES

SCHEMA_VERSION = "1.0"

FORBIDDEN_FIELD_NAMES = _FORBIDDEN_FIELD_NAMES | frozenset({
    "time_s", "elapsed_s", "frame_index", "time_to_contact_s", "release_time_s",
    "pitch_speed", "ball_distance_mm", "swing_window",
})
"""v1's list plus everything that would hand over the pitch's clock."""


@dataclass(frozen=True)
class BatObservation:
    """One eye frame and the arm's own state, and that is all.

    `eye_left` is the acute zone aimed down the pitch (D31b/D32); `eye_right`
    is the wide field. Both are what `world.batter.render_eyes` produces --
    32x32 grayscale, each pixel integrating over its own solid angle -- so
    what a policy sees is what the recordings show.

    Joint angles and velocities are the five foreleg joints the fly actually
    drives. Proprioception is not a simulator cheat: an insect has joint
    sense. Ball state is not proprioception, and is not here.
    """

    eye_left: np.ndarray
    eye_right: np.ndarray
    joint_angle_rad: np.ndarray
    joint_vel_rad_s: np.ndarray
    swing_started: bool
    """Whether this episode's swing has already been triggered. The fly knows
    what its own arm is doing; this is the same channel as proprioception."""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("eye_left", "eye_right"):
            img = getattr(self, name)
            if img.ndim != 2 or img.shape[0] != img.shape[1]:
                raise ValueError(f"{name} must be a square image, got {img.shape}")
        if self.joint_angle_rad.shape != self.joint_vel_rad_s.shape:
            raise ValueError("one velocity per joint angle")

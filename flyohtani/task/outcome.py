"""What actually happened in an episode -- ground truth, for the caller.

Its own module so that `rewards.py` can read it without importing the
environment, and so that the asymmetry is visible in the import graph: a
policy gets `observation.BatObservation`, a scorer gets this.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Outcome:
    """Goes to the CALLER, never into an observation: scoring and
    learning-signal code may read it, a policy may not."""

    swung: bool = False
    contact: bool = False
    swing_frame: int | None = None
    swing_zone: str | None = None
    pitch_zone: str = "middle"
    exit_speed_mm_s: float | None = None
    launch_angle_deg: float | None = None
    spray_angle_deg: float | None = None
    carry_mm: float | None = None
    fair: bool | None = None
    peak_joint_speed_rad_s: float = 0.0
    frames_seen: int = 0

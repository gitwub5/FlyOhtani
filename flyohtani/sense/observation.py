"""VisionObservation, the ONLY object the policy-facing code path is
allowed to see (the leak contract, docs/records/PRIOR-FINDINGS.md section
6). This is a frozen dataclass with a fixed, explicit field list -- there
is no `**kwargs`, no dict passthrough, and no field named after
ground-truth physics state (ball_pos, ball_vel, remaining, course, phase,
...). Adding a forbidden channel would require editing this class's field
list by hand, which is the point: a reviewer (or a test, see
tests/test_sense_detection.py) can check this file alone and see the
entire contract.

Proprioception is allowed -- a real insect has joint sense, so it is not a
simulator cheat. The SPECIFIC proprioception fields below
(torso/swing/tilt) are v1's 3-axis rig and are now DEAD NAMES: Phase 3
(docs/PLAN.md) replaces them with the NeuroMechFly foreleg joints. They
are left in place rather than invented anew, so that the schema change is
a deliberate, reviewable edit when the new rig actually exists.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SCHEMA_VERSION = "0.1"

_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "ball_pos",
        "ball_position",
        "ball_vel",
        "ball_velocity",
        "remaining",
        "predicted_time_to_target",
        "course",
        "target",
        "phase",
        "end_reason",
        "scoring_valid",
        "crossing_time",
        "alignment",
    }
)


@dataclass(frozen=True)
class VisionObservation:
    """`detected` is a per-frame, transient flag: did THIS frame's classical
    detector (ball_detector.py) find the ball -- used for detection-rate /
    precision-recall metrics, nothing else. It is intentionally decoupled
    from whether position_xy_px/velocity_xy_px_s carry a value: on an
    occlusion or a miss, the last valid estimate is passed on with a larger
    uncertainty and a growing age, so a miss on THIS frame does not null
    out the estimate -- tracker.py holds it, and whether to trust a stale
    estimate is the policy's decision, not something forced here by
    null-ing the field. Before the FIRST ever successful detection (cold
    start), position/velocity are genuinely None -- there is nothing to
    hold yet, and this is NOT a ground-truth fallback of any kind (there is
    no simulator-state read anywhere in this class or in
    flyohtani/sense/tracker.py)."""

    capture_timestamp_s: float
    detected: bool
    position_xy_px: tuple[float, float] | None
    velocity_xy_px_s: tuple[float, float] | None
    uncertainty_px: float
    age_s: float
    torso_angle_rad: float
    torso_vel_rad_s: float
    swing_angle_rad: float
    swing_vel_rad_s: float
    tilt_angle_rad: float
    tilt_vel_rad_s: float
    bat_contact: bool
    contact_force_n: float | None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        field_names = {f for f in self.__dataclass_fields__}
        leaked = field_names & _FORBIDDEN_FIELD_NAMES
        if leaked:
            raise AssertionError(f"VisionObservation must never carry forbidden fields: {leaked}")
        if self.age_s < 0:
            raise ValueError(f"age_s must be >= 0, got {self.age_s}")
        if self.position_xy_px is not None and not np.isfinite(self.uncertainty_px):
            raise ValueError("a reported position must carry a finite uncertainty")
        if self.position_xy_px is None and self.velocity_xy_px_s is not None:
            raise ValueError("velocity without a position makes no sense")

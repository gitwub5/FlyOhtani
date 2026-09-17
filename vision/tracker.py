"""VM-01 V1: frame-to-frame ball tracking, producing the policy-facing
VisionObservation stream. No simulator-state import -- this module only
ever sees vision/ball_detector.py's Detection objects (pixel-space) and
proprioception/contact values the CALLER already read from the env's
allowed channels (docs/design/VISION-01.md section 4's own allow-list);
it never reads ball_pos/ball_vel/remaining itself.

Implements VISION-01 section 5's clock/age/latency contract:
- the tracker is updated at the VIDEO clock's own rate (fps), not every
  control tick -- callers on a faster control loop must reuse the same
  VisionObservation (with an increasing age_s) between video frames rather
  than calling `update` more often than a new frame actually arrives.
- an explicit LATENCY (in whole video frames) between capture and
  availability is modeled: `update()` takes the detection made from a
  frame captured at `capture_timestamp_s`, but the RETURNED observation's
  age is computed against `now`, which the caller advances independently
  -- callers that want to model latency simply call `update` with a
  `now` that is later than `capture_timestamp_s`.
"""
from __future__ import annotations

from dataclasses import dataclass

from vision.ball_detector import Detection
from vision.observation import VisionObservation


@dataclass
class Proprioception:
    torso_angle_rad: float
    torso_vel_rad_s: float
    swing_angle_rad: float
    swing_vel_rad_s: float
    tilt_angle_rad: float
    tilt_vel_rad_s: float
    bat_contact: bool
    contact_force_n: float | None


class BallTracker:
    def __init__(self) -> None:
        self._last_valid_pos: tuple[float, float] | None = None
        self._last_valid_t: float | None = None
        self._last_valid_uncertainty: float = float("inf")
        self._velocity: tuple[float, float] | None = None
        self._n_detections = 0
        self._n_frames = 0

    @property
    def detection_rate(self) -> float:
        return self._n_detections / self._n_frames if self._n_frames else float("nan")

    def update(
        self,
        detection: Detection,
        capture_timestamp_s: float,
        now_s: float,
        proprio: Proprioception,
    ) -> VisionObservation:
        self._n_frames += 1
        if detection.detected:
            self._n_detections += 1
            assert detection.centroid_xy_px is not None
            if self._last_valid_pos is not None and self._last_valid_t is not None:
                dt = capture_timestamp_s - self._last_valid_t
                if dt > 1e-9:
                    vx = (detection.centroid_xy_px[0] - self._last_valid_pos[0]) / dt
                    vy = (detection.centroid_xy_px[1] - self._last_valid_pos[1]) / dt
                    self._velocity = (vx, vy)
                # dt<=0 (duplicate/out-of-order frame): keep the previous velocity estimate rather than divide by ~0.
            self._last_valid_pos = detection.centroid_xy_px
            self._last_valid_t = capture_timestamp_s
            self._last_valid_uncertainty = detection.uncertainty_px

        age = (now_s - self._last_valid_t) if self._last_valid_t is not None else 0.0
        # Uncertainty grows with age: a stale estimate is a WORSE estimate
        # of where the ball is NOW, not the same estimate it always was.
        # Linear growth is a simple, explicit, pre-registered choice -- not
        # a fitted/calibrated noise model (no such calibration exists this
        # round).
        growth_px_per_s = 200.0
        reported_uncertainty = (
            self._last_valid_uncertainty + growth_px_per_s * max(age, 0.0) if self._last_valid_pos is not None else float("inf")
        )

        return VisionObservation(
            capture_timestamp_s=capture_timestamp_s,
            detected=detection.detected,
            position_xy_px=self._last_valid_pos,
            velocity_xy_px_s=self._velocity if self._last_valid_pos is not None else None,
            uncertainty_px=reported_uncertainty,
            age_s=age,
            torso_angle_rad=proprio.torso_angle_rad,
            torso_vel_rad_s=proprio.torso_vel_rad_s,
            swing_angle_rad=proprio.swing_angle_rad,
            swing_vel_rad_s=proprio.swing_vel_rad_s,
            tilt_angle_rad=proprio.tilt_angle_rad,
            tilt_vel_rad_s=proprio.tilt_vel_rad_s,
            bat_contact=proprio.bat_contact,
            contact_force_n=proprio.contact_force_n,
        )

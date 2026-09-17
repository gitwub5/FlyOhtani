"""Adds TEMPORAL tracking and PREDICTION on top of ball_detector.py's
per-frame classical detector -- tracker.py's BallTracker only ever held
the last raw detection static and grew a heuristic uncertainty with age;
it never
actually predicted where the ball would be NOW using its own velocity.
KalmanBallTracker is a standard constant-velocity Kalman filter in PIXEL
space: it predicts forward through time on every call (so a miss/
occlusion still advances the position estimate along the last known
velocity, instead of freezing it) and corrects with a measurement only
when the detector actually finds the ball, weighting that correction by
the detector's OWN reported uncertainty_px (not a fixed number).

Like tracker.py, this module has NO import of flyohtani.sense.evaluator
and no import of any world/task module -- checked by the same AST-based
test (tests/test_sense_tracking.py). Ground-truth state is used ONLY by
the evaluator, never here.
"""
from __future__ import annotations

import numpy as np

from flyohtani.sense.ball_detector import Detection
from flyohtani.sense.observation import VisionObservation
from flyohtani.sense.tracker import Proprioception

# Pre-registered (not fit to any evaluation data): how much the
# constant-velocity assumption itself is expected to be violated per
# second, in pixels/s^2 -- pixel-space motion of an object under real 3D
# ballistic motion accelerates near the camera due to perspective, so this
# is deliberately generous, not tuned for best-looking results.
PROCESS_NOISE_ACCEL_STD_PX_S2 = 800.0
INITIAL_VELOCITY_UNCERTAINTY_PX_S = 2000.0  # a cold-start prior; overwhelmed by the first real measurement's own uncertainty within 1-2 updates


def _process_noise_q(dt: float, sigma_a: float) -> np.ndarray:
    """Standard discrete white-noise-acceleration model (e.g. Bar-Shalom
    et al., Estimation with Applications to Tracking and Navigation) for a
    [x, vx] pair, applied independently to x and y."""
    q = sigma_a**2
    dt2, dt3, dt4 = dt * dt, dt**3, dt**4
    block = np.array([[dt4 / 4, dt3 / 2], [dt3 / 2, dt2]]) * q
    Q = np.zeros((4, 4))
    Q[np.ix_([0, 2], [0, 2])] = block
    Q[np.ix_([1, 3], [1, 3])] = block
    return Q


def _transition_f(dt: float) -> np.ndarray:
    return np.array(
        [
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ]
    )


class KalmanBallTracker:
    def __init__(self, process_noise_accel_std_px_s2: float = PROCESS_NOISE_ACCEL_STD_PX_S2) -> None:
        self.sigma_a = process_noise_accel_std_px_s2
        self.state: np.ndarray | None = None  # [x, y, vx, vy]
        self.P: np.ndarray | None = None  # 4x4 covariance
        self.last_t: float | None = None
        self._n_detections = 0
        self._n_frames = 0

    @property
    def detection_rate(self) -> float:
        return self._n_detections / self._n_frames if self._n_frames else float("nan")

    def _predict(self, dt: float) -> None:
        F = _transition_f(dt)
        self.state = F @ self.state
        self.P = F @ self.P @ F.T + _process_noise_q(dt, self.sigma_a)

    def _kalman_update(self, detection: Detection) -> None:
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        z = np.array(detection.centroid_xy_px)
        R = np.eye(2) * (detection.uncertainty_px**2)
        y = z - H @ self.state
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P

    def update(
        self,
        detection: Detection,
        capture_timestamp_s: float,
        now_s: float,
        proprio: Proprioception,
    ) -> VisionObservation:
        self._n_frames += 1

        if self.state is None:
            if not detection.detected:
                return self._observation(None, None, float("inf"), 0.0, proprio, capture_timestamp_s)
            assert detection.centroid_xy_px is not None
            self.state = np.array([*detection.centroid_xy_px, 0.0, 0.0])
            self.P = np.diag(
                [
                    detection.uncertainty_px**2,
                    detection.uncertainty_px**2,
                    INITIAL_VELOCITY_UNCERTAINTY_PX_S**2,
                    INITIAL_VELOCITY_UNCERTAINTY_PX_S**2,
                ]
            )
            self.last_t = capture_timestamp_s
            self._n_detections += 1
        else:
            dt = capture_timestamp_s - self.last_t
            if dt > 0:
                self._predict(dt)
                self.last_t = capture_timestamp_s
            if detection.detected:
                self._kalman_update(detection)
                self._n_detections += 1

        # Report the filter's own PREDICTION forward to `now_s` (accounts
        # for capture->processing latency) WITHOUT committing it to
        # self.state/self.last_t -- the next real call still predicts from
        # the last actually-processed capture time, not from this
        # look-ahead value (avoids double-counting elapsed time).
        lookahead_dt = max(0.0, now_s - self.last_t)
        F = _transition_f(lookahead_dt)
        reported_state = F @ self.state
        reported_P = F @ self.P @ F.T + _process_noise_q(lookahead_dt, self.sigma_a)
        position = (float(reported_state[0]), float(reported_state[1]))
        velocity = (float(reported_state[2]), float(reported_state[3]))
        uncertainty = float(np.sqrt(reported_P[0, 0] + reported_P[1, 1]))
        age = now_s - self.last_t
        return self._observation(position, velocity, uncertainty, age, proprio, capture_timestamp_s, detected=detection.detected)

    def _observation(self, position, velocity, uncertainty, age, proprio, capture_timestamp_s, detected: bool = False) -> VisionObservation:
        return VisionObservation(
            capture_timestamp_s=capture_timestamp_s,
            detected=detected,
            position_xy_px=position,
            velocity_xy_px_s=velocity,
            uncertainty_px=uncertainty,
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

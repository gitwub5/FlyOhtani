from __future__ import annotations

import numpy as np

from envs.baseball_b1_env import ALIGNMENT, COURSES, CROSSING_TIME_S

# Strong hold gain: while waiting, the tilt axis must stay near prep_tilt=0
# against gravity (tilt has a real gravity torque, unlike the swing axis --
# see docs/records/VALIDATION_LOG.md). A weak gain (e.g. 3) let it drift
# ~0.21rad over 0.18s even while "correcting"; 50 keeps deviation under
# ~0.03rad. Swing has zero gravity torque so ctrl=0 already holds it exactly;
# the same hold function is applied to both for symmetry/simplicity.
_HOLD_GAIN = 50.0


def _hold(target: float, angle: float) -> float:
    return float(np.clip(_HOLD_GAIN * (target - angle), -1.0, 1.0))


class OracleAimController:
    """Reachability-diagnosis-only controller (docs/design/ENV-002-B1-courses.md
    section 4): reads the TRUE course label directly. Holds near prep, then
    triggers each axis's bang-bang independently at
    remaining_time == that axis's measured crossing time for this course
    (CROSSING_TIME_S), so both axes CROSS their target angle near ball-
    arrival time -- the same "cross, don't stop-and-hold" approach as
    BaseballB0Env's scripted controller. Two earlier attempts at continuous
    PD/two-phase feedback control both overshot badly (see
    docs/records/VALIDATION_LOG.md for the measured traces); this
    calibrated-crossing-time approach is what actually reaches all 9
    courses. This is privileged information a real policy never gets --
    never report this alongside scripted/learned baselines as if it were a
    fair comparison; it answers "can this body reach this course at all".
    """

    def __init__(self, course: str, prep_swing: float = 1.0, prep_tilt: float = 0.0) -> None:
        if course not in ALIGNMENT:
            raise ValueError(f"unknown course {course!r}")
        self.course = course
        self.prep_swing = prep_swing
        self.prep_tilt = prep_tilt
        self.swing_target, self.tilt_target = ALIGNMENT[course]
        self.swing_crossing_time, self.tilt_crossing_time = CROSSING_TIME_S[course]
        self._swinging = False
        self._tilting = False

    def reset(self) -> None:
        self._swinging = False
        self._tilting = False

    def act(self, obs: np.ndarray) -> np.ndarray:
        ball_vx = float(obs[3])
        swing_angle = float(obs[6])
        tilt_angle = float(obs[8])
        remaining = float(obs[10])
        approaching = ball_vx < 0.0

        if not self._swinging and approaching and 0.0 < remaining <= self.swing_crossing_time:
            self._swinging = True
        if not self._tilting and approaching and 0.0 < remaining <= self.tilt_crossing_time:
            self._tilting = True

        if self._swinging:
            swing_ctrl = 1.0 if self.swing_target > swing_angle else -1.0
        else:
            swing_ctrl = _hold(self.prep_swing, swing_angle)

        if self.tilt_crossing_time <= 0.0:
            tilt_ctrl = _hold(self.tilt_target, tilt_angle)
        elif self._tilting:
            tilt_ctrl = 1.0 if self.tilt_target > tilt_angle else -1.0
        else:
            tilt_ctrl = _hold(self.prep_tilt, tilt_angle)

        return np.array([swing_ctrl, tilt_ctrl], dtype=np.float32)


class ScriptedAimController:
    """Observation-only controller (ENV-002 section 6: no course label, no
    future plate-crossing point handed to the policy). Extrapolates the
    ball's own (y, z) at the known fixed target x-plane from the CURRENT
    observed position/velocity plus gravity (a physics constant, not hidden
    state -- gravity has no x-component, so the x-based time-to-target
    estimate is exact throughout flight). Converts that estimate to a
    (swing, tilt) aim and per-axis crossing time via linear fits to the 9
    known (course, alignment, crossing-time) triples -- a genuine aim/timing
    computation, not a label lookup. Same crossing-time trigger philosophy
    as OracleAimController."""

    def __init__(
        self, prep_swing: float = 1.0, prep_tilt: float = 0.0, gravity_z: float = -9.81
    ) -> None:
        self.prep_swing = prep_swing
        self.prep_tilt = prep_tilt
        self.gravity_z = gravity_z
        self._swing_coef, self._tilt_coef = self._fit_aim_model()
        # Tilt crossing time is strongly asymmetric (gravity helps negative
        # targets, fights positive ones) -- fit separate through-origin
        # slopes rather than one linear model.
        pos = [(ALIGNMENT[c][1], CROSSING_TIME_S[c][1]) for c in COURSES if ALIGNMENT[c][1] > 0]
        neg = [(ALIGNMENT[c][1], CROSSING_TIME_S[c][1]) for c in COURSES if ALIGNMENT[c][1] < 0]
        self._tilt_slope_pos = sum(t / a for a, t in pos) / len(pos)
        self._tilt_slope_neg = sum(t / a for a, t in neg) / len(neg)
        self._swing_crossing_time = sum(v[0] for v in CROSSING_TIME_S.values()) / len(CROSSING_TIME_S)
        self._swinging = False
        self._tilting = False

    @staticmethod
    def _fit_aim_model() -> tuple[np.ndarray, np.ndarray]:
        rows, swing_vals, tilt_vals = [], [], []
        for course, target in COURSES.items():
            y, z = float(target[1]), float(target[2])
            swing, tilt = ALIGNMENT[course]
            rows.append([1.0, y, z])
            swing_vals.append(swing)
            tilt_vals.append(tilt)
        design = np.array(rows)
        swing_coef, *_ = np.linalg.lstsq(design, np.array(swing_vals), rcond=None)
        tilt_coef, *_ = np.linalg.lstsq(design, np.array(tilt_vals), rcond=None)
        return swing_coef, tilt_coef

    def _aim_for(self, y: float, z: float) -> tuple[float, float]:
        feat = np.array([1.0, y, z])
        return float(feat @ self._swing_coef), float(feat @ self._tilt_coef)

    def _tilt_crossing_time(self, tilt_target: float) -> float:
        if tilt_target > 0:
            return self._tilt_slope_pos * tilt_target
        if tilt_target < 0:
            return self._tilt_slope_neg * abs(tilt_target)
        return 0.0

    def reset(self) -> None:
        self._swinging = False
        self._tilting = False
        self._swing_target = self.prep_swing
        self._tilt_target = self.prep_tilt

    def act(self, obs: np.ndarray) -> np.ndarray:
        ball_pos = obs[0:3]
        ball_vel = obs[3:6]
        swing_angle = float(obs[6])
        tilt_angle = float(obs[8])
        remaining = float(obs[10])
        approaching = float(ball_vel[0]) < 0.0

        # Lock in the aim estimate once, the first time either axis could
        # plausibly need to start moving, so the target doesn't keep
        # re-estimating (and re-triggering) every step.
        if approaching and not self._swinging and not self._tilting and 0.0 < remaining <= 0.30:
            t = remaining
            predicted_y = float(ball_pos[1]) + float(ball_vel[1]) * t
            predicted_z = float(ball_pos[2]) + float(ball_vel[2]) * t + 0.5 * self.gravity_z * t * t
            self._swing_target, self._tilt_target = self._aim_for(predicted_y, predicted_z)
            self._tilt_target = float(np.clip(self._tilt_target, -0.55, 0.55))

        tilt_crossing_time = self._tilt_crossing_time(self._tilt_target)

        if (
            not self._swinging
            and approaching
            and 0.0 < remaining <= self._swing_crossing_time
        ):
            self._swinging = True
        if not self._tilting and approaching and 0.0 < remaining <= tilt_crossing_time:
            self._tilting = True

        if self._swinging:
            swing_ctrl = 1.0 if self._swing_target > swing_angle else -1.0
        else:
            swing_ctrl = _hold(self.prep_swing, swing_angle)

        if tilt_crossing_time <= 0.0:
            tilt_ctrl = _hold(self._tilt_target, tilt_angle)
        elif self._tilting:
            tilt_ctrl = 1.0 if self._tilt_target > tilt_angle else -1.0
        else:
            tilt_ctrl = _hold(self.prep_tilt, tilt_angle)

        return np.array([swing_ctrl, tilt_ctrl], dtype=np.float32)


class FixedPoseAlwaysSwing:
    """ENV-002 section 6's "constant_pose/always_swing" baseline: no aiming
    (tilt held at 0), swings at full torque from t=0. Reference only."""

    def __init__(self, tilt_hold: float = 0.0) -> None:
        self.tilt_hold = tilt_hold

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        tilt_angle = float(obs[8])
        return np.array([-1.0, _hold(self.tilt_hold, tilt_angle)], dtype=np.float32)

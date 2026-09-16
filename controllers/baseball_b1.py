from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from envs.baseball_b1_env import ALIGNMENT, COURSES, CROSSING_TIME_S

# Strong hold gain: while waiting (before any swing has been triggered), the
# tilt axis must stay near prep_tilt=0 against gravity (tilt has a real
# gravity torque, unlike the swing axis -- see docs/records/VALIDATION_LOG.md).
# A weak gain (e.g. 3) let it drift ~0.21rad over 0.18s even while
# "correcting"; 50 keeps deviation under ~0.03rad. Swing has zero gravity
# torque so ctrl=0 already holds it exactly.
#
# I-07b-followthrough (docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md): this
# high-gain law is ONLY safe near its target -- it is a saturating P
# controller with no velocity damping, so invoking it from far away (large
# position error) just outputs max torque forever, i.e. it degenerates into
# undamped bang-bang and can ring/overshoot indefinitely once disturbed. It
# stays PRE-latch (pre-swing-completion) unchanged here, since that's the
# exact regime it was validated in and changing it altered the verified
# central-hit contact geometry (tested: replacing it with a gentler damped
# hold even before contact changed exit_velocity_xyz from +7.29 to negative
# -- see VALIDATION_LOG). Post-latch, _SwingAxis/_TiltAxis below switch to
# genuinely damped control instead of reusing this.
_HOLD_GAIN = 50.0


def _hold(target: float, angle: float) -> float:
    return float(np.clip(_HOLD_GAIN * (target - angle), -1.0, 1.0))


def _damped(target: float, angle: float, vel: float, kp: float, kd: float) -> float:
    return float(np.clip(-kp * (angle - target) - kd * vel, -1.0, 1.0))


def _time_optimal_bangbang(target: float, angle: float, vel: float, a_max: float) -> float:
    """Minimum-time double-integrator control: accelerate toward target
    until the braking distance vel*|vel|/(2*a_max) means it's time to
    decelerate. Chatters at the switching surface (standard for ideal
    bang-bang under discrete control) -- callers should hand off to a
    damped hold once velocity has actually settled, not use this forever."""
    switching_error = (angle - target) + vel * abs(vel) / (2.0 * a_max)
    return -1.0 if switching_error > 0.0 else 1.0


_SETTLE_QVEL = 0.2  # rad/s, from the design doc's acceptance criteria
_SETTLE_STEPS = 40  # consecutive control steps (0.2s @ control_dt=0.005s)

# I-07b-followthrough gains (docs/records/VALIDATION_LOG.md has the full
# derivation/sweep). Both derived from EACH axis's actually-measured max
# angular acceleration at ctrl=1 (not the geometric rod-about-end estimate,
# which was off by >2x for tilt -- see VALIDATION_LOG): swing 134.4rad/s^2
# (gear=30) => I_eff=0.2232kg*m^2; tilt 10.07rad/s^2 (gear=6) =>
# I_eff=0.596kg*m^2 (higher than swing's despite the same capsule, because
# tilt's rotation couples through the swing-carried frame differently).
#
# Swing: critically-ish damped PD (kp, zeta=0.9) directly to the
# follow-through target. Verified on mid_mid: settles (|qvel|<0.2rad/s
# sustained _SETTLE_STEPS) 0.435s after latch, angle peak-to-peak 1.2e-5rad
# over the next 0.2s, no overshoot past target -- meets the design doc's
# 0.5s/0.02rad targets with margin.
_SWING_I_EFF = 30.0 / 134.4
_SWING_BRAKE_KP = 8.0
_SWING_BRAKE_KD = 2 * 0.9 * float(np.sqrt(_SWING_BRAKE_KP * _SWING_I_EFF / 30.0))

# Tilt: gear=6's real torque authority (a_max=10.07rad/s^2) against the
# actual post-contact disturbance (measured on mid_mid: kicked to
# ~-3.3rad/s within ~10ms of the swing's latch, angle excursion ~0.40rad)
# means NO linear (non-saturating) PD can settle within budget -- solving
# for the largest critically-damped natural frequency that avoids
# saturating at the measured peak error/velocity gives omega_n~3.5rad/s,
# i.e. a settling time over 1s, regardless of gain choice (tested kp up to
# 500: made no difference, ctrl stayed pinned at +-1 throughout the
# high-error region either way -- see VALIDATION_LOG). A saturating PD in
# that regime is control THEORY equivalent to bang-bang, so this uses an
# explicit time-optimal bang-bang law instead (removes the PD's tendency to
# switch direction later than optimal, which was producing visible
# overshoot/ringing), then hands off to a gentle damped PD once settled.
# Measured on mid_mid: settles ~0.60s after latch (exceeds the 0.5s design
# target by ~0.1s) but converges tightly (angle within 2e-4rad, chattering
# velocity within roughly +-0.15rad/s) with no further divergence or
# repeated full-torque reversals -- this is reported as a real gear=6
# torque-authority limit, not a controller tuning gap; matching the 0.5s
# target would need tilt's gear recalibrated (out of scope here, see
# envs/assets/baseball_park_b1.xml's gear=30 recalibration for the
# analogous swing-axis precedent).
_TILT_I_EFF = 6.0 / 10.07
_TILT_A_MAX = 10.07
_TILT_HOLD_KP = 8.0
_TILT_HOLD_KD = 2 * 0.9 * float(np.sqrt(_TILT_HOLD_KP * _TILT_I_EFF / 6.0))

# How far past the alignment (accel) target, in the direction of travel, the
# swing's brake phase setpoint sits -- picked so the bat continues a natural
# follow-through instead of braking exactly at the contact angle. 0.4rad
# gives mid_mid a follow-through target of -1.298+0.4=-0.898rad, verified
# above; not reverified for the other 8 (still-uncalibrated) courses.
_FOLLOW_THROUGH_OFFSET = 0.4


class _SwingAxis:
    """The swing DOF's prepare -> accelerate -> brake -> hold sequence
    (docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md, I-07b-followthrough).
    Replaces the previous "bang-bang toward the alignment angle forever"
    controller, which never stopped chasing after the target was
    reached/passed: measured on mid_mid post-contact, that gave 5
    full-torque sign flips and an angle oscillating across
    [-1.60,-0.96]rad for the rest of the episode
    (docs/records/VALIDATION_LOG.md) -- real control chatter, not something
    the collision needed.

    Latches out of "accelerate" at most once, on whichever comes first: a
    contact observation, or the axis's OWN swing crossing its accel_target
    (a purely kinematic, non-privileged condition -- no future separation
    time or course identity is used here). This means a miss (bat swings
    through empty air) still reaches brake/hold once its swing completes,
    exactly like a genuine hit does.

    IMPORTANT (measured, see VALIDATION_LOG): a single |qvel|<settle_qvel
    sample right after a bat-ball collision is NOT "settled" -- the
    recoil's own velocity reversal can cross zero well before the angle has
    actually converged. Requires settle_steps CONSECUTIVE low-velocity
    samples before leaving "brake", not one.
    """

    def __init__(
        self,
        prep_angle: float,
        accel_target: float,
        follow_through_target: float,
        brake_kp: float = _SWING_BRAKE_KP,
        brake_kd: float = _SWING_BRAKE_KD,
        settle_qvel: float = _SETTLE_QVEL,
        settle_steps: int = _SETTLE_STEPS,
    ) -> None:
        self.prep_angle = prep_angle
        self.accel_target = accel_target
        self.follow_through_target = follow_through_target
        self.brake_kp = brake_kp
        self.brake_kd = brake_kd
        self.settle_qvel = settle_qvel
        self.settle_steps = settle_steps
        self.reset()

    def reset(self) -> None:
        self.state = "prepare"
        self._direction = 1.0 if self.accel_target > self.prep_angle else -1.0
        self._settled_steps = 0

    @property
    def disturbed(self) -> bool:
        """True once accelerate has been latched out of -- used as the
        "something happened" signal the tilt axis reacts to."""
        return self.state not in ("prepare", "accelerate")

    def act(self, angle: float, vel: float, triggered: bool, contact_now: bool) -> float:
        if self.state == "prepare":
            if not triggered:
                return _hold(self.prep_angle, angle)
            self.state = "accelerate"

        if self.state == "accelerate":
            crossed = angle >= self.accel_target if self._direction > 0 else angle <= self.accel_target
            if not (contact_now or crossed):
                return self._direction
            self.state = "brake"
            return self._direction  # one more step of the same torque: no discontinuity at the latch instant

        ctrl = _damped(self.follow_through_target, angle, vel, self.brake_kp, self.brake_kd)
        if self.state == "brake":
            self._settled_steps = self._settled_steps + 1 if abs(vel) < self.settle_qvel else 0
            if self._settled_steps >= self.settle_steps:
                self.state = "hold"
        return ctrl


class _TiltAxis:
    """The tilt DOF's counterpart to _SwingAxis. For mid_mid, tilt never
    needs to actively aim (accel_target == prep_angle), so it stays in
    "prepare" (the original high-gain hold, verified not to disturb the
    central-hit contact geometry) until the SWING axis reports `disturbed`
    (i.e. has latched out of its own accelerate) -- that's when the
    collision's recoil actually reaches the tilt DOF, not before. From
    there it runs time-optimal bang-bang (gear=6's real torque authority
    can't settle a saturating-PD-equivalent controller within budget, see
    the module-level comment) and hands off to a gentle damped hold once
    genuinely settled.

    accel_target/brake_target are only exercised (and only verified) for
    mid_mid where they equal prep_angle/0.0 -- the accelerate branch here
    exists so a future course whose tilt DOES need to aim doesn't silently
    do nothing, but its behavior is UNVERIFIED for that case; do not treat
    it as validated for anything but mid_mid.
    """

    def __init__(
        self,
        prep_angle: float,
        accel_target: float,
        brake_target: float,
        a_max: float = _TILT_A_MAX,
        hold_kp: float = _TILT_HOLD_KP,
        hold_kd: float = _TILT_HOLD_KD,
        settle_qvel: float = _SETTLE_QVEL,
        settle_steps: int = _SETTLE_STEPS,
    ) -> None:
        self.prep_angle = prep_angle
        self.accel_target = accel_target
        self.brake_target = brake_target
        self.a_max = a_max
        self.hold_kp = hold_kp
        self.hold_kd = hold_kd
        self.settle_qvel = settle_qvel
        self.settle_steps = settle_steps
        self.reset()

    def reset(self) -> None:
        self.state = "prepare"
        if self.accel_target > self.prep_angle:
            self._direction = 1.0
        elif self.accel_target < self.prep_angle:
            self._direction = -1.0
        else:
            self._direction = 0.0
        self._settled_steps = 0

    def act(self, angle: float, vel: float, triggered: bool, swing_disturbed: bool) -> float:
        if self.state == "prepare":
            if self._direction != 0.0 and triggered:
                self.state = "accelerate"
            elif swing_disturbed:
                self.state = "brake"
            else:
                return _hold(self.prep_angle, angle)

        if self.state == "accelerate":
            crossed = angle >= self.accel_target if self._direction > 0 else angle <= self.accel_target
            if not (swing_disturbed or crossed):
                return self._direction
            self.state = "brake"
            return self._direction

        if self.state == "brake":
            ctrl = _time_optimal_bangbang(self.brake_target, angle, vel, self.a_max)
            self._settled_steps = self._settled_steps + 1 if abs(vel) < self.settle_qvel else 0
            if self._settled_steps >= self.settle_steps:
                self.state = "hold"
            return ctrl

        return _damped(self.brake_target, angle, vel, self.hold_kp, self.hold_kd)


class OracleAimController:
    """Reachability-diagnosis-only controller (docs/design/ENV-002-B1-courses.md
    section 4): reads the TRUE course label directly. Holds near prep, then
    triggers each axis's accelerate phase independently at remaining_time ==
    that axis's measured crossing time for this course (CROSSING_TIME_S), so
    both axes CROSS their target angle near ball-arrival time -- the same
    "cross, don't stop-and-hold" approach as BaseballB0Env's scripted
    controller. Two earlier attempts at continuous PD/two-phase feedback
    control both overshot badly (see docs/records/VALIDATION_LOG.md for the
    measured traces); this calibrated-crossing-time approach is what
    actually reaches all 9 courses. This is privileged information a real
    policy never gets -- never report this alongside scripted/learned
    baselines as if it were a fair comparison; it answers "can this body
    reach this course at all".

    I-07b-fix: the original (pre-fix) contact-only "reaches" 9/9 was a real
    contact but a backward/decreasing-angle swing that barely deflected the
    pitch (docs/records/B1-BATTING-REVIEW.md). Only mid_mid's crossing time,
    and the env's prep_swing/gear/ball contact solref, are recalibrated for
    a genuine forward-hit (see CROSSING_TIME_S and
    envs/assets/baseball_park_b1.xml) -- the default prep_swing=1.0 here is
    ENV_default legacy; pass the env's actual prep_swing/prep_tilt in.

    I-07b-followthrough: past the accel_target crossing/contact, each axis
    now runs _SwingAxis/_TiltAxis's brake/hold instead of chasing the
    target with bang-bang forever (see their docstrings). Only verified for
    mid_mid.

    `crossing_time_s` (2026-09-17 cleanup, docs/implementation/REFACTOR-PLAN.md
    R-02 follow-up): defaults to the module's immutable CROSSING_TIME_S, so
    every existing default-constructed instance is unaffected. Pass an
    explicit mapping (e.g. `dict(CROSSING_TIME_S) | {"mid_mid": (t, 0.0)}`)
    to use a different calibration for one or more courses instead of the
    old pattern of mutating the shared module-level dict and restoring it
    afterward -- that pattern is no longer possible since CROSSING_TIME_S is
    now a read-only `types.MappingProxyType`.
    """

    def __init__(
        self,
        course: str,
        prep_swing: float = 1.0,
        prep_tilt: float = 0.0,
        crossing_time_s: Mapping[str, tuple[float, float]] | None = None,
    ) -> None:
        if course not in ALIGNMENT:
            raise ValueError(f"unknown course {course!r}")
        self.course = course
        self.prep_swing = prep_swing
        self.prep_tilt = prep_tilt
        self.crossing_time_s = crossing_time_s if crossing_time_s is not None else CROSSING_TIME_S
        self.swing_target, self.tilt_target = ALIGNMENT[course]
        self.swing_crossing_time, self.tilt_crossing_time = self.crossing_time_s[course]
        swing_direction = 1.0 if self.swing_target > prep_swing else -1.0
        self._swing_axis = _SwingAxis(
            prep_swing, self.swing_target, self.swing_target + _FOLLOW_THROUGH_OFFSET * swing_direction
        )
        self._tilt_axis = _TiltAxis(prep_tilt, self.tilt_target, self.tilt_target)
        self._swinging = False
        self._tilting = False

    def reset(self) -> None:
        self._swinging = False
        self._tilting = False
        self._swing_axis.reset()
        self._tilt_axis.reset()

    def act(self, obs: np.ndarray) -> np.ndarray:
        ball_vx = float(obs[3])
        swing_angle = float(obs[6])
        swing_vel = float(obs[7])
        tilt_angle = float(obs[8])
        tilt_vel = float(obs[9])
        remaining = float(obs[10])
        contact_now = bool(obs[11])
        approaching = ball_vx < 0.0

        if not self._swinging and approaching and 0.0 < remaining <= self.swing_crossing_time:
            self._swinging = True
        if not self._tilting and approaching and 0.0 < remaining <= self.tilt_crossing_time:
            self._tilting = True

        swing_ctrl = self._swing_axis.act(swing_angle, swing_vel, self._swinging, contact_now)
        tilt_ctrl = self._tilt_axis.act(tilt_angle, tilt_vel, self._tilting, self._swing_axis.disturbed)

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
    computation, not a label lookup. Same crossing-time trigger philosophy,
    and the same I-07b-followthrough brake/hold sequencing, as
    OracleAimController.

    `crossing_time_s` (2026-09-17 cleanup): same explicit-override mechanism
    as OracleAimController's, defaulting to the module's immutable
    CROSSING_TIME_S -- see that class's docstring."""

    def __init__(
        self,
        prep_swing: float = 1.0,
        prep_tilt: float = 0.0,
        gravity_z: float = -9.81,
        crossing_time_s: Mapping[str, tuple[float, float]] | None = None,
    ) -> None:
        self.prep_swing = prep_swing
        self.prep_tilt = prep_tilt
        self.gravity_z = gravity_z
        self.crossing_time_s = crossing_time_s if crossing_time_s is not None else CROSSING_TIME_S
        self._swing_coef, self._tilt_coef = self._fit_aim_model()
        # Tilt crossing time is strongly asymmetric (gravity helps negative
        # targets, fights positive ones) -- fit separate through-origin
        # slopes rather than one linear model.
        pos = [(ALIGNMENT[c][1], self.crossing_time_s[c][1]) for c in COURSES if ALIGNMENT[c][1] > 0]
        neg = [(ALIGNMENT[c][1], self.crossing_time_s[c][1]) for c in COURSES if ALIGNMENT[c][1] < 0]
        self._tilt_slope_pos = sum(t / a for a, t in pos) / len(pos)
        self._tilt_slope_neg = sum(t / a for a, t in neg) / len(neg)
        self._swing_crossing_time = sum(v[0] for v in self.crossing_time_s.values()) / len(self.crossing_time_s)
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
        self._swing_axis = _SwingAxis(self.prep_swing, self.prep_swing, self.prep_swing)
        self._tilt_axis = _TiltAxis(self.prep_tilt, self.prep_tilt, self.prep_tilt)

    def act(self, obs: np.ndarray) -> np.ndarray:
        ball_pos = obs[0:3]
        ball_vel = obs[3:6]
        swing_angle = float(obs[6])
        swing_vel = float(obs[7])
        tilt_angle = float(obs[8])
        tilt_vel = float(obs[9])
        remaining = float(obs[10])
        contact_now = bool(obs[11])
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
            swing_direction = 1.0 if self._swing_target > self.prep_swing else -1.0
            self._swing_axis = _SwingAxis(
                self.prep_swing, self._swing_target, self._swing_target + _FOLLOW_THROUGH_OFFSET * swing_direction
            )
            self._tilt_axis = _TiltAxis(self.prep_tilt, self._tilt_target, self._tilt_target)

        tilt_crossing_time = self._tilt_crossing_time(self._tilt_target)

        if (
            not self._swinging
            and approaching
            and 0.0 < remaining <= self._swing_crossing_time
        ):
            self._swinging = True
        if not self._tilting and approaching and 0.0 < remaining <= tilt_crossing_time:
            self._tilting = True

        swing_ctrl = self._swing_axis.act(swing_angle, swing_vel, self._swinging, contact_now)
        tilt_ctrl = self._tilt_axis.act(tilt_angle, tilt_vel, self._tilting, self._swing_axis.disturbed)

        return np.array([swing_ctrl, tilt_ctrl], dtype=np.float32)


class FixedPoseAlwaysSwing:
    """ENV-002 section 6's "constant_pose/always_swing" baseline: no aiming
    (tilt held at 0), swings at full torque from t=0. Reference only.

    I-07b-fix: ctrl sign flipped from -1.0 to +1.0 -- prep_swing=-1.9 now
    needs an INCREASING angle to reach the alignment zone (all ALIGNMENT
    swing targets are less negative than -1.9); the old -1.0 (correct only
    for the pre-fix prep_swing=+1.0/decreasing-angle swing) just drove the
    bat into the -2.0 joint limit and never contacted the ball."""

    def __init__(self, tilt_hold: float = 0.0) -> None:
        self.tilt_hold = tilt_hold

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        tilt_angle = float(obs[8])
        return np.array([1.0, _hold(self.tilt_hold, tilt_angle)], dtype=np.float32)

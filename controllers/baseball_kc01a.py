"""KC-01a (docs/design/KC-01a-TORSO-BAT-COORDINATION.md) controllers: one
generic prepare->accelerate->brake->hold axis state machine (the same
control philosophy as controllers/baseball_b1.py's `_SwingAxis`/`_TiltAxis`,
reimplemented here rather than imported so this module stays fully
independent of B1's controller file -- B1 stays frozen, and KC-01a's own
per-axis gains/inertia are different numbers derived from KC-01a's own
measurements, not B1's), driving 2 real DOF (torso_yaw, bat_hinge) plus a
held tilt (bat_tilt_hinge stays at prep_tilt=0.0 the whole episode for
mid_mid -- the calibrated target-angle search in docs/design/
KC-01a-TORSO-BAT-COORDINATION.md section 2 found tilt=0.0 in every
condition, matching B1's own mid_mid precedent where tilt never needs to
actively aim).

Four coordination modes (docs/design/KC-01a-TORSO-BAT-COORDINATION.md
section 3), all built from the SAME hardware (same gear/range on every
axis -- only which axes move, and when, differs):

- "arm_only": torso held at 0 throughout; swing alone reaches the target
  (reproduces B1's own mid_mid geometry, since torso=0 makes this
  environment's kinematics identical to B1's fixed-torso case).
- "torso_only": swing/tilt held at prep; torso alone reaches the target.
- "simultaneous": torso and swing triggered at the same crossing time.
- "staggered": torso triggers earlier than swing (hips lead, arm follows) --
  by a fixed TIME offset only; swing's own trigger is still purely
  time-based (docs/design/KC-01a-DIRECTION-CONTRACT.md section 4/
  docs/records/KC-01a-VALIDATION.md A8: this makes "leads" a claim about
  COMMAND onset, not about torso having actually moved a meaningful amount
  before swing's own command starts -- at torso's much lower a_max
  (11.41 vs swing's 134.4 rad/s^2), a fixed-time lead can still coincide
  with swing's own rapid response overtaking torso within 1-2 control
  steps).
- "torso_lead_handoff" (added for the user's follow-up: a genuine
  motion-triggered handoff instead of a fixed time offset): torso triggers
  the same way every other mode does (ball-approach crossing-time), but
  swing's OWN trigger is not time-based at all -- swing stays in
  "prepare"/hold until torso's own angular displacement toward its target
  reaches `handoff_fraction` of that target (see TorsoBatController's own
  docstring for the parameter). This is the only mode where one axis's
  trigger condition depends on another axis's actual state rather than the
  ball's arrival time.
"""
from __future__ import annotations

import numpy as np


def _hold(target: float, angle: float, gain: float) -> float:
    return float(np.clip(gain * (target - angle), -1.0, 1.0))


def _damped(target: float, angle: float, vel: float, kp: float, kd: float) -> float:
    return float(np.clip(-kp * (angle - target) - kd * vel, -1.0, 1.0))


class _Axis:
    """One actuated DOF's prepare -> accelerate -> brake -> hold sequence.
    Generic version of controllers/baseball_b1.py's _SwingAxis/_TiltAxis:
    constant max-torque "accelerate" (no premature braking) until the
    target is crossed or a `disturbed_by` signal fires (e.g. contact, or
    another axis's own latch, for coordination), then a critically-ish
    damped PD to a follow-through target, with an explicit
    settle-steps-consecutive-below-threshold hold gate (a single low-|vel|
    sample right after a collision is not "settled" -- see B1's own
    VALIDATION_LOG for why)."""

    def __init__(
        self,
        prep_angle: float,
        accel_target: float,
        follow_through_target: float,
        brake_kp: float,
        brake_kd: float,
        hold_gain: float = 50.0,
        settle_qvel: float = 0.2,
        settle_steps: int = 40,
    ) -> None:
        self.prep_angle = prep_angle
        self.accel_target = accel_target
        self.follow_through_target = follow_through_target
        self.brake_kp = brake_kp
        self.brake_kd = brake_kd
        self.hold_gain = hold_gain
        self.settle_qvel = settle_qvel
        self.settle_steps = settle_steps
        self.reset()

    def reset(self) -> None:
        self.state = "prepare"
        self._direction = 1.0 if self.accel_target > self.prep_angle else -1.0
        self._settled_steps = 0

    @property
    def disturbed(self) -> bool:
        return self.state not in ("prepare", "accelerate")

    def act(self, angle: float, vel: float, triggered: bool, latch_now: bool) -> float:
        if self.state == "prepare":
            if not triggered:
                return _hold(self.prep_angle, angle, self.hold_gain)
            self.state = "accelerate"

        if self.state == "accelerate":
            crossed = angle >= self.accel_target if self._direction > 0 else angle <= self.accel_target
            if not (latch_now or crossed):
                return self._direction
            self.state = "brake"
            return self._direction

        ctrl = _damped(self.follow_through_target, angle, vel, self.brake_kp, self.brake_kd)
        if self.state == "brake":
            self._settled_steps = self._settled_steps + 1 if abs(vel) < self.settle_qvel else 0
            if self._settled_steps >= self.settle_steps:
                self.state = "hold"
        return ctrl


def _brake_gains(gear: float, a_max: float, kp: float = 8.0, zeta: float = 0.9) -> tuple[float, float]:
    """Same derivation as controllers/baseball_b1.py's module-level
    comment: I_eff = gear / a_max (measured, not the geometric estimate),
    kd = 2*zeta*sqrt(kp*I_eff/gear)."""
    i_eff = gear / a_max
    kd = 2 * zeta * float(np.sqrt(kp * i_eff / gear))
    return kp, kd


# Measured a_max (rad/s^2 at ctrl=1), docs/design/KC-01a-TORSO-BAT-
# COORDINATION.md section 2:
# - swing (gear=30): inherited from B1's own measurement (134.4) -- the
#   bat's own inertia about bat_hinge does not depend on torso_yaw's state
#   when torso is held fixed, which every KC-01a condition's swing-active
#   phase does relative to ITS OWN moment (torso may also be moving, but
#   swing's a_max was measured, like B1's, from prep with torso held at 0).
# - torso (gear=30): measured directly on KC-01a (11.41), WITH swing/tilt
#   held at prep -- this is NOT the isolated-body value (a_max would be far
#   higher without the bat+ball's moment of inertia loading the axis); it
#   is the actually-relevant "arm in its prep pose" loaded value.
_SWING_A_MAX = 134.4
_TORSO_A_MAX = 11.41
SWING_BRAKE_KP, SWING_BRAKE_KD = _brake_gains(30.0, _SWING_A_MAX)
TORSO_BRAKE_KP, TORSO_BRAKE_KD = _brake_gains(30.0, _TORSO_A_MAX)

# Follow-through offset past each axis's accel_target, in the direction of
# travel (same idea as B1's _FOLLOW_THROUGH_OFFSET=0.4rad, scaled down for
# torso's much smaller total range of motion).
_SWING_FOLLOW_THROUGH_OFFSET = 0.4
_TORSO_FOLLOW_THROUGH_OFFSET = 0.15

TILT_HOLD_GAIN = 50.0
TORSO_HOLD_GAIN = 50.0
SWING_HOLD_GAIN = 50.0  # swing has ~zero gravity torque (vertical-axis rotation, same as B1)

# Mirrors envs/assets/baseball_park_kc01a.xml's torso_yaw/bat_hinge
# jnt_range -- this module has no env/XML dependency by design (same
# convention scripts/kc01a_calibrate.py already uses for its own
# TORSO_LIMIT/SWING_LIMIT), so these are hardcoded and must be kept in sync
# with the XML by hand if the XML ever changes.
TORSO_RANGE = (-0.6, 0.6)
SWING_RANGE = (-2.0, 2.0)


def validate_same_direction_candidate(
    prep_torso: float,
    prep_swing: float,
    torso_target: float,
    swing_target: float,
    min_swing_displacement_rad: float = 0.3,
    joint_margin_rad: float = 0.02,
) -> tuple[bool, list[str]]:
    """Pre-registered validity filter for a same-direction (torso+swing
    co-rotating) candidate, checked BEFORE any simulation is run (docs/
    design/KC-01a-DIRECTION-CONTRACT.md section 8 -- added after a
    "validated" candidate turned out to have torso and swing accelerating
    in OPPOSITE directions with both follow-through targets outside their
    own joint ranges, none of which the earlier search or acceptance
    checks had verified).

    Three independent checks, ALL reported (not just the first failure):
    1. Direction consistency: torso_target and swing_target must lie on the
       SAME side of their respective prep angles -- a "same-direction
       kinetic chain" candidate where the arm's own commanded direction is
       opposite the torso's is not what this mode is for, regardless of
       what score it produces.
    2. Minimum genuine swing displacement: a near-zero (or wrong-signed)
       swing move is not a real arm swing even if a geometry search happens
       to find it as the closest-approach solution once torso alone nearly
       reaches the target.
    3. Joint-range margin: prep/target/follow-through angles for BOTH axes
       (follow-through = target + offset*direction, the same formula
       TorsoBatController.__init__ uses) must stay within
       [range_lo+margin, range_hi-margin] -- a follow-through target
       outside the physical range can only ever be "reached" by hitting the
       hard joint-limit stop, not by the PD brake actually converging to it
       (docs/records/KC-01a-VALIDATION.md A12's own finding).

    Returns (valid, reasons) -- reasons is empty iff valid is True.
    """
    reasons: list[str] = []
    torso_dir = 1.0 if torso_target > prep_torso else -1.0
    swing_dir = 1.0 if swing_target > prep_swing else -1.0
    if torso_dir != swing_dir:
        reasons.append(
            f"direction mismatch: torso_dir={torso_dir:+.0f} swing_dir={swing_dir:+.0f} "
            "(same-direction chain requires both axes to accelerate the same sign)"
        )

    swing_disp = swing_target - prep_swing
    if abs(swing_disp) < min_swing_displacement_rad:
        reasons.append(
            f"swing displacement too small: {swing_disp:+.4f}rad "
            f"(< {min_swing_displacement_rad}rad minimum -- not a genuine arm swing)"
        )

    torso_ft = torso_target + _TORSO_FOLLOW_THROUGH_OFFSET * torso_dir
    swing_ft = swing_target + _SWING_FOLLOW_THROUGH_OFFSET * swing_dir
    checks = (
        ("torso prep", prep_torso, TORSO_RANGE),
        ("torso target", torso_target, TORSO_RANGE),
        ("torso follow-through", torso_ft, TORSO_RANGE),
        ("swing prep", prep_swing, SWING_RANGE),
        ("swing target", swing_target, SWING_RANGE),
        ("swing follow-through", swing_ft, SWING_RANGE),
    )
    for name, angle, (lo, hi) in checks:
        if not (lo + joint_margin_rad <= angle <= hi - joint_margin_rad):
            reasons.append(
                f"{name}={angle:+.4f}rad outside [{lo + joint_margin_rad:+.4f}, "
                f"{hi - joint_margin_rad:+.4f}]rad (range {lo}..{hi}, margin {joint_margin_rad}rad)"
            )

    return (len(reasons) == 0, reasons)


class TorsoBatController:
    """mid_mid-only oracle controller (reads the calibrated target/timing
    tables directly, like B1's OracleAimController -- reachability/
    mechanism diagnosis, not a fair policy comparison). `mode` selects
    which axes move and when; `torso_crossing_time`/`swing_crossing_time`
    are independently settable so callers (comparison-condition scripts,
    timing-sensitivity sweeps) can override the calibrated defaults."""

    def __init__(
        self,
        mode: str,
        prep_torso: float,
        prep_swing: float,
        prep_tilt: float,
        torso_target: float,
        swing_target: float,
        torso_crossing_time: float,
        swing_crossing_time: float,
        handoff_fraction: float = 0.3,
    ) -> None:
        if mode not in ("arm_only", "torso_only", "simultaneous", "staggered", "torso_lead_handoff"):
            raise ValueError(f"unknown mode {mode!r}")
        self.mode = mode
        self.prep_torso = prep_torso
        self.prep_swing = prep_swing
        self.prep_tilt = prep_tilt
        self.torso_target = torso_target
        self.swing_target = swing_target
        self.torso_crossing_time = torso_crossing_time
        self.swing_crossing_time = swing_crossing_time
        # Only used by mode="torso_lead_handoff" (ignored otherwise): swing's
        # own trigger fires once |torso_angle - prep_torso| reaches this
        # fraction of |torso_target - prep_torso| -- a genuine
        # motion-triggered handoff (docs/design/KC-01a-DIRECTION-CONTRACT.md
        # section 4's follow-up), not a fixed time offset like "staggered".
        self.handoff_fraction = handoff_fraction

        torso_moves = mode in ("torso_only", "simultaneous", "staggered", "torso_lead_handoff")
        swing_moves = mode in ("arm_only", "simultaneous", "staggered", "torso_lead_handoff")
        torso_dir = 1.0 if torso_target > prep_torso else -1.0
        swing_dir = 1.0 if swing_target > prep_swing else -1.0
        # Stored (not just local) so act() can compute SIGNED progress along
        # the intended direction for the handoff condition below -- using
        # abs(torso_angle - prep_torso) instead would let a torso excursion
        # in the WRONG direction also satisfy the handoff threshold, which
        # is not "torso has progressed toward its target" (docs/design/
        # KC-01a-DIRECTION-CONTRACT.md section 8's fix).
        self._torso_dir = torso_dir
        self._swing_dir = swing_dir
        self._torso_axis = _Axis(
            prep_torso,
            torso_target if torso_moves else prep_torso,
            (torso_target + _TORSO_FOLLOW_THROUGH_OFFSET * torso_dir) if torso_moves else prep_torso,
            TORSO_BRAKE_KP,
            TORSO_BRAKE_KD,
            hold_gain=TORSO_HOLD_GAIN,
        )
        self._swing_axis = _Axis(
            prep_swing,
            swing_target if swing_moves else prep_swing,
            (swing_target + _SWING_FOLLOW_THROUGH_OFFSET * swing_dir) if swing_moves else prep_swing,
            SWING_BRAKE_KP,
            SWING_BRAKE_KD,
            hold_gain=SWING_HOLD_GAIN,
        )
        self._torso_moves = torso_moves
        self._swing_moves = swing_moves
        self._torso_triggered = False
        self._swing_triggered = False

    def reset(self) -> None:
        self._torso_axis.reset()
        self._swing_axis.reset()
        self._torso_triggered = False
        self._swing_triggered = False

    def act(self, obs: np.ndarray) -> np.ndarray:
        # Observation layout: ball_pos(3) ball_vel(3) torso_angle torso_vel
        # swing_angle swing_vel tilt_angle tilt_vel remaining contact step.
        ball_vx = float(obs[3])
        torso_angle, torso_vel = float(obs[6]), float(obs[7])
        swing_angle, swing_vel = float(obs[8]), float(obs[9])
        tilt_angle = float(obs[10])
        remaining = float(obs[12])
        contact_now = bool(obs[13])
        approaching = ball_vx < 0.0

        if (
            self._torso_moves
            and not self._torso_triggered
            and approaching
            and 0.0 < remaining <= self.torso_crossing_time
        ):
            self._torso_triggered = True
        if self.mode == "torso_lead_handoff":
            # Motion-triggered, not time-triggered: swing waits for torso to
            # have actually PROGRESSED toward its own target, regardless of
            # how much real time that takes -- the point of this mode
            # (docs/design/KC-01a-DIRECTION-CONTRACT.md section 4 follow-up).
            # SIGNED progress along the intended direction (self._torso_dir),
            # not abs(torso_angle - prep_torso): a torso excursion in the
            # WRONG direction (e.g. a reaction dip) must NOT count toward
            # the handoff threshold (section 8's fix -- abs() would have let
            # it).
            handoff_target_disp = self.handoff_fraction * abs(self.torso_target - self.prep_torso)
            torso_progress = (torso_angle - self.prep_torso) * self._torso_dir
            if (
                self._swing_moves
                and not self._swing_triggered
                and self._torso_triggered
                and torso_progress >= handoff_target_disp
            ):
                self._swing_triggered = True
        elif (
            self._swing_moves
            and not self._swing_triggered
            and approaching
            and 0.0 < remaining <= self.swing_crossing_time
        ):
            self._swing_triggered = True

        torso_ctrl = self._torso_axis.act(
            torso_angle, torso_vel, self._torso_triggered, contact_now or self._swing_axis.disturbed
        )
        swing_ctrl = self._swing_axis.act(
            swing_angle, swing_vel, self._swing_triggered, contact_now or self._torso_axis.disturbed
        )
        tilt_ctrl = _hold(self.prep_tilt, tilt_angle, TILT_HOLD_GAIN)

        return np.array([torso_ctrl, swing_ctrl, tilt_ctrl], dtype=np.float32)


class ZeroTorqueController:
    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return np.zeros(3, dtype=np.float32)

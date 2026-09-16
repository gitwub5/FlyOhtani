from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

ASSET_PATH = Path(__file__).resolve().parent / "assets" / "baseball_park_b1.xml"

# Terminal (terminated=True) reasons.
END_NO_PITCH_CONTACT = "no_pitch_contact"  # ball passed the plate, bat never touched it
END_GROUND_BEFORE_BAT_CONTACT = "ground_before_bat_contact"  # pitch hit ground first
END_GROUND_BEFORE_SEPARATION = "ground_before_separation"  # ball+bat still interacting, hit ground
END_BATTED_BALL_LANDING = "batted_ball_landing"  # clean separation, then ball lands
END_OUT_OF_BOUNDS = "out_of_bounds"  # safety net, ball leaves any plausible field extent
# Truncated (truncated=True) reasons.
END_TIMEOUT_PITCH = "timeout_pitch"
END_TIMEOUT_FLIGHT = "timeout_flight"

SEPARATION_CONFIRM_S = 0.002
PROLONGED_CONTACT_S = 0.05
FORWARD_GATE_X = 5.0
OUT_OF_BOUNDS_XY = 150.0

# I-07c-score (docs/design/BATTING-QUALITY-AND-SWING.md section 1): field
# coordinate origin is home plate's own back vertex, +x toward the pitcher's
# rubber (envs/assets/baseball_park_b1.xml line 2-4 coordinate-system
# comment) -- so "home reference point" is just the world XY origin and
# "forward" is +x. Recorded here (not derived from a runtime geom lookup)
# because home_plate's own geom pos (0.2159, 0, ...) is the plate's *visual
# center*, not its back-vertex origin-defining corner.
HOME_REFERENCE_XY = np.array([0.0, 0.0])

# Course grid (docs/design/ENV-002-B1-courses.md section 1). x is always the
# same plate-front reference as B0 (0.4318); only y (inside/outside) and z
# (high/low) vary per course.
ZONE_CENTER = np.array([0.4318, 0.0, 1.0])
ZONE_HALF_WIDTH_Y = 0.2159
ZONE_HALF_HEIGHT_Z = 0.35
_U = {"in": 2 / 3, "mid": 0.0, "out": -2 / 3}
_V = {"high": 2 / 3, "mid": 0.0, "low": -2 / 3}
COURSES: dict[str, np.ndarray] = {
    f"{uname}_{vname}": np.array(
        [ZONE_CENTER[0], ZONE_CENTER[1] + u * ZONE_HALF_WIDTH_Y, ZONE_CENTER[2] + v * ZONE_HALF_HEIGHT_Z]
    )
    for uname, u in _U.items()
    for vname, v in _V.items()
}

# Per-course (swing, tilt) geometric alignment: the (swing, tilt) angle pair
# where the bat passes closest to the course's target point (2D grid search,
# docs/design/ENV-002-B1-courses.md section 3). This is direction-independent
# geometry, so it is UNCHANGED by the I-07b-fix swing-direction reversal --
# only which direction/prep angle the bat approaches it from changed.
ALIGNMENT: dict[str, tuple[float, float]] = {
    "in_high": (-1.226, 0.410),
    "in_mid": (-1.226, 0.000),
    "in_low": (-1.226, -0.410),
    "mid_high": (-1.298, 0.332),
    "mid_mid": (-1.298, 0.000),
    "mid_low": (-1.298, -0.332),
    "out_high": (-1.346, 0.280),
    "out_mid": (-1.346, 0.000),
    "out_low": (-1.346, -0.280),
}

# Per-course (swing_crossing_time, tilt_crossing_time): how long before the
# ball's predicted arrival each axis's bang-bang trigger should fire so it
# crosses ALIGNMENT near arrival ("cross, don't stop-and-hold", same
# philosophy as BaseballB0Env's scripted controller -- see
# controllers/baseball_b1.py). ONLY mid_mid is recalibrated (first for
# I-07b-fix, then again for I-07c-swing below). The other 8 entries are
# UNCHANGED from before I-07b-fix (commit c812766): calibrated for the old
# prep_swing=1.0, decreasing-angle (backward) swing at gear=12, against a
# contact-only success criterion. They are almost certainly wrong for the
# current prep_swing/gear=30/solref-fixed physics and must NOT be used as
# evidence of reachability until a future 9-course expansion step
# recalibrates them the same way mid_mid was.
#
# I-07c-swing (docs/design/BATTING-QUALITY-AND-SWING.md section 2;
# docs/records/VALIDATION_LOG.md has the full prep-angle/trigger sweep):
# prep_swing widened from -1.9 to -1.96 (bat_hinge's fixed joint range is
# [-2.0, 2.0] -- gear/mass/inertia/material/dt/pitch all held fixed, ONLY
# the windup distance and its matching trigger time changed). Under the
# swing axis's already-optimal constant-max-torque "accelerate" phase (no
# premature target-arrival braking -- see _SwingAxis), a longer windup
# purely from a further-back prep angle raises contact-point speed
# (v=sqrt(2*a_max*delta_theta)): mid_mid, trigger=0.09425316355759385s of a
# 0.459091s flight, bat_contact_vx=+7.40 m/s (was +6.98), exit_speed=8.61
# m/s (was 8.53), forward_flight_success=True, batting_score=8.48m (was
# 5.82m, +46%), settle 0.431s post-contact / 4.3e-5rad peak-to-peak (both
# within the 0.5s/0.02rad targets). Trade-off found and reported, not
# hidden: exit launch angle rose to 41.2deg (was 14.0deg) -- a markedly
# higher trajectory, not merely a faster line drive, because the new
# contact instant (still a purely kinematic function of trigger timing, not
# hand-picked for its look) lands at a different point along the bat's
# continuous sweep. ALSO found and reported: BOTH the old (-1.9) and new
# (-1.96) trigger times are extremely sensitive to a single control-step
# (0.005s) shift -- either direction flips forward_flight_success to False
# on BOTH prep angles (verified for -1.9 too, not unique to this change).
# This is a pre-existing contact-timing fragility of the bang-bang
# oracle/collision design, unchanged in kind by this recalibration; fixing
# it would need a different (closed-loop/contact-triggered) control
# approach, out of scope here. Only mid_mid uses -1.96; the other 8 courses
# keep whatever prep_swing they're constructed with (single scalar; see
# BaseballB1Env.__init__).
CROSSING_TIME_S: dict[str, tuple[float, float]] = {
    "in_high": (0.25, 0.41),
    "in_mid": (0.27, 0.0),
    "in_low": (0.23, 0.33),
    "mid_high": (0.27, 0.28),
    "mid_mid": (0.09425316355759385, 0.0),  # I-07c-swing recalibration (was 0.094091 for prep_swing=-1.9; see comment above)
    "mid_low": (0.25, 0.30),
    "out_high": (0.29, 0.28),
    "out_mid": (0.29, 0.0),
    "out_low": (0.26, 0.31),
}


@dataclass(frozen=True)
class RewardWeights:
    """batted-ball-v1 (I-07b-fix, docs/design/ENV-002-BATTED-BALL.md section 4).
    Replaces b0-contact-v1's on-contact reward entirely: mere contact scores
    0; only forward_flight_success scores +10 (once). miss=-3 on any other
    normal (non-timeout) termination. control_cost unchanged in form, now
    integrated across the whole episode (pitch + contact + flight)."""

    forward_flight_success: float = 10.0
    miss: float = 3.0
    control_cost: float = 0.2


@dataclass(frozen=True)
class ForwardCarryRewardWeights:
    """forward-carry-v1 (I-07c-score, docs/design/BATTING-QUALITY-AND-SWING.md
    section 1). Named and versioned separately from batted-ball-v1 -- never
    silently mixed with it (CLAUDE.md reward-versioning discipline). Always
    computed alongside batted-ball-v1 (see BaseballB1Env._info()'s
    "forward_carry_v1" key) so the two can be compared on identical
    episodes, but batted-ball-v1 remains the reward actually returned by
    step() until a caller explicitly opts in via reward_version=
    "forward-carry-v1". RL training on this reward has not started.

    On a normal (non-timeout, non-out-of-bounds) termination: outcome =
    outcome_scale * batting_score if scoring_valid else -miss_penalty.
    control_cost is the same time-integrated -0.2*(u_swing^2+u_tilt^2)dt as
    batted-ball-v1 (unchanged, per spec). Timeout/out-of-bounds endings
    (status="incomplete") get neither the outcome reward nor the miss
    penalty -- only the already-accrued control cost is kept. The old
    contact/gate +10 (forward_flight_success) is intentionally NOT included
    here to avoid double-paying it alongside the new outcome term.
    """

    outcome_scale: float = 0.1
    miss_penalty: float = 3.0
    control_cost: float = 0.2


class BaseballB1Env(gym.Env):
    """ENV-002 stage B1 (I-07b-fix): same fixed release/horizontal-speed
    pitch as B0, aimed at one of 9 courses, with a 2-DOF bat (horizontal
    swing + tilt). Success is a genuine forward-hit batted ball tracked to
    landing (docs/design/ENV-002-BATTED-BALL.md), not mere bat contact --
    see docs/records/B1-BATTING-REVIEW.md for why the original contact-only
    design was wrong (it hit the ball further in the pitch's own -x
    direction, not toward +x/infield).

    Kept as a separate class/XML from BaseballB0Env (envs/baseball_env.py) so
    B0's already-verified behavior/tests are never at risk of regressing.

    Action: [swing_ctrl, tilt_ctrl], both in [-1, 1].
    Observation (13-dim): ball_pos(3), ball_vel(3), swing_angle, swing_vel,
    tilt_angle, tilt_vel, predicted_time_to_target, prev_contact,
    normalized_step (pitch-phase step count only). The course identity/
    target/phase/exit-velocity are NOT in the observation (ENV-002 section 6)
    -- only info carries them, for logging/oracle use.
    """

    metadata: ClassVar[dict[str, Any]] = {
        "render_modes": ["human", "rgb_array", None],
        "render_fps": 60,
    }

    RELEASE = np.array([16.5, 0.0, 1.8])
    HORIZONTAL_SPEED = 35.0

    def __init__(
        self,
        xml_path: str | Path = ASSET_PATH,
        render_mode: str | None = None,
        frame_skip: int = 20,
        pitch_timeout_s: float = 1.2,
        flight_timeout_s: float = 10.0,
        reward_weights: RewardWeights | None = None,
        forward_carry_reward_weights: ForwardCarryRewardWeights | None = None,
        reward_version: str = "batted-ball-v1",
        seed: int | None = None,
        # I-07c-swing: widened from -1.9 to -1.96 (bat_hinge's fixed joint
        # limit is -2.0; see CROSSING_TIME_S's comment above for the
        # measured before/after). Only mid_mid's own CROSSING_TIME_S entry
        # is retuned to match -1.96 -- the other 8 courses' crossing times
        # remain the pre-I-07b-fix values and are already flagged unusable.
        prep_swing: float = -1.96,
        prep_tilt: float = 0.0,
        pass_margin: float = 0.25,
        default_course: str = "mid_mid",
    ) -> None:
        super().__init__()
        self.xml_path = Path(xml_path)
        self.model = mujoco.MjModel.from_xml_path(str(self.xml_path))
        self.data = mujoco.MjData(self.model)
        self.frame_skip = frame_skip
        self.render_mode = render_mode
        self.pitch_timeout_s = pitch_timeout_s
        self.flight_timeout_s = flight_timeout_s
        self.max_pitch_steps = int(pitch_timeout_s / (self.model.opt.timestep * frame_skip))
        self.reward_weights = reward_weights or RewardWeights()
        self.forward_carry_reward_weights = forward_carry_reward_weights or ForwardCarryRewardWeights()
        if reward_version not in ("batted-ball-v1", "forward-carry-v1"):
            raise ValueError(
                f"unknown reward_version {reward_version!r}; must be 'batted-ball-v1' or 'forward-carry-v1'"
            )
        self.reward_version = reward_version
        self._rng = np.random.default_rng(seed)
        self._renderer: dict[str, mujoco.Renderer] = {}

        self.prep_swing = float(prep_swing)
        self.prep_tilt = float(prep_tilt)
        self.pass_x = float(ZONE_CENTER[0] - pass_margin)
        self.default_course = default_course

        self.ball_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        self.ball_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
        self.bat_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "bat_geom")
        self.bat_body_id = int(self.model.geom_bodyid[self.bat_geom_id])
        self.ground_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ground")
        self.batter_box_geom_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_GEOM, "batter_box_rh"
        )
        self.batter_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "batter_body")
        self.swing_joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "bat_hinge")
        self.tilt_joint_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_JOINT, "bat_tilt_hinge"
        )
        self.swing_qpos_adr = self.model.jnt_qposadr[self.swing_joint_id]
        self.swing_qvel_adr = self.model.jnt_dofadr[self.swing_joint_id]
        self.tilt_qpos_adr = self.model.jnt_qposadr[self.tilt_joint_id]
        self.tilt_qvel_adr = self.model.jnt_dofadr[self.tilt_joint_id]
        self.ball_free_joint_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free"
        )
        self.ball_qpos_adr = self.model.jnt_qposadr[self.ball_free_joint_id]
        self.ball_qvel_adr = self.model.jnt_dofadr[self.ball_free_joint_id]

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(2,), dtype=np.float32)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(13,), dtype=np.float32)

        self._reset_episode_state()

    def _reset_episode_state(self) -> None:
        self._step_count = 0
        self._done = False
        self._held_swing: float | None = None
        self._held_tilt: float | None = None
        self._course: str = self.default_course
        self._target = COURSES[self.default_course].copy()
        self._planned_arrival: float | None = None

        self._phase = "pitch"  # "pitch" -> "bat_contact" -> "batted_ball" -> "done"
        self._contact_occurred = False
        self._first_contact_time: float | None = None
        self._first_contact_bat_vel: np.ndarray | None = None
        self._first_contact_ball_vel: np.ndarray | None = None
        self._first_contact_ball_pos: np.ndarray | None = None
        self._last_contact_time: float | None = None
        self._recontact_count = 0
        self._prolonged_contact = False

        self._candidate_exit_time: float | None = None
        self._candidate_exit_vel: np.ndarray | None = None
        self._candidate_exit_pos: np.ndarray | None = None
        self._exit_time: float | None = None
        self._exit_velocity: np.ndarray | None = None
        self._exit_pos: np.ndarray | None = None

        self._prev_ball_x: float | None = None
        self._prev_ball_y: float | None = None
        self._gate_crossing_xyz: np.ndarray | None = None
        self._gate_crossing_time: float | None = None
        self._forward_flight_success = False

        self._first_landing_xyz: np.ndarray | None = None
        self._end_reason: str | None = None
        self._prev_contact_obs = 0.0

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        options = options or {}
        course = options.get("course", self.default_course)
        if course not in COURSES:
            raise ValueError(f"unknown course {course!r}; must be one of {sorted(COURSES)}")

        mujoco.mj_resetData(self.model, self.data)
        self._reset_episode_state()
        self._course = course
        self._target = COURSES[course].copy()

        flight_time = (self.RELEASE[0] - self._target[0]) / self.HORIZONTAL_SPEED
        self._planned_arrival = float(flight_time)
        gravity = np.array(self.model.opt.gravity, dtype=float)
        ball_vel = (self._target - self.RELEASE - 0.5 * gravity * flight_time**2) / flight_time
        self._launch_speed_total = float(np.linalg.norm(ball_vel))
        self._launch_speed_horizontal = float(np.linalg.norm(ball_vel[:2]))

        self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 3] = self.RELEASE
        self.data.qpos[self.ball_qpos_adr + 3 : self.ball_qpos_adr + 7] = [1.0, 0.0, 0.0, 0.0]
        self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3] = ball_vel
        self.data.qvel[self.ball_qvel_adr + 3 : self.ball_qvel_adr + 6] = [0.0, 0.0, 0.0]
        self.data.qpos[self.swing_qpos_adr] = self.prep_swing
        self.data.qvel[self.swing_qvel_adr] = 0.0
        self.data.qpos[self.tilt_qpos_adr] = self.prep_tilt
        self.data.qvel[self.tilt_qvel_adr] = 0.0

        mujoco.mj_forward(self.model, self.data)
        self._check_no_initial_penetration()
        self._prev_ball_x = float(self.data.xpos[self.ball_body_id][0])
        self._prev_ball_y = float(self.data.xpos[self.ball_body_id][1])
        obs = self._get_obs()
        scoring = self._compute_scoring()
        no_control_cost = {"outcome": 0.0, "control_cost": 0.0}
        return obs, self._info(reward_terms={}, scoring=scoring, forward_carry_reward_terms=no_control_cost)

    def _check_no_initial_penetration(self) -> None:
        min_dist = min((float(c.dist) for c in self.data.contact), default=0.0)
        if min_dist < -1e-6:
            bad = [
                (
                    mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, c.geom1),
                    mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, c.geom2),
                    float(c.dist),
                )
                for c in self.data.contact
                if c.dist < -1e-6
            ]
            raise RuntimeError(f"reset() produced an initial penetration: {bad}")

    def set_held_pose(self, swing: float | None, tilt: float | None) -> None:
        """held_rest diagnostic, exact at physics-substep resolution (both
        axes). Pass (None, None) to release."""
        self._held_swing = swing
        self._held_tilt = tilt
        if swing is not None:
            self.data.qpos[self.swing_qpos_adr] = swing
            self.data.qvel[self.swing_qvel_adr] = 0.0
        if tilt is not None:
            self.data.qpos[self.tilt_qpos_adr] = tilt
            self.data.qvel[self.tilt_qvel_adr] = 0.0
        if swing is not None or tilt is not None:
            mujoco.mj_forward(self.model, self.data)

    def batter_feet_in_box(self) -> bool:
        box_pos = self.model.geom_pos[self.batter_box_geom_id]
        box_half = self.model.geom_size[self.batter_box_geom_id]
        foot = self.model.body_pos[self.batter_body_id]
        return bool(
            abs(foot[0] - box_pos[0]) <= box_half[0] and abs(foot[1] - box_pos[1]) <= box_half[1]
        )

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._done:
            raise RuntimeError(
                "step() called after the episode already terminated/truncated; call reset()."
            )

        action = np.asarray(action, dtype=np.float32)
        swing_ctrl = float(np.clip(action[0], -1.0, 1.0)) if self._held_swing is None else 0.0
        tilt_ctrl = float(np.clip(action[1], -1.0, 1.0)) if self._held_tilt is None else 0.0
        self.data.ctrl[0] = swing_ctrl
        self.data.ctrl[1] = tilt_ctrl

        end_reason: str | None = None
        substeps_run = 0
        this_step_had_bat_contact = False

        for _ in range(self.frame_skip):
            mujoco.mj_step(self.model, self.data)
            substeps_run += 1

            if self._held_swing is not None:
                self.data.qpos[self.swing_qpos_adr] = self._held_swing
                self.data.qvel[self.swing_qvel_adr] = 0.0
            if self._held_tilt is not None:
                self.data.qpos[self.tilt_qpos_adr] = self._held_tilt
                self.data.qvel[self.tilt_qvel_adr] = 0.0

            # I-07a-1 item A fix (kept): refresh xpos/contact from the just-
            # integrated qpos so every check below matches d.time.
            mujoco.mj_forward(self.model, self.data)

            now = float(self.data.time)
            ball_pos = self.data.xpos[self.ball_body_id].copy()
            ball_vel = self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3].copy()
            ground_now = self._detect_ground_contact()
            bat_hit, bat_vel_at_contact, ball_vel_at_contact = self._detect_bat_contact()

            if bat_hit:
                this_step_had_bat_contact = True
                self._last_contact_time = now
                if not self._contact_occurred:
                    self._contact_occurred = True
                    self._first_contact_time = now
                    self._first_contact_bat_vel = bat_vel_at_contact
                    self._first_contact_ball_vel = ball_vel_at_contact
                    self._first_contact_ball_pos = ball_pos.copy()
                    self._phase = "bat_contact"
                elif self._phase == "batted_ball":
                    self._recontact_count += 1
                    self._phase = "bat_contact"
                self._candidate_exit_time = None
                self._candidate_exit_vel = None
                self._candidate_exit_pos = None
                if (
                    not self._prolonged_contact
                    and self._first_contact_time is not None
                    and now - self._first_contact_time > PROLONGED_CONTACT_S
                ):
                    self._prolonged_contact = True

            if self._phase == "pitch":
                if ground_now:
                    end_reason = END_GROUND_BEFORE_BAT_CONTACT
                    break
                if self._ball_has_passed(ball_pos[0]):
                    end_reason = END_NO_PITCH_CONTACT
                    break
            elif self._phase == "bat_contact":
                if not bat_hit:
                    if self._candidate_exit_time is None:
                        self._candidate_exit_time = now
                        self._candidate_exit_vel = ball_vel.copy()
                        self._candidate_exit_pos = ball_pos.copy()
                    if now - self._candidate_exit_time >= SEPARATION_CONFIRM_S:
                        self._phase = "batted_ball"
                        self._exit_time = self._candidate_exit_time
                        self._exit_velocity = self._candidate_exit_vel
                        self._exit_pos = self._candidate_exit_pos
                if ground_now:
                    end_reason = END_GROUND_BEFORE_SEPARATION
                    break
            elif self._phase == "batted_ball":
                # Forward-gate crossing: only detect the ball moving in +x
                # through x=5 (a pitch crossing x=5 while still incoming is
                # moving in -x, so it can never trigger this; no separate
                # "exclude the pitch" check is needed).
                if (
                    self._gate_crossing_xyz is None
                    and self._prev_ball_x is not None
                    and self._prev_ball_x < FORWARD_GATE_X <= ball_pos[0]
                ):
                    span = ball_pos[0] - self._prev_ball_x
                    t = 0.0 if span <= 0 else (FORWARD_GATE_X - self._prev_ball_x) / span
                    cross_y = self._prev_ball_y + t * (ball_pos[1] - self._prev_ball_y)
                    self._gate_crossing_xyz = np.array([FORWARD_GATE_X, cross_y, np.nan])
                    self._gate_crossing_time = now
                    if abs(cross_y) <= FORWARD_GATE_X:
                        self._forward_flight_success = True
                if ground_now:
                    self._first_landing_xyz = ball_pos.copy()
                    end_reason = END_BATTED_BALL_LANDING
                    break
                if abs(ball_pos[0]) > OUT_OF_BOUNDS_XY or abs(ball_pos[1]) > OUT_OF_BOUNDS_XY:
                    end_reason = END_OUT_OF_BOUNDS
                    break

            self._prev_ball_x = float(ball_pos[0])
            self._prev_ball_y = float(ball_pos[1])

        self._step_count += 1
        actual_substep_duration = substeps_run * self.model.opt.timestep

        if end_reason is None:
            if self._phase == "pitch" and self._step_count >= self.max_pitch_steps:
                end_reason = END_TIMEOUT_PITCH
            elif self._phase != "pitch" and self._first_contact_time is not None:
                elapsed_flight = float(self.data.time) - self._first_contact_time
                if elapsed_flight >= self.flight_timeout_s:
                    end_reason = END_TIMEOUT_FLIGHT

        if end_reason is not None:
            self._end_reason = end_reason

        terminated = end_reason in (
            END_NO_PITCH_CONTACT,
            END_GROUND_BEFORE_BAT_CONTACT,
            END_GROUND_BEFORE_SEPARATION,
            END_BATTED_BALL_LANDING,
            END_OUT_OF_BOUNDS,
        )
        truncated = end_reason in (END_TIMEOUT_PITCH, END_TIMEOUT_FLIGHT)
        self._done = terminated or truncated

        reward, reward_terms, scoring, forward_carry_reward_terms = self._reward(
            swing_ctrl, tilt_ctrl, end_reason, actual_substep_duration
        )
        obs = self._get_obs()
        self._prev_contact_obs = float(this_step_had_bat_contact)

        if self.render_mode == "human":
            self.render()

        info = self._info(reward_terms, scoring, forward_carry_reward_terms)
        return obs, reward, terminated, truncated, info

    def render(self, camera: str = "park_wide") -> np.ndarray | None:
        if self.render_mode is None:
            return None
        if self.render_mode == "human":
            return None
        return self.render_rgb(camera)

    def render_rgb(self, camera: str = "park_wide") -> np.ndarray:
        if camera not in self._renderer:
            self._renderer[camera] = mujoco.Renderer(self.model, width=960, height=540)
        renderer = self._renderer[camera]
        renderer.update_scene(self.data, camera=camera)
        return renderer.render()

    def close(self) -> None:
        for renderer in self._renderer.values():
            renderer.close()
        self._renderer = {}

    def _get_obs(self) -> np.ndarray:
        ball_pos = self.data.xpos[self.ball_body_id].copy()
        ball_vel = self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3].copy()
        swing_angle = float(self.data.qpos[self.swing_qpos_adr])
        swing_vel = float(self.data.qvel[self.swing_qvel_adr])
        tilt_angle = float(self.data.qpos[self.tilt_qpos_adr])
        tilt_vel = float(self.data.qvel[self.tilt_qvel_adr])
        predicted_time_to_target = self._predicted_time_to_target(ball_pos, ball_vel)
        obs = np.array(
            [
                *ball_pos,
                *ball_vel,
                swing_angle,
                swing_vel,
                tilt_angle,
                tilt_vel,
                predicted_time_to_target,
                self._prev_contact_obs,
                float(self._step_count) / max(self.max_pitch_steps, 1),
            ],
            dtype=np.float32,
        )
        return obs

    def _compute_scoring(self) -> dict[str, Any]:
        """I-07c-score (docs/design/BATTING-QUALITY-AND-SWING.md section 1).
        Pure function of already-recorded episode state (self._end_reason
        and the contact/landing bookkeeping populated in step()) -- reads
        no mutable physics state itself, so it is safe to call from both
        _reward() and _info() on the same step without side effects."""
        end_reason = self._end_reason
        landing_xy = (
            self._first_landing_xyz[:2].copy() if self._first_landing_xyz is not None else None
        )

        carry_distance_m = None
        if landing_xy is not None and self._first_contact_ball_pos is not None:
            carry_distance_m = float(
                np.linalg.norm(landing_xy - self._first_contact_ball_pos[:2])
            )

        landing_range_from_home_m = None
        if landing_xy is not None:
            landing_range_from_home_m = float(np.linalg.norm(landing_xy - HOME_REFERENCE_XY))

        if end_reason is None:
            status = None
        elif end_reason in (END_TIMEOUT_PITCH, END_TIMEOUT_FLIGHT, END_OUT_OF_BOUNDS):
            # Landing was never observed (truncated or flew past the safety
            # bound while still in flight) -- undetermined, not a 0-distance
            # miss. Distinct from a definite failure below.
            status = "incomplete"
        else:
            status = "complete"

        scoring_valid = False
        if (
            status == "complete"
            and landing_xy is not None
            and self._exit_velocity is not None  # confirmed clean separation
            and float(self._exit_velocity[0]) > 0.0
            and self._recontact_count == 0
            and not self._prolonged_contact
        ):
            x_rel = float(landing_xy[0] - HOME_REFERENCE_XY[0])
            y_rel = float(landing_xy[1] - HOME_REFERENCE_XY[1])
            scoring_valid = x_rel > 0.0 and abs(y_rel) <= x_rel

        if status == "complete":
            batting_score = carry_distance_m if (scoring_valid and carry_distance_m is not None) else 0.0
        else:
            batting_score = None  # incomplete or episode still in progress: undetermined

        return {
            "status": status,
            "carry_distance_m": carry_distance_m,
            "landing_range_from_home_m": landing_range_from_home_m,
            "scoring_valid": scoring_valid,
            "batting_score": batting_score,
        }

    def _reward(
        self,
        swing_ctrl: float,
        tilt_ctrl: float,
        end_reason: str | None,
        actual_substep_duration_s: float,
    ) -> tuple[float, dict[str, float], dict[str, Any], dict[str, float]]:
        weights = self.reward_weights
        success = float(
            end_reason is not None and self._forward_flight_success and end_reason != END_TIMEOUT_FLIGHT
        )
        miss = float(
            end_reason
            in (
                END_NO_PITCH_CONTACT,
                END_GROUND_BEFORE_BAT_CONTACT,
                END_GROUND_BEFORE_SEPARATION,
                END_BATTED_BALL_LANDING,
                END_OUT_OF_BOUNDS,
            )
            and not self._forward_flight_success
        )
        control_cost = (swing_ctrl**2 + tilt_ctrl**2) * actual_substep_duration_s

        reward_terms = {
            "forward_flight_success": weights.forward_flight_success * success,
            "control_cost": -weights.control_cost * control_cost,
            "miss": -weights.miss * miss,
        }

        scoring = self._compute_scoring()
        fc_weights = self.forward_carry_reward_weights
        if scoring["status"] == "complete":
            if scoring["scoring_valid"]:
                fc_outcome = fc_weights.outcome_scale * scoring["batting_score"]
            else:
                fc_outcome = -fc_weights.miss_penalty
        else:
            # Not done, or truncated/out-of-bounds before landing: no
            # outcome reward and no miss penalty, only the control cost
            # already spent (docs/design/BATTING-QUALITY-AND-SWING.md
            # section 1: "외부 truncation에는 outcome reward/실패 벌점을
            # 지급하지 않고 소모된 제어비용만 유지한다").
            fc_outcome = 0.0
        forward_carry_reward_terms = {
            "outcome": fc_outcome,
            "control_cost": -fc_weights.control_cost * control_cost,
        }

        if self.reward_version == "forward-carry-v1":
            active_terms = forward_carry_reward_terms
        else:
            active_terms = reward_terms
        return float(sum(active_terms.values())), reward_terms, scoring, forward_carry_reward_terms

    def _point_velocity(self, body_id: int, point: np.ndarray) -> np.ndarray:
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        mujoco.mj_jac(self.model, self.data, jacp, jacr, point, body_id)
        return jacp @ self.data.qvel

    def _detect_bat_contact(self) -> tuple[bool, np.ndarray | None, np.ndarray | None]:
        for idx in range(self.data.ncon):
            contact = self.data.contact[idx]
            if contact.dist > 0:
                continue
            geom_pair = {contact.geom1, contact.geom2}
            if self.ball_geom_id in geom_pair and self.bat_geom_id in geom_pair:
                point = np.array(contact.pos, dtype=float)
                v_ball = self._point_velocity(self.ball_body_id, point)
                v_bat = self._point_velocity(self.bat_body_id, point)
                return True, v_bat, v_ball
        return False, None, None

    def _detect_ground_contact(self) -> bool:
        for idx in range(self.data.ncon):
            contact = self.data.contact[idx]
            if contact.dist > 0:
                continue
            geom_pair = {contact.geom1, contact.geom2}
            if self.ball_geom_id in geom_pair and self.ground_geom_id in geom_pair:
                return True
        return False

    def _predicted_time_to_target(self, ball_pos: np.ndarray, ball_vel: np.ndarray) -> float:
        vx = float(ball_vel[0])
        if abs(vx) < 1e-6:
            return 10.0
        return float((self._target[0] - float(ball_pos[0])) / vx)

    def _ball_has_passed(self, ball_x: float) -> bool:
        return bool(ball_x < self.pass_x)

    def _info(
        self,
        reward_terms: dict[str, float],
        scoring: dict[str, Any] | None = None,
        forward_carry_reward_terms: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        exit_velocity = self._exit_velocity
        if exit_velocity is not None:
            exit_speed = float(np.linalg.norm(exit_velocity))
            launch_angle = float(
                math.atan2(exit_velocity[2], math.hypot(exit_velocity[0], exit_velocity[1]))
            )
            spray_angle = float(math.atan2(exit_velocity[1], exit_velocity[0]))
        else:
            exit_speed = None
            launch_angle = None
            spray_angle = None

        carry_distance_xy = None
        if self._first_landing_xyz is not None and self._exit_pos is not None:
            carry_distance_xy = float(
                np.linalg.norm(self._first_landing_xyz[:2] - self._exit_pos[:2])
            )

        bat_contact_vx = (
            float(self._first_contact_bat_vel[0]) if self._first_contact_bat_vel is not None else None
        )

        if scoring is None:
            scoring = self._compute_scoring()
        if forward_carry_reward_terms is None:
            forward_carry_reward_terms = {"outcome": 0.0, "control_cost": 0.0}
        forward_carry_reward = float(sum(forward_carry_reward_terms.values()))

        return {
            "step": self._step_count,
            "phase": self._phase,
            "end_reason": self._end_reason,
            "course": self._course,
            "target": self._target.tolist(),
            "planned_arrival_s": self._planned_arrival,
            "launch_speed_total_m_s": getattr(self, "_launch_speed_total", None),
            "launch_speed_horizontal_m_s": getattr(self, "_launch_speed_horizontal", None),
            # contact (event, not success)
            "contact_occurred": self._contact_occurred,
            "first_contact_time_s": self._first_contact_time,
            "bat_contact_vx": bat_contact_vx,
            "bat_contact_velocity": (
                self._first_contact_bat_vel.tolist() if self._first_contact_bat_vel is not None else None
            ),
            "recontact_count": self._recontact_count,
            "prolonged_contact": self._prolonged_contact,
            # separation / exit
            "separated": self._exit_velocity is not None,
            "exit_time_s": self._exit_time,
            "exit_velocity_xyz": exit_velocity.tolist() if exit_velocity is not None else None,
            "exit_speed": exit_speed,
            "launch_angle_rad": launch_angle,
            "spray_angle_rad": spray_angle,
            # outcome
            "gate_crossing_xyz": (
                self._gate_crossing_xyz.tolist() if self._gate_crossing_xyz is not None else None
            ),
            "gate_crossing_time_s": self._gate_crossing_time,
            "forward_flight_success": self._forward_flight_success,
            "first_landing_xyz": (
                self._first_landing_xyz.tolist() if self._first_landing_xyz is not None else None
            ),
            "carry_distance_xy_m": carry_distance_xy,
            "reward_terms": reward_terms,
            # I-07c-score (docs/design/BATTING-QUALITY-AND-SWING.md section
            # 1): forward-carry distance score, distinct from the exit-pos-
            # anchored carry_distance_xy_m above -- carry_distance_m is
            # anchored at the ball's position at FIRST BAT CONTACT, not at
            # the confirmed-separation exit position.
            "first_contact_ball_pos_xyz": (
                self._first_contact_ball_pos.tolist()
                if self._first_contact_ball_pos is not None
                else None
            ),
            "status": scoring["status"],  # None (in progress) | "complete" | "incomplete"
            "carry_distance_m": scoring["carry_distance_m"],
            "landing_range_from_home_m": scoring["landing_range_from_home_m"],
            "scoring_valid": scoring["scoring_valid"],
            "batting_score": scoring["batting_score"],  # None until status == "complete"
            "reward_version": self.reward_version,
            # Always computed (regardless of which version is the active
            # scalar `reward`) so batted-ball-v1 and forward-carry-v1 can be
            # compared on the same episode without a second rollout.
            "forward_carry_v1": {
                "reward_terms": forward_carry_reward_terms,
                "reward": forward_carry_reward,
            },
        }

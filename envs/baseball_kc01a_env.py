"""KC-01a (docs/design/KC-01a-TORSO-BAT-COORDINATION.md, proposed by
docs/research/BATTING-KINETIC-CHAIN.md): the same B0/B1 pitch/ball physics
and phase state machine (pitch -> bat_contact -> batted_ball -> done),
with a real, finite-inertia torso rotation (torso_yaw) added as a third
actuated DOF that the bat's swing/tilt hinges are now mounted on, instead
of a fixed/welded torso. This is a SEPARATE class/XML from BaseballB1Env
(envs/baseball_b1_env.py, unmodified by this file) -- not a subclass or a
DOF-count branch in it -- for the same reason B1 is separate from B0
(docs/implementation/REFACTOR-PLAN.md R-02: "ENV-001/B0/B1은 단계별
기준선이다... 동일 의미가 검증된 순수 유틸리티만 공유한다").

Reused unchanged from envs/baseball/reward.py: `compute_scoring` (a pure
function of already-recorded contact/landing state -- genuinely DOF-count
agnostic) and the `RewardWeights`/`ForwardCarryRewardWeights` dataclasses.
NOT reused: `compute_reward_terms`, because its control-cost term is
hardcoded to exactly two control signals (swing, tilt) -- KC-01a computes
its own (see `_reward` below), rather than changing that shared function's
signature and risking B1's frozen behavior for a KC-01a-only need.

The base is fixed this round (torso_body's own `pos` is a constant, exactly
as B1's batter_body was) -- only torso ROTATION is under test. Two-leg
ground support/weight transfer/balance is KC-01b (out of scope here, see
the research doc's staging).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

from envs.baseball.courses import COURSES, ZONE_CENTER
from envs.baseball.reward import ForwardCarryRewardWeights, RewardWeights, compute_scoring

ASSET_PATH = Path(__file__).resolve().parent / "assets" / "baseball_park_kc01a.xml"

# Terminal (terminated=True) reasons -- identical vocabulary to B1's (same
# ball/pitch/bat-contact physics; only the bat's mount differs).
END_NO_PITCH_CONTACT = "no_pitch_contact"
END_GROUND_BEFORE_BAT_CONTACT = "ground_before_bat_contact"
END_GROUND_BEFORE_SEPARATION = "ground_before_separation"
END_BATTED_BALL_LANDING = "batted_ball_landing"
END_OUT_OF_BOUNDS = "out_of_bounds"
# Truncated (truncated=True) reasons.
END_TIMEOUT_PITCH = "timeout_pitch"
END_TIMEOUT_FLIGHT = "timeout_flight"

SEPARATION_CONFIRM_S = 0.002
PROLONGED_CONTACT_S = 0.05
FORWARD_GATE_X = 5.0
OUT_OF_BOUNDS_XY = 150.0

_INCOMPLETE_END_REASONS = frozenset({END_TIMEOUT_PITCH, END_TIMEOUT_FLIGHT, END_OUT_OF_BOUNDS})
_MISS_END_REASONS = frozenset(
    {
        END_NO_PITCH_CONTACT,
        END_GROUND_BEFORE_BAT_CONTACT,
        END_GROUND_BEFORE_SEPARATION,
        END_BATTED_BALL_LANDING,
        END_OUT_OF_BOUNDS,
    }
)


class BaseballKC01aEnv(gym.Env):
    """KC-01a: BaseballB1Env's pitch/ball physics and batted-ball tracking,
    with a 3-DOF bat mount (torso_yaw, bat_hinge, bat_tilt_hinge) instead
    of B1's fixed-torso 2-DOF (bat_hinge, bat_tilt_hinge). torso_yaw is a
    real hinge with finite rotational inertia (envs/assets/
    baseball_park_kc01a.xml) -- torso rotation genuinely changes the bat's
    world-frame position/velocity and receives reaction torque from the
    bat/ball through the kinematic chain; it is not a cosmetic overlay.

    Action: [torso_ctrl, swing_ctrl, tilt_ctrl], all in [-1, 1].
    Observation (15-dim): ball_pos(3), ball_vel(3), torso_angle, torso_vel,
    swing_angle, swing_vel, tilt_angle, tilt_vel, predicted_time_to_target,
    prev_contact, normalized_step. Course identity/target/phase/exit-
    velocity are NOT in the observation (same policy as B1) -- only info
    carries them.
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
        prep_torso: float = 0.0,
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

        self.prep_torso = float(prep_torso)
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
        self.torso_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "torso_body")
        self.torso_joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "torso_yaw")
        self.swing_joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "bat_hinge")
        self.tilt_joint_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_JOINT, "bat_tilt_hinge"
        )
        self.torso_qpos_adr = self.model.jnt_qposadr[self.torso_joint_id]
        self.torso_qvel_adr = self.model.jnt_dofadr[self.torso_joint_id]
        self.swing_qpos_adr = self.model.jnt_qposadr[self.swing_joint_id]
        self.swing_qvel_adr = self.model.jnt_dofadr[self.swing_joint_id]
        self.tilt_qpos_adr = self.model.jnt_qposadr[self.tilt_joint_id]
        self.tilt_qvel_adr = self.model.jnt_dofadr[self.tilt_joint_id]
        self.ball_free_joint_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free"
        )
        self.ball_qpos_adr = self.model.jnt_qposadr[self.ball_free_joint_id]
        self.ball_qvel_adr = self.model.jnt_dofadr[self.ball_free_joint_id]

        self.torso_actuator_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, "torso_motor")
        self.swing_actuator_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, "bat_motor")
        self.tilt_actuator_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, "bat_tilt_motor"
        )

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(3,), dtype=np.float32)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(15,), dtype=np.float32)

        self._reset_episode_state()

    def _reset_episode_state(self) -> None:
        self._step_count = 0
        self._done = False
        self._held_torso: float | None = None
        self._held_swing: float | None = None
        self._held_tilt: float | None = None
        self._course: str = self.default_course
        self._target = COURSES[self.default_course].copy()
        self._planned_arrival: float | None = None

        self._phase = "pitch"
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

        # KC-01a-specific bookkeeping (docs/design/KC-01a-TORSO-BAT-
        # COORDINATION.md section 4's "필수 측정"): mechanical work/peak
        # power/torque per actuated joint, accumulated every physics
        # substep (not just once per control step) so short high-torque
        # bursts within a control step are not averaged away.
        self._joint_positive_work_j = {"torso": 0.0, "swing": 0.0, "tilt": 0.0}
        self._joint_negative_work_j = {"torso": 0.0, "swing": 0.0, "tilt": 0.0}
        self._joint_peak_abs_power_w = {"torso": 0.0, "swing": 0.0, "tilt": 0.0}
        self._joint_peak_abs_torque_nm = {"torso": 0.0, "swing": 0.0, "tilt": 0.0}

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
        self.data.qpos[self.torso_qpos_adr] = self.prep_torso
        self.data.qvel[self.torso_qvel_adr] = 0.0
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
        return obs, self._info(reward_terms={}, scoring=scoring)

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

    def set_held_pose(
        self, torso: float | None, swing: float | None, tilt: float | None
    ) -> None:
        """Diagnostic hold, exact at physics-substep resolution, for any
        subset of the 3 axes -- generalizes B1's set_held_pose(swing, tilt)
        to also lock torso (used by the "torso-locked, arm-only" comparison
        condition; docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 3).
        Pass None for an axis to leave it under actuator control."""
        self._held_torso = torso
        self._held_swing = swing
        self._held_tilt = tilt
        if torso is not None:
            self.data.qpos[self.torso_qpos_adr] = torso
            self.data.qvel[self.torso_qvel_adr] = 0.0
        if swing is not None:
            self.data.qpos[self.swing_qpos_adr] = swing
            self.data.qvel[self.swing_qvel_adr] = 0.0
        if tilt is not None:
            self.data.qpos[self.tilt_qpos_adr] = tilt
            self.data.qvel[self.tilt_qvel_adr] = 0.0
        if torso is not None or swing is not None or tilt is not None:
            mujoco.mj_forward(self.model, self.data)

    def batter_feet_in_box(self) -> bool:
        """Same check as B1's: the torso's fixed PIVOT point (torso_body's
        rest `pos`, unaffected by torso_yaw -- this round's base does not
        translate) must sit inside the batter's box."""
        box_pos = self.model.geom_pos[self.batter_box_geom_id]
        box_half = self.model.geom_size[self.batter_box_geom_id]
        foot = self.model.body_pos[self.torso_body_id]
        return bool(
            abs(foot[0] - box_pos[0]) <= box_half[0] and abs(foot[1] - box_pos[1]) <= box_half[1]
        )

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._done:
            raise RuntimeError(
                "step() called after the episode already terminated/truncated; call reset()."
            )

        action = np.asarray(action, dtype=np.float32)
        torso_ctrl = float(np.clip(action[0], -1.0, 1.0)) if self._held_torso is None else 0.0
        swing_ctrl = float(np.clip(action[1], -1.0, 1.0)) if self._held_swing is None else 0.0
        tilt_ctrl = float(np.clip(action[2], -1.0, 1.0)) if self._held_tilt is None else 0.0
        self.data.ctrl[self.torso_actuator_id] = torso_ctrl
        self.data.ctrl[self.swing_actuator_id] = swing_ctrl
        self.data.ctrl[self.tilt_actuator_id] = tilt_ctrl

        end_reason: str | None = None
        substeps_run = 0
        this_step_had_bat_contact = False

        for _ in range(self.frame_skip):
            mujoco.mj_step(self.model, self.data)
            substeps_run += 1

            if self._held_torso is not None:
                self.data.qpos[self.torso_qpos_adr] = self._held_torso
                self.data.qvel[self.torso_qvel_adr] = 0.0
            if self._held_swing is not None:
                self.data.qpos[self.swing_qpos_adr] = self._held_swing
                self.data.qvel[self.swing_qvel_adr] = 0.0
            if self._held_tilt is not None:
                self.data.qpos[self.tilt_qpos_adr] = self._held_tilt
                self.data.qvel[self.tilt_qvel_adr] = 0.0

            mujoco.mj_forward(self.model, self.data)
            self._accumulate_joint_work(substep_dt=self.model.opt.timestep)

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

        reward, reward_terms = self._reward(torso_ctrl, swing_ctrl, tilt_ctrl, end_reason, actual_substep_duration)
        obs = self._get_obs()
        self._prev_contact_obs = float(this_step_had_bat_contact)

        if self.render_mode == "human":
            self.render()

        info = self._info(reward_terms, self._compute_scoring())
        info["reward"] = reward
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
        torso_angle = float(self.data.qpos[self.torso_qpos_adr])
        torso_vel = float(self.data.qvel[self.torso_qvel_adr])
        swing_angle = float(self.data.qpos[self.swing_qpos_adr])
        swing_vel = float(self.data.qvel[self.swing_qvel_adr])
        tilt_angle = float(self.data.qpos[self.tilt_qpos_adr])
        tilt_vel = float(self.data.qvel[self.tilt_qvel_adr])
        predicted_time_to_target = self._predicted_time_to_target(ball_pos, ball_vel)
        obs = np.array(
            [
                *ball_pos,
                *ball_vel,
                torso_angle,
                torso_vel,
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
        """Reuses envs.baseball.reward.compute_scoring unchanged (R-02
        pattern) -- ball-flight scoring does not depend on how many joints
        drove the bat."""
        return compute_scoring(
            end_reason=self._end_reason,
            incomplete_end_reasons=_INCOMPLETE_END_REASONS,
            first_landing_xyz=self._first_landing_xyz,
            first_contact_ball_pos=self._first_contact_ball_pos,
            exit_velocity=self._exit_velocity,
            recontact_count=self._recontact_count,
            prolonged_contact=self._prolonged_contact,
        )

    def _reward(
        self,
        torso_ctrl: float,
        swing_ctrl: float,
        tilt_ctrl: float,
        end_reason: str | None,
        actual_substep_duration_s: float,
    ) -> tuple[float, dict[str, float]]:
        """KC-01a's own reward combination (NOT envs.baseball.reward.
        compute_reward_terms, which hardcodes a 2-control-signal cost) --
        same weights/semantics as B1's batted-ball-v1 for the outcome
        terms, but control_cost now integrates THREE squared controls.
        Only batted-ball-v1 is implemented for KC-01a (forward-carry-v1's
        per-episode score is unaffected by this and can be read from
        `_compute_scoring()`'s `batting_score` directly; a separate scalar
        reward for it was not needed for this comparison and is not
        implemented, to avoid an unused/unverified code path)."""
        weights = self.reward_weights
        success = float(
            end_reason is not None and self._forward_flight_success and end_reason != END_TIMEOUT_FLIGHT
        )
        miss = float(end_reason in _MISS_END_REASONS and not self._forward_flight_success)
        control_cost = (torso_ctrl**2 + swing_ctrl**2 + tilt_ctrl**2) * actual_substep_duration_s
        reward_terms = {
            "forward_flight_success": weights.forward_flight_success * success,
            "control_cost": -weights.control_cost * control_cost,
            "miss": -weights.miss * miss,
        }
        return float(sum(reward_terms.values())), reward_terms

    def _point_velocity(self, body_id: int, point: np.ndarray) -> np.ndarray:
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        mujoco.mj_jac(self.model, self.data, jacp, jacr, point, body_id)
        return jacp @ self.data.qvel

    def _accumulate_joint_work(self, substep_dt: float) -> None:
        """docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 4's
        required measurements: real mechanical work (torque x joint
        angular velocity, integrated), peak |power|, and peak |torque| per
        actuated joint, over actual physics substeps (not once per control
        step). `qfrc_actuator` is each DOF's actual generalized force from
        the actuator this substep (post gear ratio, i.e. joint-space
        torque) -- NOT the same thing as ctrl x gear when the motor is
        ctrllimited/saturated or when other forces act through the same
        DOF; reading it directly avoids assuming an idealized motor."""
        for name, dof_adr in (
            ("torso", self.torso_qvel_adr),
            ("swing", self.swing_qvel_adr),
            ("tilt", self.tilt_qvel_adr),
        ):
            torque = float(self.data.qfrc_actuator[dof_adr])
            omega = float(self.data.qvel[dof_adr])
            power = torque * omega
            work = power * substep_dt
            if work >= 0:
                self._joint_positive_work_j[name] += work
            else:
                self._joint_negative_work_j[name] += work
            self._joint_peak_abs_power_w[name] = max(self._joint_peak_abs_power_w[name], abs(power))
            self._joint_peak_abs_torque_nm[name] = max(self._joint_peak_abs_torque_nm[name], abs(torque))

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

        return {
            "step": self._step_count,
            "phase": self._phase,
            "end_reason": self._end_reason,
            "course": self._course,
            "target": self._target.tolist(),
            "planned_arrival_s": self._planned_arrival,
            "launch_speed_total_m_s": getattr(self, "_launch_speed_total", None),
            "launch_speed_horizontal_m_s": getattr(self, "_launch_speed_horizontal", None),
            "contact_occurred": self._contact_occurred,
            "first_contact_time_s": self._first_contact_time,
            "bat_contact_vx": bat_contact_vx,
            "bat_contact_velocity": (
                self._first_contact_bat_vel.tolist() if self._first_contact_bat_vel is not None else None
            ),
            "recontact_count": self._recontact_count,
            "prolonged_contact": self._prolonged_contact,
            "separated": self._exit_velocity is not None,
            "exit_time_s": self._exit_time,
            "exit_velocity_xyz": exit_velocity.tolist() if exit_velocity is not None else None,
            "exit_speed": exit_speed,
            "launch_angle_rad": launch_angle,
            "spray_angle_rad": spray_angle,
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
            "first_contact_ball_pos_xyz": (
                self._first_contact_ball_pos.tolist()
                if self._first_contact_ball_pos is not None
                else None
            ),
            "status": scoring["status"],
            "carry_distance_m": scoring["carry_distance_m"],
            "landing_range_from_home_m": scoring["landing_range_from_home_m"],
            "scoring_valid": scoring["scoring_valid"],
            "batting_score": scoring["batting_score"],
            "reward_version": self.reward_version,
            # KC-01a-specific: cumulative-so-far mechanical work/peak power/
            # torque per joint (docs/design/KC-01a-TORSO-BAT-COORDINATION.md
            # section 4). Positive/negative work are kept separate --
            # summing them would hide braking/absorbed work as if it never
            # happened.
            "joint_positive_work_j": dict(self._joint_positive_work_j),
            "joint_negative_work_j": dict(self._joint_negative_work_j),
            "joint_peak_abs_power_w": dict(self._joint_peak_abs_power_w),
            "joint_peak_abs_torque_nm": dict(self._joint_peak_abs_torque_nm),
        }

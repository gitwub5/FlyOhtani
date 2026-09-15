from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

ASSET_PATH = Path(__file__).resolve().parent / "assets" / "baseball_park.xml"

# Episode end reasons -- same convention as envs/fly_batter_env.py (I-03b):
# "hit", "ground_contact" and "passed_no_contact" are task terminals
# (terminated=True); "timeout" is the only external truncation
# (truncated=True). Ground contact wins if both occur in the same substep.
END_REASON_HIT = "hit"
END_REASON_GROUND_CONTACT = "ground_contact"
END_REASON_PASSED_NO_CONTACT = "passed_no_contact"
END_REASON_TIMEOUT = "timeout"


@dataclass(frozen=True)
class RewardWeights:
    """b0-contact-v1 (I-07a-1 item B): a minimal, explicit definition of the
    B0 contact-smoke task, NOT a reward reviewed or tuned for learning
    optimality. hit_success/miss/control_cost are ENV-001's reviewed values,
    kept. contact_velocity is 0 -- ENV-001's 0.25 speed bonus was never
    reviewed for this scale (ENV-002: "ENV-001의 속도 보너스를 새 스케일에
    검토 없이 복사하지 않는다") and is zeroed rather than silently copied.
    Ball/batted-ball quality and plate discipline get their own reward
    version in a later stage. Compare success (hit rate, docs/records/
    VALIDATION_LOG.md) against reward totals separately -- they are not the
    same evidence."""

    hit_success: float = 10.0
    contact_velocity: float = 0.0
    control_cost: float = 0.2
    miss: float = 3.0


class BaseballB0Env(gym.Env):
    """ENV-002 stage B0: fixed-release, fixed-location, fixed-speed straight
    pitch in a baseball park layout, with a human-scale fly batter swinging a
    simple bat on one horizontal hinge.

    Coordinate system (docs/design/ENV-002-baseball.md section 1): origin is
    home plate's back vertex, +x toward the pitcher's rubber, +y toward third
    base, +z up. The ball travels mostly in -x -- the opposite convention
    from envs/fly_batter_env.py's +x -- so nothing here hardcodes a pitch
    direction; termination/observation logic reads sign from the actual
    release-to-target vector.

    B0's pitch is fully deterministic (fixed release/target/speed per ENV-002);
    `seed`/`options` are accepted for API compatibility but do not change the
    pitch. Not a claim about the fly's actual anatomy or a real pitcher's
    mechanics -- see the class-level notes in ENV-002-baseball.md.
    """

    metadata: ClassVar[dict[str, Any]] = {
        "render_modes": ["human", "rgb_array", None],
        "render_fps": 60,
    }

    RELEASE = np.array([16.5, 0.0, 1.8])
    TARGET_PLANE_X = 0.4318
    TARGET_CENTER_Y = 0.0
    TARGET_CENTER_Z = 1.0
    HORIZONTAL_SPEED = 35.0

    def __init__(
        self,
        xml_path: str | Path = ASSET_PATH,
        render_mode: str | None = None,
        frame_skip: int = 20,  # control_dt=0.005s at the XML's physics_dt=0.00025s (see baseball_park.xml)
        episode_seconds: float = 1.2,
        reward_weights: RewardWeights | None = None,
        seed: int | None = None,
        prep_angle: float = 1.0,
        pass_margin: float = 0.25,
    ) -> None:
        super().__init__()
        self.xml_path = Path(xml_path)
        self.model = mujoco.MjModel.from_xml_path(str(self.xml_path))
        self.data = mujoco.MjData(self.model)
        self.frame_skip = frame_skip
        self.render_mode = render_mode
        self.max_steps = int(episode_seconds / (self.model.opt.timestep * frame_skip))
        self.reward_weights = reward_weights or RewardWeights()
        self._rng = np.random.default_rng(seed)
        self._renderer: dict[str, mujoco.Renderer] = {}

        self.target = np.array([self.TARGET_PLANE_X, self.TARGET_CENTER_Y, self.TARGET_CENTER_Z])
        self.pass_x = float(self.target[0] - pass_margin)  # ball travels -x: "passed" means x below this
        self.prep_angle = float(prep_angle)

        self._step_count = 0
        self._hit_step: int | None = None
        self._hit_time: float | None = None
        self._planned_arrival: float | None = None
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0
        self._end_reason: str | None = None
        self._done = False
        self._held_angle: float | None = None

        self.ball_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        self.ball_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
        self.bat_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "bat_geom")
        self.bat_body_id = int(self.model.geom_bodyid[self.bat_geom_id])
        self.ground_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ground")
        self.batter_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "batter_torso")
        self.batter_box_geom_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_GEOM, "batter_box_rh"
        )
        self.batter_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "batter_body")
        self.bat_joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "bat_hinge")
        self.bat_qpos_adr = self.model.jnt_qposadr[self.bat_joint_id]
        self.bat_qvel_adr = self.model.jnt_dofadr[self.bat_joint_id]
        self.ball_free_joint_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free"
        )
        self.ball_qpos_adr = self.model.jnt_qposadr[self.ball_free_joint_id]
        self.ball_qvel_adr = self.model.jnt_dofadr[self.ball_free_joint_id]

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(11,), dtype=np.float32)

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        mujoco.mj_resetData(self.model, self.data)
        self._step_count = 0
        self._hit_step = None
        self._hit_time = None
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0
        self._end_reason = None
        self._done = False
        self._held_angle = None

        # B0: fixed release, target, and horizontal speed (ENV-002 section 2).
        # T = (release_x - plane_x) / horizontal_speed; v0 solved from the
        # same gravity-only ballistic formula as ENV-001, computed once here
        # -- never corrected toward the target per-frame after release.
        target = np.array([self.TARGET_PLANE_X, self.TARGET_CENTER_Y, self.TARGET_CENTER_Z])
        flight_time = (self.RELEASE[0] - self.TARGET_PLANE_X) / self.HORIZONTAL_SPEED
        self._planned_arrival = float(flight_time)
        gravity = np.array(self.model.opt.gravity, dtype=float)
        ball_vel = (target - self.RELEASE - 0.5 * gravity * flight_time**2) / flight_time
        self._launch_speed_total = float(np.linalg.norm(ball_vel))
        self._launch_speed_horizontal = float(np.linalg.norm(ball_vel[:2]))

        self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 3] = self.RELEASE
        self.data.qpos[self.ball_qpos_adr + 3 : self.ball_qpos_adr + 7] = [1.0, 0.0, 0.0, 0.0]
        self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3] = ball_vel
        self.data.qvel[self.ball_qvel_adr + 3 : self.ball_qvel_adr + 6] = [0.0, 0.0, 0.0]
        self.data.qpos[self.bat_qpos_adr] = self.prep_angle
        self.data.qvel[self.bat_qvel_adr] = 0.0

        mujoco.mj_forward(self.model, self.data)
        self._check_no_initial_penetration()
        obs = self._get_obs()
        return obs, self._info(reward_terms={})

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

    def set_held_pose(self, angle: float | None) -> None:
        """held_rest diagnostic, exact at physics-substep resolution: while
        enabled, the bat hinge is re-pinned to `angle` after every mj_step
        substep inside step() (not just once per control step, unlike the
        earlier I-03b approximation for envs/fly_batter_env.py)."""
        self._held_angle = angle
        if angle is not None:
            self.data.qpos[self.bat_qpos_adr] = angle
            self.data.qvel[self.bat_qvel_adr] = 0.0
            mujoco.mj_forward(self.model, self.data)

    def batter_feet_in_box(self) -> bool:
        """ENV-002: check the batter's support point lies inside the box."""
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
        torque = float(np.clip(action[0], -1.0, 1.0)) if self._held_angle is None else 0.0
        self.data.ctrl[0] = torque

        end_reason: str | None = None
        hit_this_step = False
        hit_velocity = 0.0
        substeps_run = 0

        for _ in range(self.frame_skip):
            mujoco.mj_step(self.model, self.data)
            substeps_run += 1

            if self._held_angle is not None:
                self.data.qpos[self.bat_qpos_adr] = self._held_angle
                self.data.qvel[self.bat_qvel_adr] = 0.0

            # I-07a-1 item A: with the RK4 integrator, d.xpos/d.contact
            # immediately after mj_step() can momentarily disagree with the
            # just-integrated d.qpos/d.time during a contact transient (the
            # step where a new contact first appears) -- verified empirically
            # against a minimal model. mj_forward() here recomputes xpos and
            # collision detection from the current qpos, so every reader
            # below (contact detection, _ball_has_passed) sees state at the
            # SAME instant as d.time, not a stale RK4 sub-stage. This also
            # refreshes state after the held-pose override above.
            mujoco.mj_forward(self.model, self.data)

            ground_now = self._detect_ground_contact()
            bat_hit, bat_speed = self._detect_bat_contact()

            if ground_now:
                end_reason = END_REASON_GROUND_CONTACT
                break
            if bat_hit:
                end_reason = END_REASON_HIT
                hit_this_step = True
                hit_velocity = bat_speed
                break
            if self._ball_has_passed():
                end_reason = END_REASON_PASSED_NO_CONTACT
                break

        self._step_count += 1
        actual_substep_duration = substeps_run * self.model.opt.timestep

        if hit_this_step:
            self._hit_step = self._step_count
            self._hit_time = float(self.data.time)
            self._last_contact_velocity = hit_velocity

        timeout = end_reason is None and self._step_count >= self.max_steps
        if timeout:
            end_reason = END_REASON_TIMEOUT
        if end_reason is not None:
            self._end_reason = end_reason

        terminated = end_reason in (
            END_REASON_HIT,
            END_REASON_GROUND_CONTACT,
            END_REASON_PASSED_NO_CONTACT,
        )
        truncated = end_reason == END_REASON_TIMEOUT
        self._done = terminated or truncated

        reward, reward_terms = self._reward(torque, hit_this_step, end_reason, actual_substep_duration)
        obs = self._get_obs()
        self._prev_contact = float(hit_this_step)

        if self.render_mode == "human":
            self.render()

        return obs, reward, terminated, truncated, self._info(reward_terms)

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
        bat_angle = float(self.data.qpos[self.bat_qpos_adr])
        bat_vel = float(self.data.qvel[self.bat_qvel_adr])
        predicted_time_to_target = self._predicted_time_to_target(ball_pos, ball_vel)
        obs = np.array(
            [
                *ball_pos,
                *ball_vel,
                bat_angle,
                bat_vel,
                predicted_time_to_target,
                self._prev_contact,
                float(self._step_count) / max(self.max_steps, 1),
            ],
            dtype=np.float32,
        )
        return obs

    def _reward(
        self,
        torque: float,
        hit_this_step: bool,
        end_reason: str | None,
        actual_substep_duration_s: float,
    ) -> tuple[float, dict[str, float]]:
        weights = self.reward_weights
        hit_success = float(hit_this_step)
        contact_velocity_term = self._last_contact_velocity if hit_this_step else 0.0
        miss = float(
            end_reason
            in (END_REASON_GROUND_CONTACT, END_REASON_PASSED_NO_CONTACT, END_REASON_TIMEOUT)
        )
        control_cost = (torque * torque) * actual_substep_duration_s

        reward_terms = {
            "hit_success": weights.hit_success * hit_success,
            "contact_velocity": weights.contact_velocity * contact_velocity_term,
            "control_cost": -weights.control_cost * control_cost,
            "miss": -weights.miss * miss,
        }
        return float(sum(reward_terms.values())), reward_terms

    def _point_velocity(self, body_id: int, point: np.ndarray) -> np.ndarray:
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        mujoco.mj_jac(self.model, self.data, jacp, jacr, point, body_id)
        return jacp @ self.data.qvel

    def _detect_bat_contact(self) -> tuple[bool, float]:
        for idx in range(self.data.ncon):
            contact = self.data.contact[idx]
            if contact.dist > 0:
                continue
            geom_pair = {contact.geom1, contact.geom2}
            if self.ball_geom_id in geom_pair and self.bat_geom_id in geom_pair:
                point = np.array(contact.pos, dtype=float)
                v_ball = self._point_velocity(self.ball_body_id, point)
                v_bat = self._point_velocity(self.bat_body_id, point)
                relative_speed = float(np.linalg.norm(v_ball - v_bat))
                return True, relative_speed
        return False, 0.0

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
        return float((self.target[0] - float(ball_pos[0])) / vx)

    def _ball_has_passed(self) -> bool:
        # Ball travels -x; "passed" means it went below the boundary behind
        # home plate without contact.
        return bool(self.data.xpos[self.ball_body_id][0] < self.pass_x)

    def _info(self, reward_terms: dict[str, float]) -> dict[str, Any]:
        contact_time = self._hit_time
        planned_arrival = self._planned_arrival
        if contact_time is not None:
            signed_timing_error = contact_time - planned_arrival
            timing_error = abs(signed_timing_error)
            timing_error_missing_reason = None
        else:
            signed_timing_error = None
            timing_error = None
            timing_error_missing_reason = "no_contact"
        return {
            "step": self._step_count,
            "hit": self._hit_step is not None,
            "hit_step": self._hit_step,
            "end_reason": self._end_reason,
            "contact_time_s": contact_time,
            "planned_arrival_s": planned_arrival,
            "signed_timing_error_s": signed_timing_error,
            "timing_error": timing_error,
            "timing_error_missing_reason": timing_error_missing_reason,
            "contact_velocity_post_contact": self._last_contact_velocity,
            "launch_speed_total_m_s": getattr(self, "_launch_speed_total", None),
            "launch_speed_horizontal_m_s": getattr(self, "_launch_speed_horizontal", None),
            "reward_terms": reward_terms,
        }

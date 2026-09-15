from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

ASSET_PATH = Path(__file__).resolve().parent / "assets" / "fly_batter.xml"

# x-coordinate of the swing zone the ball is launched toward (see reset()'s `target`).
ZONE_X = 0.08

# Episode end reasons. Exactly one of these (or None, mid-episode) is reported in
# info["end_reason"]. "hit" and "ground_contact" set terminated=True;
# "passed_no_contact" and "timeout" set truncated=True.
END_REASON_HIT = "hit"
END_REASON_GROUND_CONTACT = "ground_contact"
END_REASON_PASSED_NO_CONTACT = "passed_no_contact"
END_REASON_TIMEOUT = "timeout"


@dataclass(frozen=True)
class RewardWeights:
    hit_success: float = 10.0
    contact_velocity: float = 0.25
    control_cost: float = 0.002
    miss: float = 3.0


class FlyBatterEnv(gym.Env):
    """Minimal MuJoCo ball-interception environment.

    The ball is reset to a randomized start pose and launched on a
    gravity-compensated ballistic trajectory toward a fixed target point. The
    agent controls one hinge actuator that rotates a lightweight limb.

    Rendering: `render_mode="rgb_array"` returns rendered frames via
    `mujoco.Renderer`. `render_mode="human"` does not currently open a window
    (no interactive viewer is implemented); see
    docs/implementation/WORK_PACKAGES.md I-03.
    """

    metadata: ClassVar[dict[str, Any]] = {
        "render_modes": ["human", "rgb_array", None],
        "render_fps": 60,
    }

    def __init__(
        self,
        xml_path: str | Path = ASSET_PATH,
        render_mode: str | None = None,
        frame_skip: int = 5,
        episode_seconds: float = 1.6,
        reward_weights: RewardWeights | None = None,
        seed: int | None = None,
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
        self._renderer: mujoco.Renderer | None = None

        self._step_count = 0
        self._hit_step: int | None = None
        self._hit_time: float | None = None
        self._zone_cross_time: float | None = None
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0
        self._end_reason: str | None = None
        self._prev_ball_x: float | None = None

        self.ball_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        self.ball_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
        self.limb_geom_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_GEOM, "swing_limb_geom"
        )
        self.limb_body_id = int(self.model.geom_bodyid[self.limb_geom_id])
        self.ground_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ground")
        self.swing_joint_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_JOINT, "swing_hinge"
        )
        self.swing_qpos_adr = self.model.jnt_qposadr[self.swing_joint_id]
        self.swing_qvel_adr = self.model.jnt_dofadr[self.swing_joint_id]
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
        self._zone_cross_time = None
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0
        self._end_reason = None

        options = options or {}
        ball_pos = np.array(
            [
                options.get("ball_x", -2.2),
                options.get("ball_y", float(self._rng.uniform(-0.05, 0.05))),
                options.get("ball_z", float(self._rng.uniform(0.45, 0.65))),
            ],
            dtype=float,
        )
        target = np.array([ZONE_X, 0.0, 0.52], dtype=float)
        flight_time = float(options.get("flight_time", self._rng.uniform(0.72, 0.95)))

        # Gravity-compensated ballistic launch velocity: solve
        #   target = ball_pos + v * T + 0.5 * g * T^2
        # for v, using the model's own gravity vector (not a hardcoded constant)
        # so a free (uncontrolled) flight reaches `target` at t=flight_time.
        gravity = np.array(self.model.opt.gravity, dtype=float)
        ball_vel = (target - ball_pos - 0.5 * gravity * flight_time**2) / flight_time

        self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 3] = ball_pos
        self.data.qpos[self.ball_qpos_adr + 3 : self.ball_qpos_adr + 7] = [1.0, 0.0, 0.0, 0.0]
        self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3] = ball_vel
        self.data.qvel[self.ball_qvel_adr + 3 : self.ball_qvel_adr + 6] = [0.0, 0.0, 0.0]
        self.data.qpos[self.swing_qpos_adr] = -0.75
        self.data.qvel[self.swing_qvel_adr] = 0.0

        mujoco.mj_forward(self.model, self.data)
        self._prev_ball_x = float(self.data.xpos[self.ball_body_id][0])
        obs = self._get_obs()
        return obs, self._info(reward_terms={})

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.asarray(action, dtype=np.float32)
        torque = float(np.clip(action[0], -1.0, 1.0))
        self.data.ctrl[0] = torque

        # Collect contact/crossing events at every physics substep, not just after
        # the last one, so a contact that starts and ends within this control step
        # (frame_skip > 1) is never missed.
        hit_now = False
        hit_velocity = 0.0
        hit_time_this_step: float | None = None
        ground_now = False

        for _ in range(self.frame_skip):
            mujoco.mj_step(self.model, self.data)

            ball_x = float(self.data.xpos[self.ball_body_id][0])
            if (
                self._zone_cross_time is None
                and self._prev_ball_x is not None
                and self._prev_ball_x < ZONE_X <= ball_x
            ):
                self._zone_cross_time = float(self.data.time)
            self._prev_ball_x = ball_x

            limb_hit, limb_speed = self._detect_limb_contact()
            if limb_hit and not hit_now:
                hit_now = True
                hit_velocity = limb_speed
                hit_time_this_step = float(self.data.time)

            if self._detect_ground_contact():
                ground_now = True

        self._step_count += 1

        first_hit_this_step = hit_now and self._hit_step is None
        if first_hit_this_step:
            self._hit_step = self._step_count
            self._hit_time = hit_time_this_step
            self._last_contact_velocity = hit_velocity

        end_reason: str | None = None
        if first_hit_this_step:
            end_reason = END_REASON_HIT
        elif ground_now and self._hit_step is None:
            end_reason = END_REASON_GROUND_CONTACT
        elif self._ball_has_passed() and self._hit_step is None:
            end_reason = END_REASON_PASSED_NO_CONTACT
        elif self._step_count >= self.max_steps and self._hit_step is None:
            end_reason = END_REASON_TIMEOUT
        if end_reason is not None:
            self._end_reason = end_reason

        terminated = end_reason in (END_REASON_HIT, END_REASON_GROUND_CONTACT)
        truncated = end_reason in (END_REASON_PASSED_NO_CONTACT, END_REASON_TIMEOUT)

        reward, reward_terms = self._reward(torque, first_hit_this_step, end_reason)
        obs = self._get_obs()
        self._prev_contact = float(hit_now)

        if self.render_mode == "human":
            self.render()

        return obs, reward, terminated, truncated, self._info(reward_terms)

    def render(self) -> np.ndarray | None:
        if self.render_mode is None:
            return None
        if self.render_mode == "human":
            # No interactive viewer is implemented yet (see class docstring / I-03).
            return None
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, width=960, height=540)
        self._renderer.update_scene(self.data, camera="tracking")
        return self._renderer.render()

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def _get_obs(self) -> np.ndarray:
        ball_pos = self.data.xpos[self.ball_body_id].copy()
        ball_vel = self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3].copy()
        swing_angle = float(self.data.qpos[self.swing_qpos_adr])
        swing_vel = float(self.data.qvel[self.swing_qvel_adr])
        # Predicted time until the ball reaches the swing zone's x-coordinate,
        # assuming constant velocity. This is a predictive observation feature,
        # not the post-hoc timing_error evaluation metric reported in info().
        predicted_time_to_zone = self._predicted_time_to_zone(ball_pos, ball_vel)
        obs = np.array(
            [
                *ball_pos,
                *ball_vel,
                swing_angle,
                swing_vel,
                predicted_time_to_zone,
                self._prev_contact,
                float(self._step_count) / max(self.max_steps, 1),
            ],
            dtype=np.float32,
        )
        return obs

    def _reward(
        self, torque: float, first_hit_this_step: bool, end_reason: str | None
    ) -> tuple[float, dict[str, float]]:
        weights = self.reward_weights
        hit_success = float(first_hit_this_step)
        contact_velocity_term = self._last_contact_velocity if first_hit_this_step else 0.0
        miss = float(
            end_reason
            in (END_REASON_GROUND_CONTACT, END_REASON_PASSED_NO_CONTACT, END_REASON_TIMEOUT)
        )
        control_cost = torque * torque

        reward_terms = {
            "hit_success": weights.hit_success * hit_success,
            "contact_velocity": weights.contact_velocity * contact_velocity_term,
            "control_cost": -weights.control_cost * control_cost,
            "miss": -weights.miss * miss,
        }
        return float(sum(reward_terms.values())), reward_terms

    def _point_velocity(self, body_id: int, point: np.ndarray) -> np.ndarray:
        """World-frame linear velocity of the material point `point` fixed to `body_id`."""
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        mujoco.mj_jac(self.model, self.data, jacp, jacr, point, body_id)
        return jacp @ self.data.qvel

    def _detect_limb_contact(self) -> tuple[bool, float]:
        """Return (hit, relative_speed_m_s) for a ball<->limb contact this substep.

        `relative_speed_m_s` is the norm of the relative linear velocity between
        the ball's and limb's material points at the contact location (both in
        m/s, via MuJoCo point-velocity Jacobians) -- not a mix of the ball's
        linear speed and the limb's raw hinge angular velocity (rad/s).
        """
        for idx in range(self.data.ncon):
            contact = self.data.contact[idx]
            geom_pair = {contact.geom1, contact.geom2}
            if self.ball_geom_id in geom_pair and self.limb_geom_id in geom_pair:
                point = np.array(contact.pos, dtype=float)
                v_ball = self._point_velocity(self.ball_body_id, point)
                v_limb = self._point_velocity(self.limb_body_id, point)
                relative_speed = float(np.linalg.norm(v_ball - v_limb))
                return True, relative_speed
        return False, 0.0

    def _detect_ground_contact(self) -> bool:
        for idx in range(self.data.ncon):
            contact = self.data.contact[idx]
            geom_pair = {contact.geom1, contact.geom2}
            if self.ball_geom_id in geom_pair and self.ground_geom_id in geom_pair:
                return True
        return False

    def _predicted_time_to_zone(self, ball_pos: np.ndarray, ball_vel: np.ndarray) -> float:
        vx = float(ball_vel[0])
        if abs(vx) < 1e-6:
            return 10.0
        return float((ZONE_X - float(ball_pos[0])) / vx)

    def _timing_error(self) -> tuple[float | None, str | None]:
        """Actual |hit time - zone-crossing time|, only defined when both occurred.

        Distinct from the observation's `_predicted_time_to_zone`: this is a
        post-hoc evaluation metric, not part of the per-step reward.
        """
        if self._hit_time is None:
            return None, "no_contact"
        if self._zone_cross_time is None:
            return None, "no_zone_crossing_detected"
        return abs(self._hit_time - self._zone_cross_time), None

    def _ball_has_passed(self) -> bool:
        return bool(self.data.xpos[self.ball_body_id][0] > 0.45)

    def _info(self, reward_terms: dict[str, float]) -> dict[str, Any]:
        timing_error, timing_error_missing_reason = self._timing_error()
        return {
            "step": self._step_count,
            "hit": self._hit_step is not None,
            "hit_step": self._hit_step,
            "end_reason": self._end_reason,
            "timing_error": timing_error,
            "timing_error_missing_reason": timing_error_missing_reason,
            "contact_velocity": self._last_contact_velocity,
            "reward_terms": reward_terms,
        }

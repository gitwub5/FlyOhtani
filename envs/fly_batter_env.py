from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gymnasium as gym
from gymnasium import spaces
import mujoco
import numpy as np


ASSET_PATH = Path(__file__).resolve().parent / "assets" / "fly_batter.xml"


@dataclass(frozen=True)
class RewardWeights:
    hit_success: float = 10.0
    timing_error: float = 2.0
    contact_velocity: float = 0.25
    energy_cost: float = 0.002
    miss: float = 3.0


class FlyBatterEnv(gym.Env):
    """Minimal MuJoCo ball-interception environment.

    The ball is reset to a randomized start pose and launched toward the swing
    zone. The agent controls one hinge actuator that rotates a lightweight limb.
    """

    metadata = {"render_modes": ["human", "rgb_array", None], "render_fps": 60}

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
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0

        self.ball_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        self.ball_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
        self.limb_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "swing_limb_geom")
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
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0

        options = options or {}
        ball_pos = np.array(
            [
                options.get("ball_x", -2.2),
                options.get("ball_y", float(self._rng.uniform(-0.05, 0.05))),
                options.get("ball_z", float(self._rng.uniform(0.45, 0.65))),
            ],
            dtype=float,
        )
        target = np.array([0.08, 0.0, 0.52], dtype=float)
        flight_time = float(options.get("flight_time", self._rng.uniform(0.72, 0.95)))
        ball_vel = (target - ball_pos) / flight_time

        self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 3] = ball_pos
        self.data.qpos[self.ball_qpos_adr + 3 : self.ball_qpos_adr + 7] = [1.0, 0.0, 0.0, 0.0]
        self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3] = ball_vel
        self.data.qvel[self.ball_qvel_adr + 3 : self.ball_qvel_adr + 6] = [0.0, 0.0, 0.0]
        self.data.qpos[self.swing_qpos_adr] = -0.75
        self.data.qvel[self.swing_qvel_adr] = 0.0

        mujoco.mj_forward(self.model, self.data)
        obs = self._get_obs()
        return obs, self._info(reward_terms={})

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.asarray(action, dtype=np.float32)
        torque = float(np.clip(action[0], -1.0, 1.0))
        self.data.ctrl[0] = torque

        for _ in range(self.frame_skip):
            mujoco.mj_step(self.model, self.data)

        self._step_count += 1
        contact_now, contact_velocity = self._detect_contact()
        if contact_now and self._hit_step is None:
            self._hit_step = self._step_count
            self._last_contact_velocity = contact_velocity

        reward, reward_terms = self._reward(torque, contact_now, contact_velocity)
        obs = self._get_obs()
        terminated = bool(contact_now)
        truncated = self._step_count >= self.max_steps or self._ball_has_passed()
        self._prev_contact = float(contact_now)

        if self.render_mode == "human":
            self.render()

        return obs, reward, terminated, truncated, self._info(reward_terms)

    def render(self) -> np.ndarray | None:
        if self.render_mode is None:
            return None
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, width=960, height=540)
        self._renderer.update_scene(self.data, camera="tracking")
        image = self._renderer.render()
        if self.render_mode == "rgb_array":
            return image
        return None

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def _get_obs(self) -> np.ndarray:
        ball_pos = self.data.xpos[self.ball_body_id].copy()
        ball_vel = self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3].copy()
        swing_angle = float(self.data.qpos[self.swing_qpos_adr])
        swing_vel = float(self.data.qvel[self.swing_qvel_adr])
        time_to_zone = self._time_to_swing_zone(ball_pos, ball_vel)
        obs = np.array(
            [
                *ball_pos,
                *ball_vel,
                swing_angle,
                swing_vel,
                time_to_zone,
                self._prev_contact,
                float(self._step_count) / max(self.max_steps, 1),
            ],
            dtype=np.float32,
        )
        return obs

    def _reward(
        self, torque: float, contact_now: bool, contact_velocity: float
    ) -> tuple[float, dict[str, float]]:
        weights = self.reward_weights
        timing_error = abs(self._time_to_swing_zone())
        hit_success = float(contact_now)
        contact_velocity_term = contact_velocity if contact_now else 0.0
        miss = float(self._ball_has_passed() and self._hit_step is None)
        energy_cost = torque * torque

        reward_terms = {
            "hit_success": weights.hit_success * hit_success,
            "timing_error": -weights.timing_error * timing_error,
            "contact_velocity": weights.contact_velocity * contact_velocity_term,
            "energy_cost": -weights.energy_cost * energy_cost,
            "miss": -weights.miss * miss,
        }
        return float(sum(reward_terms.values())), reward_terms

    def _detect_contact(self) -> tuple[bool, float]:
        for idx in range(self.data.ncon):
            contact = self.data.contact[idx]
            geom_pair = {contact.geom1, contact.geom2}
            if self.ball_geom_id in geom_pair and self.limb_geom_id in geom_pair:
                ball_speed = float(np.linalg.norm(self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3]))
                limb_speed = abs(float(self.data.qvel[self.swing_qvel_adr]))
                return True, ball_speed + limb_speed
        return False, 0.0

    def _time_to_swing_zone(
        self, ball_pos: np.ndarray | None = None, ball_vel: np.ndarray | None = None
    ) -> float:
        ball_pos = self.data.xpos[self.ball_body_id] if ball_pos is None else ball_pos
        ball_vel = (
            self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3]
            if ball_vel is None
            else ball_vel
        )
        zone_x = 0.08
        vx = float(ball_vel[0])
        if abs(vx) < 1e-6:
            return 10.0
        return float((zone_x - ball_pos[0]) / vx)

    def _ball_has_passed(self) -> bool:
        return bool(self.data.xpos[self.ball_body_id][0] > 0.45)

    def _info(self, reward_terms: dict[str, float]) -> dict[str, Any]:
        return {
            "step": self._step_count,
            "hit": self._hit_step is not None,
            "hit_step": self._hit_step,
            "timing_error": abs(self._time_to_swing_zone()),
            "contact_velocity": self._last_contact_velocity,
            "reward_terms": reward_terms,
        }

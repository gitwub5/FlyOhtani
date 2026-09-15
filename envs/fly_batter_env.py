from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

ASSET_PATH = Path(__file__).resolve().parent / "assets" / "fly_batter.xml"

# Episode end reasons. Exactly one of these (or None, mid-episode) is reported in
# info["end_reason"]. "hit", "ground_contact" and "passed_no_contact" are task
# terminals (terminated=True); "timeout" is the only external truncation
# (truncated=True). Per ENV-001, if ground contact and a limb hit are both
# detected within the same physics substep, ground_contact wins (conservative
# failure rule).
END_REASON_HIT = "hit"
END_REASON_GROUND_CONTACT = "ground_contact"
END_REASON_PASSED_NO_CONTACT = "passed_no_contact"
END_REASON_TIMEOUT = "timeout"


@dataclass(frozen=True)
class RewardWeights:
    hit_success: float = 10.0
    contact_velocity: float = 0.25
    control_cost: float = 0.2
    miss: float = 3.0


class FlyBatterEnv(gym.Env):
    """Minimal MuJoCo ball-interception environment (ENV-001, short-distance
    smoke task -- a regression fixture, not the target baseball environment;
    see docs/design/ENV-002-baseball.md for that).

    The ball is reset to a randomized start pose and launched on a
    gravity-compensated ballistic trajectory toward a fixed target point. The
    agent controls one hinge actuator that rotates a lightweight limb, starting
    from a "cocked back" prep angle that does not by itself intercept the ball.

    Rendering: `render_mode="rgb_array"` returns rendered frames via
    `mujoco.Renderer`. `render_mode="human"` does not currently open a window
    (no interactive viewer is implemented).
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
        episode_seconds: float = 1.0,
        reward_weights: RewardWeights | None = None,
        seed: int | None = None,
        target: tuple[float, float, float] = (0.50, 0.0, 0.52),
        pass_margin: float = 0.25,
        prep_angle: float = 0.50,
        ball_x0: float = -2.2,
        ball_y_range: tuple[float, float] = (-0.05, 0.05),
        ball_z_range: tuple[float, float] = (0.45, 0.65),
        flight_time_range: tuple[float, float] = (0.40, 0.50),
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

        # Shared task geometry config -- reset(), _get_obs(), _reward(), and
        # termination all read from these, so no coordinate is duplicated or
        # hardcoded in more than one place (ENV-001 item 3).
        self.target = np.array(target, dtype=float)
        self.pass_x = float(self.target[0] + pass_margin)
        self.prep_angle = float(prep_angle)
        self.ball_x0 = float(ball_x0)
        self.ball_y_range = ball_y_range
        self.ball_z_range = ball_z_range
        self.flight_time_range = flight_time_range

        self._step_count = 0
        self._hit_step: int | None = None
        self._hit_time: float | None = None
        self._planned_arrival: float | None = None
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0
        self._end_reason: str | None = None
        self._done = False

        self.ball_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        self.ball_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
        self.limb_geom_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_GEOM, "swing_limb_geom"
        )
        self.limb_body_id = int(self.model.geom_bodyid[self.limb_geom_id])
        self.ground_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ground")
        self.thorax_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "thorax")
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
        self._last_contact_velocity = 0.0
        self._prev_contact = 0.0
        self._end_reason = None
        self._done = False

        options = options or {}
        ball_pos = np.array(
            [
                options.get("ball_x", self.ball_x0),
                options.get("ball_y", float(self._rng.uniform(*self.ball_y_range))),
                options.get("ball_z", float(self._rng.uniform(*self.ball_z_range))),
            ],
            dtype=float,
        )
        flight_time = float(options.get("flight_time", self._rng.uniform(*self.flight_time_range)))
        self._planned_arrival = flight_time

        # Gravity-compensated ballistic launch velocity: solve
        #   target = ball_pos + v * T + 0.5 * g * T^2
        # for v, using the model's own gravity vector.
        gravity = np.array(self.model.opt.gravity, dtype=float)
        ball_vel = (self.target - ball_pos - 0.5 * gravity * flight_time**2) / flight_time

        self.data.qpos[self.ball_qpos_adr : self.ball_qpos_adr + 3] = ball_pos
        self.data.qpos[self.ball_qpos_adr + 3 : self.ball_qpos_adr + 7] = [1.0, 0.0, 0.0, 0.0]
        self.data.qvel[self.ball_qvel_adr : self.ball_qvel_adr + 3] = ball_vel
        self.data.qvel[self.ball_qvel_adr + 3 : self.ball_qvel_adr + 6] = [0.0, 0.0, 0.0]
        self.data.qpos[self.swing_qpos_adr] = self.prep_angle
        self.data.qvel[self.swing_qvel_adr] = 0.0

        mujoco.mj_forward(self.model, self.data)
        self._check_no_initial_penetration()
        obs = self._get_obs()
        return obs, self._info(reward_terms={})

    def _check_no_initial_penetration(self) -> None:
        """ENV-001 item 1: reset must never start from a penetrating state.

        Raises rather than silently continuing, since an initial penetration's
        contact-resolution impulse contaminates every downstream measurement
        (this is exactly the bug in the earlier SWING_REST_ANGLE=1.1 attempt;
        see docs/records/REVIEW_2026-09-16.md).
        """
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

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._done:
            raise RuntimeError(
                "step() called after the episode already terminated/truncated; call reset()."
            )

        action = np.asarray(action, dtype=np.float32)
        torque = float(np.clip(action[0], -1.0, 1.0))
        self.data.ctrl[0] = torque

        end_reason: str | None = None
        hit_this_step = False
        hit_velocity = 0.0
        substeps_run = 0

        # Stop at the FIRST terminal physics event, substep-resolution, rather
        # than always running the full frame_skip and deciding afterward
        # (ENV-001 items 4 / VALIDATION.md's substep + priority requirement).
        for _ in range(self.frame_skip):
            mujoco.mj_step(self.model, self.data)
            substeps_run += 1

            ground_now = self._detect_ground_contact()
            limb_hit, limb_speed = self._detect_limb_contact()

            if ground_now:
                end_reason = END_REASON_GROUND_CONTACT
                break
            if limb_hit:
                end_reason = END_REASON_HIT
                hit_this_step = True
                hit_velocity = limb_speed
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

    def render(self) -> np.ndarray | None:
        if self.render_mode is None:
            return None
        if self.render_mode == "human":
            # No interactive viewer is implemented yet.
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
        predicted_time_to_target = self._predicted_time_to_target(ball_pos, ball_vel)
        obs = np.array(
            [
                *ball_pos,
                *ball_vel,
                swing_angle,
                swing_vel,
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
        # Time-integrated control cost: only the real elapsed substep time of
        # THIS call, so an episode that ends early mid-frame_skip is charged
        # for the physics time that actually ran, not the full control_dt.
        control_cost = (torque * torque) * actual_substep_duration_s

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

        `relative_speed_m_s` is the post-contact-resolution relative linear
        velocity between the ball's and limb's material points at the contact
        location (m/s, via MuJoCo point-velocity Jacobians), evaluated after
        mj_step has already resolved the contact for this substep -- not a
        pre-impact velocity.
        """
        for idx in range(self.data.ncon):
            contact = self.data.contact[idx]
            if contact.dist > 0:
                continue
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
        return bool(self.data.xpos[self.ball_body_id][0] > self.pass_x)

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
            "reward_terms": reward_terms,
        }

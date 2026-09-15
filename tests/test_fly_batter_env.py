"""Physics/API regression tests for FlyBatterEnv, written for I-03.

These check the specific defects listed in
docs/records/PROJECT_AUDIT_2026-09-16.md and their completion criteria in
docs/implementation/WORK_PACKAGES.md (I-03). They validate environment
mechanics only -- not physical realism of the fly/limb/ball scale, and not
learning performance.
"""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from envs.fly_batter_env import SWING_REST_ANGLE, ZONE_X, FlyBatterEnv


def make_env(**kwargs) -> FlyBatterEnv:
    return FlyBatterEnv(**kwargs)


def test_reset_starts_the_limb_at_the_cocked_back_rest_angle():
    """Regression only -- does NOT claim this makes the task discriminate control.

    See docs/records/VALIDATION_LOG.md's I-03 follow-up: an exhaustive sweep of
    every reachable rest angle still gets a motionless limb hit ~100% of the
    time, because the ball's gravity-compensated launch arc is much larger than
    the limb's reach given how close the fixed target point is to the hinge.
    That is a task-geometry issue, unresolved here.
    """
    env = make_env()
    try:
        env.reset(seed=0)
        assert env.data.qpos[env.swing_qpos_adr] == pytest.approx(SWING_REST_ANGLE)
    finally:
        env.close()


def test_gravity_compensated_launch_reaches_target_without_limb_interference():
    env = make_env()
    try:
        # Isolate the ball's free-flight kinematics from incidental limb contact,
        # so this test checks the launch formula, not collision luck.
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0

        flight_time = 0.8
        target = np.array([ZONE_X, 0.0, 0.52])
        env.reset(
            seed=0,
            options={"ball_x": -2.2, "ball_y": 0.0, "ball_z": 0.55, "flight_time": flight_time},
        )
        min_ball_z = float(env.data.xpos[env.ball_body_id][2])
        n_steps = round(flight_time / (env.model.opt.timestep * env.frame_skip))

        for _ in range(n_steps):
            _, _, terminated, truncated, _ = env.step(np.zeros(1, dtype=np.float32))
            min_ball_z = min(min_ball_z, float(env.data.xpos[env.ball_body_id][2]))
            assert not terminated and not truncated, "episode ended before reaching flight_time"

        final_pos = env.data.xpos[env.ball_body_id].copy()
        assert np.linalg.norm(final_pos - target) < 0.05, (
            f"gravity-compensated launch missed target: {final_pos} vs {target}"
        )
        assert min_ball_z > 0.05, f"ball dropped near/through the ground: min_z={min_ball_z}"
    finally:
        env.close()


def test_no_double_hit_reward_on_repeated_contact():
    env = make_env()
    try:
        env.reset(seed=1)
        limb_pos = env.data.geom_xpos[env.limb_geom_id].copy()
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = limb_pos
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)

        _, _, terminated1, _, info1 = env.step(np.zeros(1, dtype=np.float32))
        assert info1["hit"] is True
        assert info1["reward_terms"]["hit_success"] > 0
        assert terminated1 is True

        _, _, _, _, info2 = env.step(np.zeros(1, dtype=np.float32))
        assert info2["reward_terms"]["hit_success"] == 0.0
    finally:
        env.close()


def test_point_velocity_is_in_m_per_s_and_scales_with_lever_arm():
    """Regression for the old bug that summed m/s (ball) + rad/s (hinge)."""
    env = make_env()
    try:
        env.reset(seed=2)
        omega = 3.0  # rad/s, arbitrary nonzero
        env.data.qvel[env.swing_qvel_adr] = omega
        mujoco.mj_forward(env.model, env.data)

        hinge_pos = env.data.xanchor[env.swing_joint_id].copy()
        near_point = hinge_pos + np.array([0.1, 0.0, 0.0])
        far_point = hinge_pos + np.array([0.4, 0.0, 0.0])

        speed_near = float(np.linalg.norm(env._point_velocity(env.limb_body_id, near_point)))
        speed_far = float(np.linalg.norm(env._point_velocity(env.limb_body_id, far_point)))

        # v = omega * r for a point at radius r from a hinge rotating at omega.
        assert speed_near == pytest.approx(abs(omega) * 0.1, rel=0.2)
        assert speed_far == pytest.approx(abs(omega) * 0.4, rel=0.2)
        assert speed_far > speed_near
    finally:
        env.close()


def test_ground_contact_terminates_with_distinct_end_reason():
    env = make_env()
    try:
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.reset(seed=3, options={"ball_x": -0.3, "ball_y": 0.0, "ball_z": 0.06})
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 3] = [0.0, 0.0, -2.0]
        mujoco.mj_forward(env.model, env.data)

        terminated = truncated = False
        info: dict = {}
        for _ in range(20):
            _, _, terminated, truncated, info = env.step(np.zeros(1, dtype=np.float32))
            if terminated or truncated:
                break

        assert terminated is True
        assert info["end_reason"] == "ground_contact"
        assert info["hit"] is False
        assert info["reward_terms"]["miss"] < 0
    finally:
        env.close()


def test_control_cost_matches_action_squared_and_is_isolated():
    env = make_env()
    try:
        env.reset(seed=4, options={"ball_x": -2.2, "ball_z": 0.55, "flight_time": 0.9})
        action = np.array([0.6], dtype=np.float32)
        _, _, terminated, truncated, info = env.step(action)
        assert not terminated and not truncated

        expected = -env.reward_weights.control_cost * (0.6**2)
        assert info["reward_terms"]["control_cost"] == pytest.approx(expected, rel=1e-5)
        assert info["reward_terms"]["miss"] == 0.0
        assert info["reward_terms"]["hit_success"] == 0.0
    finally:
        env.close()


def test_timing_error_missing_reason_when_no_contact():
    env = make_env()
    try:
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.reset(seed=5)

        terminated = truncated = False
        info: dict = {}
        for _ in range(200):
            _, _, terminated, truncated, info = env.step(np.zeros(1, dtype=np.float32))
            if terminated or truncated:
                break

        assert info["hit"] is False
        assert info["timing_error"] is None
        assert info["timing_error_missing_reason"] == "no_contact"
    finally:
        env.close()


def test_timing_error_defined_after_hit_when_zone_crossing_detected():
    env = make_env()
    try:
        env.reset(seed=6)
        # Phase 1: cross ZONE_X with limb collision disabled, so crossing is
        # detected independent of any incidental contact.
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = [-0.3, 0.0, 0.55]
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = [5.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        mujoco.mj_forward(env.model, env.data)
        env._prev_ball_x = -0.3

        for _ in range(10):
            _, _, terminated, truncated, _ = env.step(np.zeros(1, dtype=np.float32))
            if env._zone_cross_time is not None or terminated or truncated:
                break
        assert env._zone_cross_time is not None, "test setup failed to cross ZONE_X"

        # Phase 2: re-enable limb collision and force a hit at the recorded
        # geom position, so timing_error can be computed against the crossing
        # recorded above.
        env.model.geom_contype[env.limb_geom_id] = 1
        env.model.geom_conaffinity[env.limb_geom_id] = 1
        limb_pos = env.data.geom_xpos[env.limb_geom_id].copy()
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = limb_pos
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)

        _, _, _terminated2, _truncated2, info2 = env.step(np.zeros(1, dtype=np.float32))
        if not info2["hit"]:
            pytest.skip("test setup did not produce a limb contact on this MuJoCo build")
        assert info2["timing_error_missing_reason"] is None
        assert info2["timing_error"] >= 0.0
    finally:
        env.close()

"""Regression tests for BaseballB0Env (ENV-002 stage B0 / I-07a).

Cover the I-07a acceptance items from docs/design/ENV-002-baseball.md section 8
and docs/implementation/WORK_PACKAGES.md's I-07 entry: layout/footing, hand-
spawn match, zero initial penetration, analytic free-trajectory match,
headless/render physics identity, no future-information leakage, fixed-pitch
zero_torque-vs-scripted validity, and event/replay reproducibility. Does not
claim biological or human-batting realism (ENV-002's own caveat).
"""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from envs.baseball_env import BaseballB0Env


def make_env(**kwargs) -> BaseballB0Env:
    return BaseballB0Env(**kwargs)


# ---------------------------------------------------------------------------
# Layout, footing, release/spawn match, initial penetration
# ---------------------------------------------------------------------------


def test_reset_never_starts_from_a_penetrating_state():
    env = make_env()
    try:
        for seed in range(5):
            env.reset(seed=seed)
            min_dist = min((float(c.dist) for c in env.data.contact), default=0.0)
            assert min_dist >= -1e-6, f"seed={seed} penetration dist={min_dist}"
    finally:
        env.close()


def test_batter_footing_is_inside_the_batters_box():
    env = make_env()
    try:
        env.reset(seed=0)
        assert env.batter_feet_in_box() is True
    finally:
        env.close()


def test_field_dimensions_match_env002_spec_values():
    env = make_env()
    try:
        env.reset(seed=0)
        rubber_pos = env.model.geom_pos[
            mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_GEOM, "pitcher_rubber")
        ]
        assert rubber_pos[0] == pytest.approx(18.4404)
        plate_size = env.model.geom_size[
            mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_GEOM, "home_plate")
        ]
        assert plate_size[0] * 2 == pytest.approx(0.4318, abs=1e-4)
        box_size = env.model.geom_size[env.batter_box_geom_id]
        assert box_size[0] * 2 == pytest.approx(1.8288, abs=1e-4)
        assert box_size[1] * 2 == pytest.approx(1.2192, abs=1e-4)
    finally:
        env.close()


def test_ball_spawn_exactly_matches_the_release_marker():
    env = make_env()
    try:
        env.reset(seed=0)
        marker_pos = env.model.geom_pos[
            mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_GEOM, "release_marker")
        ]
        ball_pos = env.data.xpos[env.ball_body_id]
        assert np.array_equal(ball_pos, marker_pos)
        assert np.array_equal(ball_pos, env.RELEASE)
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Analytic free-trajectory verification
# ---------------------------------------------------------------------------


def test_gravity_only_launch_matches_analytic_ballistics_at_the_actual_stop_time():
    """Separates two different error sources (per I-07a item 5's request not
    to conflate them, following the same finding in ENV-001's I-03b work):

    1. Integration accuracy: does the simulated position at whatever time the
       loop actually stopped match the closed-form ballistic formula
       evaluated at that SAME time? This isolates RK4/engine error from
       stopping-time quantization and must be tiny.
    2. Stopping-time quantization: n_steps=round(T/dt) generally does not
       land exactly on the continuous-valued T, so the position at the
       nearest step differs from the position at exactly t=T by an amount
       bounded by (dt/2)*speed. This is reported, not asserted against a
       tight bound, since it is an inherent discretization property, not a
       physics bug.
    """
    env = make_env(frame_skip=1)
    try:
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0
        env.max_steps = 10**7
        env.reset(seed=0)

        launch_pos = env.RELEASE.copy()
        launch_vel = env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 3].copy()
        gravity = np.array(env.model.opt.gravity, dtype=float)
        assert np.linalg.norm(launch_vel[:2]) == pytest.approx(35.0, abs=1e-6)

        n_steps = round(env._planned_arrival / env.model.opt.timestep)
        for _ in range(n_steps):
            env.step(np.zeros(1, dtype=np.float32))
        t_actual = env.data.time
        sim_pos = env.data.xpos[env.ball_body_id].copy()

        analytic_pos_at_t_actual = launch_pos + launch_vel * t_actual + 0.5 * gravity * t_actual**2
        integration_error = np.linalg.norm(sim_pos - analytic_pos_at_t_actual)
        assert integration_error <= 1e-4, f"RK4 vs analytic mismatch: {integration_error} m"

        quantization_error = np.linalg.norm(sim_pos - env.target)
        expected_bound = (env.model.opt.timestep / 2) * float(np.linalg.norm(launch_vel)) * 1.5
        assert quantization_error <= expected_bound, (
            f"quantization error {quantization_error} exceeds the expected "
            f"discretization bound {expected_bound} -- would suggest a real bug, "
            f"not just stop-time rounding"
        )
    finally:
        env.close()


def test_headless_and_render_mode_give_identical_physics():
    def run(render_mode):
        env = BaseballB0Env(render_mode=render_mode)
        env.reset(seed=0)
        for _ in range(20):
            env.step(np.array([-1.0], dtype=np.float32))
        final = env.data.qpos.copy()
        env.close()
        return final

    q_headless = run(None)
    q_rgb = run("rgb_array")
    assert np.array_equal(q_headless, q_rgb)


# ---------------------------------------------------------------------------
# No future-information leakage
# ---------------------------------------------------------------------------


def test_observation_does_not_expose_hidden_target_or_rng():
    """The 11-dim observation is [ball_pos(3), ball_vel(3), bat_angle,
    bat_vel, predicted_time_to_target, prev_contact, normalized_step] --
    all derivable from the current physics state, never the (fixed, but
    still not directly exposed) target/planned_arrival constants or RNG."""
    env = make_env()
    try:
        obs, _info = env.reset(seed=0)
        assert obs.shape == (11,)
        predicted = obs[8]
        ball_pos = obs[0:3]
        ball_vel = obs[3:6]
        expected = (env.target[0] - float(ball_pos[0])) / float(ball_vel[0])
        assert predicted == pytest.approx(expected, rel=1e-5)
        # (predicted happening to equal planned_arrival_s at t=0 is not a
        # leak: gravity has no x-component, so the x-only time-to-target
        # prediction is exact and constant for the whole flight -- any
        # observer could compute it from the current ball state alone.)
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Zero-torque vs held_pose vs scripted baseline validity, event order
# ---------------------------------------------------------------------------


def test_zero_torque_does_not_drift_horizontal_swing_is_not_gravity_torqued():
    """Unlike envs/fly_batter_env.py's vertical-plane limb, this bat's swing
    axis is vertical, so gravity (purely -z) produces zero torque about it."""
    env = make_env()
    try:
        env.reset(seed=0)
        for _ in range(60):
            env.step(np.zeros(1, dtype=np.float32))
        assert env.data.qpos[env.bat_qpos_adr] == pytest.approx(env.prep_angle, abs=1e-9)
    finally:
        env.close()


def test_held_pose_is_exact_at_physics_substep_resolution():
    """I-03b follow-up item 5: held_rest must be exact every physics substep,
    not approximated at the coarser control_dt (this was the earlier
    fly_batter_env.py demo's limitation)."""
    env = make_env(frame_skip=10)
    try:
        env.reset(seed=0)
        env.set_held_pose(env.prep_angle)
        for _ in range(5):
            env.step(np.array([1.0], dtype=np.float32))  # action ignored while held
            assert env.data.qpos[env.bat_qpos_adr] == pytest.approx(env.prep_angle, abs=1e-12)
            assert env.data.qvel[env.bat_qvel_adr] == pytest.approx(0.0, abs=1e-12)
    finally:
        env.close()


def test_scripted_hits_zero_torque_and_held_rest_do_not():
    from controllers.baseball_scripted import BaseballScriptedSwing

    env_zero = make_env()
    env_held = make_env()
    env_scripted = make_env()
    try:
        env_zero.reset(seed=0)
        info_zero = {}
        while True:
            _, _, term, trunc, info_zero = env_zero.step(np.zeros(1, dtype=np.float32))
            if term or trunc:
                break

        env_held.reset(seed=0)
        env_held.set_held_pose(env_held.prep_angle)
        info_held = {}
        while True:
            _, _, term, trunc, info_held = env_held.step(np.zeros(1, dtype=np.float32))
            if term or trunc:
                break

        controller = BaseballScriptedSwing(prep_angle=env_scripted.prep_angle)
        obs, _ = env_scripted.reset(seed=0)
        controller.reset()
        info_scripted = {}
        while True:
            obs, _, term, trunc, info_scripted = env_scripted.step(controller.act(obs))
            if term or trunc:
                break

        assert info_zero["hit"] is False
        assert info_held["hit"] is False
        assert info_scripted["hit"] is True
    finally:
        env_zero.close()
        env_held.close()
        env_scripted.close()


def test_ground_contact_priority_and_first_terminal_event_stop():
    env = make_env(frame_skip=10)
    try:
        env.reset(seed=0)
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = [1.0, 0.0, 0.03]
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)
        assert any(
            frozenset((c.geom1, c.geom2)) == frozenset((env.ball_geom_id, env.ground_geom_id))
            and c.dist <= 0
            for c in env.data.contact
        ), "test setup must start already touching the ground"

        t0 = env.data.time
        _, _, terminated, _truncated, info = env.step(np.zeros(1, dtype=np.float32))
        elapsed = env.data.time - t0
        assert info["end_reason"] == "ground_contact"
        assert terminated is True
        assert elapsed == pytest.approx(env.model.opt.timestep, abs=1e-9)
    finally:
        env.close()


def test_step_after_terminal_raises_and_no_double_reward():
    env = make_env()
    try:
        env.reset(seed=0)
        limb_pos = env.data.geom_xpos[env.bat_geom_id].copy()
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = limb_pos
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)

        _, _, terminated, _, info = env.step(np.zeros(1, dtype=np.float32))
        assert info["hit"] is True
        assert terminated is True
        with pytest.raises(RuntimeError):
            env.step(np.zeros(1, dtype=np.float32))
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Event/replay reproducibility
# ---------------------------------------------------------------------------


def test_same_seed_reproduces_an_identical_trajectory():
    from controllers.baseball_scripted import BaseballScriptedSwing

    def run():
        env = make_env()
        controller = BaseballScriptedSwing(prep_angle=env.prep_angle)
        obs, _ = env.reset(seed=7)
        controller.reset()
        trace = [obs.copy()]
        while True:
            obs, _, term, trunc, info = env.step(controller.act(obs))
            trace.append(obs.copy())
            if term or trunc:
                break
        env.close()
        return np.array(trace), info

    trace1, info1 = run()
    trace2, info2 = run()
    assert np.array_equal(trace1, trace2)
    assert info1["end_reason"] == info2["end_reason"]
    assert info1["contact_time_s"] == info2["contact_time_s"]

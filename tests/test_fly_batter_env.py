"""Physics/API regression tests for FlyBatterEnv, written for I-03 / I-03b.

These check the specific defects listed in
docs/records/PROJECT_AUDIT_2026-09-16.md, docs/records/REVIEW_2026-09-16.md,
and their completion criteria in docs/design/ENV-001-interception.md /
docs/implementation/VALIDATION.md. They validate environment mechanics only --
not physical realism of the fly/limb/ball scale, and not control/learning
performance (see docs/records/VALIDATION_LOG.md for baseline measurements).
"""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from envs.fly_batter_env import FlyBatterEnv


def make_env(**kwargs) -> FlyBatterEnv:
    return FlyBatterEnv(**kwargs)


# ---------------------------------------------------------------------------
# I-03b item 1: initial penetration / connector self-collision
# ---------------------------------------------------------------------------


def test_reset_never_starts_from_a_penetrating_state():
    env = make_env()
    try:
        for seed in range(20):
            env.reset(seed=seed)
            min_dist = min((float(c.dist) for c in env.data.contact), default=0.0)
            assert min_dist >= -1e-6, f"seed={seed} penetration dist={min_dist}"
    finally:
        env.close()


def test_prep_pose_has_ground_clearance_margin():
    env = make_env()
    try:
        env.reset(seed=0)
        assert len(env.data.contact) == 0
        origin = env.data.geom_xpos[env.limb_geom_id]
        xmat = env.data.geom_xmat[env.limb_geom_id].reshape(3, 3)
        z_axis = xmat[:, 2]
        p0 = origin - 0.29 * z_axis
        p1 = origin + 0.29 * z_axis
        lowest_z = min(p0[2], p1[2]) - 0.018
        assert lowest_z >= 0.02, f"ground clearance {lowest_z} below the 0.02m margin"
    finally:
        env.close()


def test_no_ground_penetration_across_the_full_joint_range():
    """The joint range [-1.4, 0.65] was itself chosen so the limb never
    penetrates the ground; this locks that in as a regression, independent of
    the specific prep_angle."""
    env = make_env()
    try:
        env.reset(seed=0)
        lo, hi = env.model.jnt_range[env.swing_joint_id]
        for angle in np.arange(lo, hi + 1e-9, 0.05):
            env.data.qpos[env.swing_qpos_adr] = min(angle, hi)
            mujoco.mj_forward(env.model, env.data)
            origin = env.data.geom_xpos[env.limb_geom_id]
            xmat = env.data.geom_xmat[env.limb_geom_id].reshape(3, 3)
            z_axis = xmat[:, 2]
            p0 = origin - 0.29 * z_axis
            p1 = origin + 0.29 * z_axis
            lowest_z = min(p0[2], p1[2]) - 0.018
            assert lowest_z >= 0.0, f"angle={angle}: ground penetration, clearance={lowest_z}"
    finally:
        env.close()


def test_thorax_limb_connector_overlap_is_excluded_not_penetrating():
    """The hinge attachment legitimately overlaps geometrically; the XML
    explicitly excludes only this body pair, so it must never appear in
    data.contact regardless of joint angle."""
    env = make_env()
    try:
        for angle in np.arange(-1.4, 0.651, 0.2):
            env.reset(seed=0)
            env.data.qpos[env.swing_qpos_adr] = angle
            mujoco.mj_forward(env.model, env.data)
            for c in env.data.contact:
                pair = {c.geom1, c.geom2}
                assert not (
                    env.thorax_geom_id in pair and env.limb_geom_id in pair
                ), f"angle={angle}: thorax-limb contact was not excluded"
    finally:
        env.close()


# ---------------------------------------------------------------------------
# I-03b item 2: zero_torque / held_pose / actuated are distinct, actuator gear
# ---------------------------------------------------------------------------


def test_zero_torque_held_pose_and_actuated_are_three_distinct_conditions():
    """zero_torque is NOT static: gravity alone rotates the light limb toward
    its lower resting equilibrium (docs/records/REVIEW_2026-09-16.md already
    found this for the earlier geometry; confirmed again here). held_pose is
    an artificial diagnostic that stays exactly fixed by construction.
    actuated drives toward the interception zone. All three must differ."""
    env_zero = make_env()
    env_held = make_env()
    env_actuated = make_env()
    try:
        opts = {"ball_x": -100.0, "ball_z": 50.0, "flight_time": 100.0}
        env_zero.reset(seed=0, options=opts)
        env_held.reset(seed=0, options=opts)
        env_actuated.reset(seed=0, options=opts)

        for _ in range(35):  # 0.35s at control_dt=0.01s
            env_zero.step(np.zeros(1, dtype=np.float32))
            env_held.step(np.zeros(1, dtype=np.float32))
            env_held.data.qpos[env_held.swing_qpos_adr] = env_held.prep_angle
            env_held.data.qvel[env_held.swing_qvel_adr] = 0.0
            mujoco.mj_forward(env_held.model, env_held.data)
            env_actuated.step(np.array([-1.0], dtype=np.float32))

        q_zero = float(env_zero.data.qpos[env_zero.swing_qpos_adr])
        q_held = float(env_held.data.qpos[env_held.swing_qpos_adr])
        q_actuated = float(env_actuated.data.qpos[env_actuated.swing_qpos_adr])

        # zero_torque drifts substantially under gravity (a real, previously
        # undocumented-for-this-geometry finding -- it is a moving passive
        # system, not a stand-in for "no movement").
        assert abs(q_zero - env_zero.prep_angle) > 0.05, q_zero
        # held_pose stays exactly pinned by construction.
        assert q_held == pytest.approx(env_held.prep_angle)
        # actuated reaches the interception zone within the calibrated deadline.
        assert q_actuated <= -0.264 + 0.05, q_actuated
        assert len({round(q_zero, 3), round(q_held, 3), round(q_actuated, 3)}) == 3
    finally:
        env_zero.close()
        env_held.close()
        env_actuated.close()


def test_actuator_reaches_alignment_angle_within_deadline_without_ball():
    """Reproduces the ENV-001-calibration.json gear=0.08 result inside the
    committed environment (not an isolated diagnostic model copy)."""
    env = make_env()
    try:
        env.reset(seed=0, options={"ball_x": -100.0, "ball_z": 50.0, "flight_time": 100.0})
        assert len(env.data.contact) == 0
        target_angle = -0.264
        deadline_s = 0.35
        reached_at = None
        n_steps = round(1.0 / env.model.opt.timestep)
        for i in range(n_steps):
            env.data.ctrl[0] = -1.0
            mujoco.mj_step(env.model, env.data)
            q = float(env.data.qpos[env.swing_qpos_adr])
            assert np.isfinite(q)
            if q <= target_angle:
                reached_at = (i + 1) * env.model.opt.timestep
                break
        assert reached_at is not None, "never reached the alignment angle within 1.0s"
        assert reached_at <= deadline_s, reached_at
    finally:
        env.close()


# ---------------------------------------------------------------------------
# I-03b item 3: shared target/pass-boundary config, gravity-compensated launch
# ---------------------------------------------------------------------------


def test_target_and_pass_boundary_are_shared_not_hardcoded():
    env = make_env()
    try:
        env.reset(seed=0)
        assert tuple(env.target) == (0.50, 0.0, 0.52)
        assert env.pass_x == pytest.approx(0.75)
        # _ball_has_passed and _predicted_time_to_target both read env.target/pass_x
        assert env._ball_has_passed() is False
    finally:
        env.close()


def test_gravity_compensated_launch_error_does_not_worsen_when_dt_halves():
    def mean_error(dt: float, n_seeds: int = 15) -> float:
        errs = []
        for seed in range(n_seeds):
            env = FlyBatterEnv(frame_skip=1)
            env.model.opt.timestep = dt
            env.max_steps = 10**7
            env.model.geom_contype[env.limb_geom_id] = 0
            env.model.geom_conaffinity[env.limb_geom_id] = 0
            env.reset(seed=seed)
            planned_t = env._planned_arrival
            n_steps = round(planned_t / dt)
            for _ in range(n_steps):
                env.step(np.zeros(1, dtype=np.float32))
            final_pos = env.data.xpos[env.ball_body_id].copy()
            errs.append(float(np.linalg.norm(final_pos - env.target)))
            env.close()
        return float(np.mean(errs))

    err_2ms = mean_error(0.002)
    err_1ms = mean_error(0.001)
    assert err_1ms <= err_2ms + 1e-9, (err_1ms, err_2ms)
    # At the finer resolution the stopping-time quantization error shrinks
    # enough to meet the 0.01m target; at 2ms it is close but not guaranteed
    # for every seed (see docs/records/VALIDATION_LOG.md for the full sweep).
    assert err_1ms <= 0.01, err_1ms


# ---------------------------------------------------------------------------
# I-03b item 4: substep-level first-terminal-event handling, priority,
# terminated/truncated classification, nominal timing, time-integrated cost
# ---------------------------------------------------------------------------


def test_ground_and_limb_contact_in_the_same_substep_prioritizes_ground():
    env = make_env(frame_skip=5)
    try:
        env.reset(seed=0)
        env.data.qpos[env.swing_qpos_adr] = 0.6
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = [0.499, 0.0, 0.043]
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)
        dists = {
            frozenset((c.geom1, c.geom2)): c.dist
            for c in env.data.contact
        }
        ground_pair = frozenset((env.ball_geom_id, env.ground_geom_id))
        limb_pair = frozenset((env.ball_geom_id, env.limb_geom_id))
        assert dists.get(ground_pair, 1.0) <= 0 and dists.get(limb_pair, 1.0) <= 0, (
            "test setup must start with both ball-ground and ball-limb already touching"
        )

        _, _, terminated, _truncated, info = env.step(np.zeros(1, dtype=np.float32))
        assert terminated is True
        assert info["end_reason"] == "ground_contact"
        assert info["hit"] is False
    finally:
        env.close()


def test_first_terminal_event_stops_the_substep_loop_early():
    """A ground contact detected on the very first substep must end the
    control step immediately -- not run the remaining frame_skip substeps."""
    env = make_env(frame_skip=5)
    try:
        env.reset(seed=0)
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = [0.3, 0.0, 0.044]
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)
        assert any(
            frozenset((c.geom1, c.geom2)) == frozenset((env.ball_geom_id, env.ground_geom_id))
            and c.dist <= 0
            for c in env.data.contact
        ), "test setup must start already touching the ground"

        t0 = env.data.time
        _, _, _terminated, _truncated, info = env.step(np.zeros(1, dtype=np.float32))
        elapsed = env.data.time - t0
        assert info["end_reason"] == "ground_contact"
        # Only the first substep ran (physics_dt), not the full frame_skip=5.
        assert elapsed == pytest.approx(env.model.opt.timestep, abs=1e-9), elapsed
    finally:
        env.close()


def test_mid_substep_contact_within_frame_skip_is_not_missed():
    env = make_env(frame_skip=5)
    try:
        env.reset(seed=1)
        limb_pos = env.data.geom_xpos[env.limb_geom_id].copy()
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = limb_pos
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)

        _, _, terminated, _truncated, info = env.step(np.zeros(1, dtype=np.float32))
        assert info["hit"] is True
        assert terminated is True
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
        with pytest.raises(RuntimeError):
            env.step(np.zeros(1, dtype=np.float32))
    finally:
        env.close()


def test_passed_no_contact_is_terminated_not_truncated():
    env = make_env()
    try:
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.reset(seed=2)
        terminated = truncated = False
        info: dict = {}
        for _ in range(200):
            _, _, terminated, truncated, info = env.step(np.zeros(1, dtype=np.float32))
            if terminated or truncated:
                break
        assert info["end_reason"] in ("passed_no_contact", "timeout")
        if info["end_reason"] == "passed_no_contact":
            assert terminated is True
            assert truncated is False
    finally:
        env.close()


def test_timeout_is_truncated_only():
    env = make_env(episode_seconds=0.02, frame_skip=1)
    try:
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.reset(seed=0, options={"ball_x": -100.0, "ball_z": 50.0, "flight_time": 100.0})
        terminated = truncated = False
        info: dict = {}
        for _ in range(1000):
            _, _, terminated, truncated, info = env.step(np.zeros(1, dtype=np.float32))
            if terminated or truncated:
                break
        assert info["end_reason"] == "timeout"
        assert truncated is True
        assert terminated is False
    finally:
        env.close()


def test_step_after_terminal_raises_runtime_error():
    env = make_env(episode_seconds=0.02, frame_skip=1)
    try:
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.reset(seed=0, options={"ball_x": -100.0, "ball_z": 50.0, "flight_time": 100.0})
        for _ in range(1000):
            _, _, terminated, truncated, _ = env.step(np.zeros(1, dtype=np.float32))
            if terminated or truncated:
                break
        with pytest.raises(RuntimeError):
            env.step(np.zeros(1, dtype=np.float32))
    finally:
        env.close()


def test_timing_uses_planned_arrival_and_is_always_present_on_hit():
    env = make_env()
    try:
        env.reset(seed=3)
        limb_pos = env.data.geom_xpos[env.limb_geom_id].copy()
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = limb_pos
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)

        _, _, _terminated, _, info = env.step(np.zeros(1, dtype=np.float32))
        assert info["hit"] is True
        assert info["contact_time_s"] is not None
        assert info["planned_arrival_s"] == pytest.approx(env._planned_arrival)
        assert info["signed_timing_error_s"] == pytest.approx(
            info["contact_time_s"] - info["planned_arrival_s"]
        )
        assert info["timing_error"] == pytest.approx(abs(info["signed_timing_error_s"]))
        assert info["timing_error_missing_reason"] is None
    finally:
        env.close()


def test_timing_error_on_a_naturally_launched_hit_not_just_teleported_ball():
    """VALIDATION.md: don't rely solely on artificially-teleported-ball tests
    for the nominal-timing check. Uses a real reset() launch + the scripted
    controller, no white-box qpos/qvel manipulation."""
    from controllers import ScriptedSwingController

    env = make_env()
    try:
        controller = ScriptedSwingController(prep_angle=env.prep_angle)
        hit_seeds = 0
        for seed in range(10):
            obs, _ = env.reset(seed=seed)
            controller.reset()
            info: dict = {}
            while True:
                obs, _, terminated, truncated, info = env.step(controller.act(obs))
                if terminated or truncated:
                    break
            if info["hit"]:
                hit_seeds += 1
                assert info["contact_time_s"] is not None
                assert info["planned_arrival_s"] is not None
                assert info["timing_error"] == pytest.approx(
                    abs(info["contact_time_s"] - info["planned_arrival_s"])
                )
                assert info["timing_error"] < 0.5
        assert hit_seeds > 0, "scripted controller never hit across 10 real launches"
    finally:
        env.close()


def test_timing_missing_reason_when_no_contact():
    env = make_env()
    try:
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.reset(seed=4)
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


def test_control_cost_invariant_to_control_dt():
    """Same constant action over the same real elapsed time must accumulate
    the same total control cost regardless of control_dt (frame_skip)."""

    def total_cost_over(frame_skip: int, n_control_steps: int, physics_dt: float) -> float:
        env = FlyBatterEnv(frame_skip=frame_skip)
        env.model.opt.timestep = physics_dt
        env.max_steps = 10**7
        env.model.geom_contype[env.limb_geom_id] = 0
        env.model.geom_conaffinity[env.limb_geom_id] = 0
        env.reset(seed=0, options={"ball_x": -100.0, "ball_z": 50.0, "flight_time": 100.0})
        total = 0.0
        action = np.array([0.7], dtype=np.float32)
        for _ in range(n_control_steps):
            _, _, terminated, truncated, info = env.step(action)
            total += info["reward_terms"]["control_cost"]
            if terminated or truncated:
                break
        env.close()
        return total

    physics_dt = 0.001
    # control_dt = 5ms/10ms/20ms via frame_skip 5/10/20 at physics_dt=1ms,
    # each covering the same 200ms of real elapsed time.
    cost_5ms = total_cost_over(frame_skip=5, n_control_steps=40, physics_dt=physics_dt)
    cost_10ms = total_cost_over(frame_skip=10, n_control_steps=20, physics_dt=physics_dt)
    cost_20ms = total_cost_over(frame_skip=20, n_control_steps=10, physics_dt=physics_dt)

    assert cost_5ms == pytest.approx(cost_10ms, abs=1e-9)
    assert cost_5ms == pytest.approx(cost_20ms, abs=1e-9)


# ---------------------------------------------------------------------------
# I-03b item 4 (cont.): contact-point velocity precision
# ---------------------------------------------------------------------------


def test_point_velocity_matches_omega_cross_r_analytically():
    env = make_env()
    try:
        env.reset(seed=5)
        omega = 2.0  # rad/s
        env.data.qvel[env.swing_qvel_adr] = omega
        mujoco.mj_forward(env.model, env.data)

        hinge_pos = env.data.xanchor[env.swing_joint_id].copy()
        axis = env.data.xaxis[env.swing_joint_id].copy()
        r_vec = np.array([0.2, 0.0, 0.0])
        point = hinge_pos + r_vec

        v = env._point_velocity(env.limb_body_id, point)
        v_expected = omega * np.cross(axis, r_vec)

        assert np.allclose(v, v_expected, atol=1e-8), (v, v_expected)
    finally:
        env.close()


# ---------------------------------------------------------------------------
# I-03b item 5: baseline seed isolation
# ---------------------------------------------------------------------------


def test_env_rng_is_independent_of_controller_choice():
    """The same env seed must produce an identical ball launch regardless of
    which controller (and how much of its own RNG) is used afterward."""
    from controllers import ScriptedSwingController

    env_a = make_env()
    env_b = make_env()
    try:
        env_a.reset(seed=42)
        vel_a = env_a.data.qvel[env_a.ball_qvel_adr : env_a.ball_qvel_adr + 3].copy()

        env_b.reset(seed=42)
        controller = ScriptedSwingController()
        controller.reset()
        for _ in range(5):
            env_b.step(controller.act(np.zeros(11, dtype=np.float32)))
        env_b.reset(seed=42)
        vel_b = env_b.data.qvel[env_b.ball_qvel_adr : env_b.ball_qvel_adr + 3].copy()

        assert np.array_equal(vel_a, vel_b)
    finally:
        env_a.close()
        env_b.close()


def test_reset_starts_at_the_configured_prep_angle():
    env = make_env()
    try:
        env.reset(seed=0)
        assert env.data.qpos[env.swing_qpos_adr] == pytest.approx(env.prep_angle)
    finally:
        env.close()

"""Regression tests for BaseballB1Env (ENV-002 stage B1 / I-07b aiming+courses).

Covers docs/design/ENV-002-B1-courses.md's fixed spec: control-period
consistency, initial penetration across both DOFs, the 9-course grid,
reachability (oracle only, privileged), and observer-only scripted behavior.
Does not claim RL/learning performance -- none was run (out of scope).
"""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from controllers.baseball_b1 import OracleAimController, ScriptedAimController
from envs.baseball_b1_env import ALIGNMENT, COURSES, CROSSING_TIME_S, BaseballB1Env


def make_env(**kwargs) -> BaseballB1Env:
    return BaseballB1Env(**kwargs)


# ---------------------------------------------------------------------------
# Item 1: control period consistency
# ---------------------------------------------------------------------------


def test_control_period_matches_b0():
    env = make_env()
    try:
        assert env.model.opt.timestep == pytest.approx(0.00025)
        assert env.frame_skip == 20
        assert env.model.opt.timestep * env.frame_skip == pytest.approx(0.005)
        # episode_seconds default (1.2s) / control_dt -> max_steps, exactly
        assert env.max_steps == round(1.2 / (env.model.opt.timestep * env.frame_skip))
    finally:
        env.close()


def test_first_terminal_event_stops_the_substep_loop_early():
    """Same I-03b/I-07a-1 guarantee ported to B1: a ground contact on the
    first substep ends the control step immediately (elapsed == one
    physics_dt), not the full frame_skip=20 substeps."""
    env = make_env(frame_skip=20)
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = [1.0, 0.0, 0.03]
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)
        t0 = env.data.time
        _, _, terminated, _truncated, info = env.step(np.zeros(2, dtype=np.float32))
        elapsed = env.data.time - t0
        assert info["end_reason"] == "ground_contact"
        assert terminated is True
        assert elapsed == pytest.approx(env.model.opt.timestep, abs=1e-9)
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Item 2: aiming DOF -- initial penetration, joint range, batter footing
# ---------------------------------------------------------------------------


def test_reset_never_starts_from_a_penetrating_state_any_course():
    env = make_env()
    try:
        for course in COURSES:
            for seed in range(3):
                env.reset(seed=seed, options={"course": course})
                min_dist = min((float(c.dist) for c in env.data.contact), default=0.0)
                assert min_dist >= -1e-6, f"{course} seed={seed} penetration dist={min_dist}"
    finally:
        env.close()


def test_no_ground_or_torso_penetration_across_full_tilt_and_swing_range():
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        swing_lo, swing_hi = env.model.jnt_range[env.swing_joint_id]
        tilt_lo, tilt_hi = env.model.jnt_range[env.tilt_joint_id]
        for sw in np.arange(swing_lo, swing_hi + 1e-9, 0.2):
            for ti in np.arange(tilt_lo, tilt_hi + 1e-9, 0.15):
                env.data.qpos[env.swing_qpos_adr] = min(sw, swing_hi)
                env.data.qpos[env.tilt_qpos_adr] = min(ti, tilt_hi)
                mujoco.mj_forward(env.model, env.data)
                for c in env.data.contact:
                    assert c.dist >= -1e-6, f"sw={sw} ti={ti} penetration {c.dist}"
    finally:
        env.close()


def test_batter_footing_is_inside_the_batters_box():
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        assert env.batter_feet_in_box() is True
    finally:
        env.close()


def test_held_pose_is_exact_on_both_axes_at_substep_resolution():
    env = make_env(frame_skip=20)
    try:
        env.reset(seed=0, options={"course": "in_high"})
        env.set_held_pose(env.prep_swing, env.prep_tilt)
        for _ in range(5):
            env.step(np.array([1.0, 1.0], dtype=np.float32))
            assert env.data.qpos[env.swing_qpos_adr] == pytest.approx(env.prep_swing, abs=1e-12)
            assert env.data.qpos[env.tilt_qpos_adr] == pytest.approx(env.prep_tilt, abs=1e-12)
    finally:
        env.close()


def test_zero_torque_swing_static_tilt_drifts_under_gravity():
    """Same asymmetry as the swing-only B0 finding, now confirmed on B1's
    2-DOF bat: the vertical swing axis has zero gravity torque; the tilt
    axis (rotates a horizontally-extended mass) does not."""
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        for _ in range(60):
            env.step(np.zeros(2, dtype=np.float32))
        assert env.data.qpos[env.swing_qpos_adr] == pytest.approx(env.prep_swing, abs=1e-9)
        assert abs(env.data.qpos[env.tilt_qpos_adr] - env.prep_tilt) > 0.05
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Item 3: 9-course grid
# ---------------------------------------------------------------------------


def test_nine_courses_match_the_fixed_zone_definition():
    assert set(COURSES) == {
        f"{u}_{v}" for u in ("in", "mid", "out") for v in ("high", "mid", "low")
    }
    for target in COURSES.values():
        assert target[0] == pytest.approx(0.4318)  # same plate-front x as B0
        assert abs(target[1]) <= 0.2159 + 1e-9
        assert 0.65 <= target[2] <= 1.35 + 1e-9
    assert COURSES["mid_mid"][1] == pytest.approx(0.0)
    assert COURSES["mid_mid"][2] == pytest.approx(1.0)  # same target as B0


def test_release_and_horizontal_constraint_match_b0_for_every_course():
    env = make_env()
    try:
        arrivals = set()
        for course in COURSES:
            env.reset(seed=0, options={"course": course})
            assert np.array_equal(env.data.xpos[env.ball_body_id], env.RELEASE)
            # "same horizontal constraint as B0" means vx (the approach speed
            # along the pitch direction) stays -35 m/s; vy is nonzero for
            # inside/outside courses (the ball drifts sideways to reach
            # them), so the full xy-norm is NOT exactly 35 for those.
            launch_vel = env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 3]
            assert float(launch_vel[0]) == pytest.approx(-35.0, abs=1e-6)
            arrivals.add(round(env._planned_arrival, 9))
        assert len(arrivals) == 1  # same T for all courses (only y,z target vary)
    finally:
        env.close()


def test_unknown_course_is_rejected():
    env = make_env()
    try:
        with pytest.raises(ValueError):
            env.reset(seed=0, options={"course": "does_not_exist"})
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Item 4: reachability (oracle, privileged) vs scripted (observation-only)
# ---------------------------------------------------------------------------


def test_oracle_reaches_all_nine_courses():
    """Reachability diagnosis: every course is hittable within actual
    actuator limits (docs/design/ENV-002-B1-courses.md section 4/5). If this
    ever fails for a course, that means a body/actuator limitation, not a
    policy failure -- report the joint range/gear, don't just retune."""
    for course in COURSES:
        env = make_env()
        try:
            controller = OracleAimController(course, prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
            obs, _ = env.reset(seed=0, options={"course": course})
            controller.reset()
            info: dict = {}
            while True:
                obs, _, terminated, truncated, info = env.step(controller.act(obs))
                if terminated or truncated:
                    break
            assert info["hit"] is True, f"course {course} unreachable by oracle: {info['end_reason']}"
        finally:
            env.close()


def test_scripted_controller_never_reads_course_identity():
    """The observer-only controller's aim model is fit once from the public
    ALIGNMENT/COURSES tables at construction time; act() must not accept or
    use a course label -- only the observation array."""
    import inspect

    sig = inspect.signature(ScriptedAimController.act)
    assert list(sig.parameters) == ["self", "obs"]


def test_scripted_hit_rate_is_course_dependent_and_reported_per_course():
    """Regression for the measured baseline: the observer-only fit is exact
    for none of the 9 courses in general, so hit rate varies by course --
    must never be summarized as one number. See docs/records/VALIDATION_LOG.md."""
    results = {}
    for course in COURSES:
        env = make_env()
        try:
            controller = ScriptedAimController(prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
            obs, _ = env.reset(seed=0, options={"course": course})
            controller.reset()
            info: dict = {}
            while True:
                obs, _, terminated, truncated, info = env.step(controller.act(obs))
                if terminated or truncated:
                    break
            results[course] = info["hit"]
        finally:
            env.close()
    assert any(results.values()), "scripted should hit at least one course"
    assert not all(results.values()), "scripted should not hit every course (would need re-examination)"


# ---------------------------------------------------------------------------
# Reward (reused b0-contact-v1 definition)
# ---------------------------------------------------------------------------


def test_b1_reuses_b0_contact_v1_reward_definition():
    env = make_env()
    try:
        assert env.reward_weights.hit_success == 10.0
        assert env.reward_weights.contact_velocity == 0.0
        assert env.reward_weights.miss == 3.0
        assert env.reward_weights.control_cost == 0.2
    finally:
        env.close()


def test_crossing_time_table_covers_every_course():
    assert set(CROSSING_TIME_S) == set(COURSES)
    for course in COURSES:
        swing_t, tilt_t = CROSSING_TIME_S[course]
        assert 0.0 < swing_t < 0.35
        assert 0.0 <= tilt_t < 0.45
        if ALIGNMENT[course][1] == 0.0:
            assert tilt_t == 0.0

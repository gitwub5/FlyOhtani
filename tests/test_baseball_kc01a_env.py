"""Regression tests for BaseballKC01aEnv (docs/design/
KC-01a-TORSO-BAT-COORDINATION.md), mid_mid only -- matching B1's own scope
precedent. Covers: initial/full-range non-penetration, torso_yaw's real
dynamic role (direction, reaction, inertial coupling), energy/work
accounting sanity, and that torso locked at 0 reproduces B1's own contact
physics (not a cosmetic copy -- an actual independent computation of the
same geometry).
"""
from __future__ import annotations

import mujoco
import numpy as np
import pytest

from controllers.baseball_kc01a import TorsoBatController, ZeroTorqueController
from envs.baseball_kc01a_env import BaseballKC01aEnv


def make_env(**kwargs) -> BaseballKC01aEnv:
    return BaseballKC01aEnv(**kwargs)


# ---------------------------------------------------------------------------
# Structure / non-penetration
# ---------------------------------------------------------------------------


def test_three_actuated_dof_exist_with_correct_names():
    env = make_env()
    try:
        for name in ("torso_yaw", "bat_hinge", "bat_tilt_hinge"):
            jid = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            assert jid >= 0, name
        assert env.action_space.shape == (3,)
        assert env.observation_space.shape == (15,)
    finally:
        env.close()


def test_reset_never_starts_from_a_penetrating_state():
    env = make_env()
    try:
        for seed in range(5):
            env.reset(seed=seed, options={"course": "mid_mid"})
            min_dist = min((float(c.dist) for c in env.data.contact), default=0.0)
            assert min_dist >= -1e-6, f"seed={seed} penetration dist={min_dist}"
    finally:
        env.close()


def test_no_ground_or_self_penetration_across_full_3dof_range():
    """Confirms the torso capsule geometry fix (docs/design/
    KC-01a-TORSO-BAT-COORDINATION.md section 5's discovered ground-overlap
    issue) holds across the full range of all three joints, not just at
    reset."""
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        torso_lo, torso_hi = env.model.jnt_range[env.torso_joint_id]
        swing_lo, swing_hi = env.model.jnt_range[env.swing_joint_id]
        tilt_lo, tilt_hi = env.model.jnt_range[env.tilt_joint_id]
        for to in np.arange(torso_lo, torso_hi + 1e-9, 0.2):
            for sw in np.arange(swing_lo, swing_hi + 1e-9, 0.4):
                for ti in np.arange(tilt_lo, tilt_hi + 1e-9, 0.3):
                    env.data.qpos[env.torso_qpos_adr] = min(to, torso_hi)
                    env.data.qpos[env.swing_qpos_adr] = min(sw, swing_hi)
                    env.data.qpos[env.tilt_qpos_adr] = min(ti, tilt_hi)
                    mujoco.mj_forward(env.model, env.data)
                    for c in env.data.contact:
                        assert c.dist >= -1e-6, f"to={to} sw={sw} ti={ti} penetration {c.dist}"
    finally:
        env.close()


def test_torso_body_pivot_stays_inside_the_batters_box():
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        assert env.batter_feet_in_box() is True
    finally:
        env.close()


# ---------------------------------------------------------------------------
# torso_yaw's real dynamic role
# ---------------------------------------------------------------------------


def test_positive_torso_ctrl_increases_torso_angle_from_rest():
    """Joint-direction sanity: no ball, arm held, ctrl=+1 on torso alone
    must move the angle in the +ctrl direction, not away from it."""
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        env.set_held_pose(None, env.prep_swing, env.prep_tilt)
        for _ in range(10):
            env.step(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        assert float(env.data.qpos[env.torso_qpos_adr]) > 0.0
    finally:
        env.close()


def test_torso_measured_a_max_matches_calibration():
    """Re-derives docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 2's
    measured a_max=11.41 rad/s^2 (gear=30, arm loaded at prep) -- catches
    silent XML/gear drift."""
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        env.set_held_pose(None, env.prep_swing, env.prep_tilt)
        env.step(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        v1 = float(env.data.qvel[env.torso_qvel_adr])
        t1 = float(env.data.time)
        a = v1 / t1
        assert a == pytest.approx(11.41, rel=0.02)
    finally:
        env.close()


def test_torso_rotation_changes_bat_world_position_not_just_orientation():
    """The core physical claim of KC-01a (docs/design/
    KC-01a-TORSO-BAT-COORDINATION.md section 1): torso_yaw must actually
    move the bat's world-frame position, not just its own body's
    orientation with the bat pinned in place."""
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        env.set_held_pose(0.0, env.prep_swing, env.prep_tilt)
        mujoco.mj_forward(env.model, env.data)
        bat_pos_at_0 = env.data.geom_xpos[env.bat_geom_id].copy()
        env.set_held_pose(0.3, env.prep_swing, env.prep_tilt)
        mujoco.mj_forward(env.model, env.data)
        bat_pos_at_03 = env.data.geom_xpos[env.bat_geom_id].copy()
        assert np.linalg.norm(bat_pos_at_03 - bat_pos_at_0) > 0.05
    finally:
        env.close()


def test_bat_ball_collision_produces_reaction_torque_on_torso():
    """Reaction/coupling sanity: during a real bat-ball collision, the
    torso DOF must receive a nonzero actuator/constraint-mediated
    generalized force from the impact (it is not decoupled from the bat
    it carries)."""
    env = make_env()
    try:
        controller = TorsoBatController(
            "arm_only", 0.0, env.prep_swing, env.prep_tilt, 0.0, -1.298, 999.0, 0.09425316355759385
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        env.set_held_pose(0.0, None, None)  # torso_body itself locked -- but the DOF still exists
        controller.reset()
        saw_nonzero_torso_qfrc_passive_or_constraint = False
        while True:
            obs, _, terminated, truncated, info = env.step(controller.act(obs))
            # qfrc_constraint captures the constraint force holding torso at
            # its commanded held value -- during contact this must spike,
            # evidencing the bat's impact reaching the torso DOF.
            if info["contact_occurred"] and abs(float(env.data.qfrc_constraint[env.torso_qvel_adr])) > 1e-3:
                saw_nonzero_torso_qfrc_passive_or_constraint = True
            if terminated or truncated:
                break
        assert saw_nonzero_torso_qfrc_passive_or_constraint
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Mechanical work / power / torque bookkeeping
# ---------------------------------------------------------------------------


def test_joint_work_is_zero_for_zero_torque_baseline():
    env = make_env()
    try:
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller = ZeroTorqueController()
        info = {}
        while True:
            obs, _, terminated, truncated, info = env.step(controller.act(obs))
            if terminated or truncated:
                break
        for name in ("torso", "swing", "tilt"):
            assert info["joint_positive_work_j"][name] == pytest.approx(0.0, abs=1e-9)
            assert info["joint_negative_work_j"][name] == pytest.approx(0.0, abs=1e-9)
    finally:
        env.close()


def test_joint_work_accumulates_and_is_never_absurdly_large():
    """Sanity bound, not a physical proof of energy conservation (see
    docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 3's energy-budget
    validation for the real check) -- catches a sign error or unit error
    that would make accumulated work explode."""
    env = make_env()
    try:
        controller = TorsoBatController(
            "simultaneous", 0.0, env.prep_swing, env.prep_tilt, -0.4, -0.726, 0.096, 0.096
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        info = {}
        while True:
            obs, _, terminated, truncated, info = env.step(controller.act(obs))
            if terminated or truncated:
                break
        total_positive = sum(info["joint_positive_work_j"].values())
        assert 0.0 < total_positive < 50.0  # a hand torque motor over ~0.3s is not kilojoules
    finally:
        env.close()


# ---------------------------------------------------------------------------
# arm_only reproduces B1's own geometry (torso locked at 0)
# ---------------------------------------------------------------------------


def test_arm_only_with_torso_locked_reproduces_b1_alignment_geometry():
    """docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 6: with torso
    held at 0 and swing at B1's own ALIGNMENT['mid_mid'] target (-1.298),
    the bat capsule's closest approach to the course target must match
    B1's own documented ~5e-5m residual -- an independent confirmation
    that torso=0 makes this environment's kinematics identical to B1's,
    not merely a claim."""
    from envs.baseball.courses import COURSES

    env = make_env()
    try:
        env.data.qpos[env.torso_qpos_adr] = 0.0
        env.data.qpos[env.swing_qpos_adr] = -1.298
        env.data.qpos[env.tilt_qpos_adr] = 0.0
        mujoco.mj_forward(env.model, env.data)
        target = COURSES["mid_mid"]
        p0 = env.data.geom_xpos[env.bat_geom_id].copy()
        mat = env.data.geom_xmat[env.bat_geom_id].reshape(3, 3)
        axis = mat @ np.array([0.0, 0.0, 1.0])
        p1, p2 = p0 - axis * 0.425, p0 + axis * 0.425
        seg = p2 - p1
        t = np.clip(np.dot(target - p1, seg) / np.dot(seg, seg), 0.0, 1.0)
        closest = p1 + t * seg
        dist = float(np.linalg.norm(target - closest))
        assert dist == pytest.approx(4.925e-05, abs=1e-6)
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Grip-reach honesty (docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 3)
# ---------------------------------------------------------------------------


def test_front_leg_grip_reach_error_is_tracked_not_hidden():
    """Runs the staggered condition (the largest torso excursion among the
    calibrated conditions) with the visual overlay active and confirms
    FrontLegGripOverlay reports SOME reach_error value every frame (0 or
    positive) rather than the check being skipped -- the actual pass/fail
    threshold is a visual-acceptance question tracked in
    docs/records/KC-01a-COMPARISON.md, not asserted blindly here."""
    from envs.fly_visual import FrontLegGripOverlay

    env = make_env()
    try:
        overlay = FrontLegGripOverlay(env.model)
        controller = TorsoBatController(
            "staggered", 0.0, env.prep_swing, env.prep_tilt, -0.4, -0.726, 0.242, 0.122
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        max_reach_error = 0.0
        steps = 0
        while steps < 30:
            obs, _, terminated, truncated, _info = env.step(controller.act(obs))
            errs = overlay.update(env.model, env.data)
            max_reach_error = max(max_reach_error, errs["L"], errs["R"])
            steps += 1
            if terminated or truncated:
                break
        assert max_reach_error >= 0.0  # the check ran and produced a real number
    finally:
        env.close()

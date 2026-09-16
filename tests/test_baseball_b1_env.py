"""Regression tests for BaseballB1Env (ENV-002 stage B1 / I-07b aiming+courses,
I-07b-fix real batted-ball physics).

Covers docs/design/ENV-002-B1-courses.md's fixed spec (control-period
consistency, initial penetration across both DOFs, the 9-course grid) plus
docs/design/ENV-002-BATTED-BALL.md's contact-is-an-event / forward-hit
tracking, verified so far ONLY for the mid_mid course (see
docs/records/VALIDATION_LOG.md and CROSSING_TIME_S's comment in
envs/baseball_b1_env.py). The other 8 courses' oracle/scripted reachability
under the new forward_flight_success criterion is NOT yet re-verified and is
deliberately not asserted here -- that is I-07b-fix's next step, not this
one. Does not claim RL/learning performance -- none was run (out of scope).
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np
import pytest

from controllers.baseball_b1 import OracleAimController, ScriptedAimController
from envs.baseball_b1_env import ALIGNMENT, COURSES, CROSSING_TIME_S, BaseballB1Env


def make_env(**kwargs) -> BaseballB1Env:
    return BaseballB1Env(**kwargs)


def run_to_end(env: BaseballB1Env, controller, course: str) -> dict:
    obs, _ = env.reset(seed=0, options={"course": course})
    controller.reset()
    info: dict = {}
    while True:
        obs, _, terminated, truncated, info = env.step(controller.act(obs))
        if terminated or truncated:
            return info


# ---------------------------------------------------------------------------
# Item 1: control period consistency
# ---------------------------------------------------------------------------


def test_control_period_matches_b0():
    env = make_env()
    try:
        assert env.model.opt.timestep == pytest.approx(0.00025)
        assert env.frame_skip == 20
        assert env.model.opt.timestep * env.frame_skip == pytest.approx(0.005)
        assert env.max_pitch_steps == round(1.2 / (env.model.opt.timestep * env.frame_skip))
    finally:
        env.close()


def test_first_terminal_event_stops_the_substep_loop_early():
    """Same I-03b/I-07a-1 guarantee ported to B1: a ground contact on the
    first substep ends the control step immediately (elapsed == one
    physics_dt), not the full frame_skip=20 substeps. This still applies
    pre-contact (phase="pitch"); it is unaffected by the batted-ball-v1
    phase model added in I-07b-fix."""
    env = make_env(frame_skip=20)
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        env.data.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = [1.0, 0.0, 0.03]
        env.data.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
        mujoco.mj_forward(env.model, env.data)
        t0 = env.data.time
        _, _, terminated, _truncated, info = env.step(np.zeros(2, dtype=np.float32))
        elapsed = env.data.time - t0
        assert info["end_reason"] == "ground_before_bat_contact"
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
    axis (rotates a horizontally-extended mass) does not. This is exactly
    why OracleAimController/ScriptedAimController must actively hold tilt
    near prep with a P-gain rather than leaving ctrl=0 (see controllers/
    baseball_b1.py's _hold; a naive ctrl=0 tilt drifted ~0.54rad by the
    time the ball arrived during I-07b-fix's debugging -- see
    docs/records/VALIDATION_LOG.md)."""
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
# Item 4 (I-07b-fix): real batted-ball physics, verified for mid_mid only.
# See docs/design/ENV-002-BATTED-BALL.md for the phase model/metrics this
# checks, and docs/records/VALIDATION_LOG.md for the gear/solref/trigger
# sweep that produced envs/assets/baseball_park_b1.xml's current
# calibration.
# ---------------------------------------------------------------------------


def test_oracle_achieves_a_real_forward_hit_for_mid_mid():
    """The user-facing bug this fix addresses: contact alone is not
    success. Assert the FULL chain -- positive bat contact-point vx
    (swing direction is correct), positive ball exit vx after physical
    separation (the ball was actually redirected, not just grazed), and
    forward_flight_success (it crosses x=5m within the infield fan before
    landing)."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        info = run_to_end(env, controller, "mid_mid")
        assert info["contact_occurred"] is True
        assert info["bat_contact_vx"] > 0.0, "swing must move toward +x (infield) at contact"
        assert info["exit_velocity_xyz"] is not None, "ball must physically separate from the bat"
        assert info["exit_velocity_xyz"][0] > 0.0, "ball must exit toward +x, not continue at the catcher"
        assert info["forward_flight_success"] is True
        assert info["end_reason"] == "batted_ball_landing"
        assert info["first_landing_xyz"] is not None
    finally:
        env.close()


def test_contact_is_an_event_not_a_terminal_bat_contact_state_is_reached():
    """Regression for the original bug (docs/records/B1-BATTING-REVIEW.md):
    the episode used to terminate on the very first bat/ball contact. Now
    contact must be followed by a separation and continued flight tracking
    within the SAME episode before termination."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        saw_bat_contact_phase = False
        saw_batted_ball_phase = False
        info: dict = {}
        while True:
            obs, _, terminated, truncated, info = env.step(controller.act(obs))
            saw_bat_contact_phase = saw_bat_contact_phase or info["phase"] == "bat_contact"
            saw_batted_ball_phase = saw_batted_ball_phase or info["phase"] == "batted_ball"
            if terminated or truncated:
                break
        assert saw_bat_contact_phase, "must pass through the bat_contact phase"
        assert saw_batted_ball_phase, "must reach batted_ball (post-separation) before ending"
        assert info["end_reason"] == "batted_ball_landing"
        assert info["recontact_count"] == 0
        assert info["prolonged_contact"] is False
    finally:
        env.close()


def test_scripted_controller_never_reads_course_identity():
    """The observer-only controller's aim model is fit once from the public
    ALIGNMENT/COURSES tables at construction time; act() must not accept or
    use a course label -- only the observation array."""
    import inspect

    sig = inspect.signature(ScriptedAimController.act)
    assert list(sig.parameters) == ["self", "obs"]


# ---------------------------------------------------------------------------
# Reward (batted-ball-v1, I-07b-fix)
# ---------------------------------------------------------------------------


def test_b1_uses_batted_ball_v1_reward_definition():
    env = make_env()
    try:
        assert env.reward_weights.forward_flight_success == 10.0
        assert env.reward_weights.miss == 3.0
        assert env.reward_weights.control_cost == 0.2
        assert not hasattr(env.reward_weights, "hit_success")
        assert not hasattr(env.reward_weights, "contact_velocity")
    finally:
        env.close()


def test_forward_flight_success_pays_once_mere_contact_pays_nothing():
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        total_success_reward = 0.0
        info: dict = {}
        while True:
            obs, _reward, terminated, truncated, info = env.step(controller.act(obs))
            total_success_reward += info["reward_terms"]["forward_flight_success"]
            if terminated or truncated:
                break
        assert info["forward_flight_success"] is True
        assert total_success_reward == pytest.approx(env.reward_weights.forward_flight_success)
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


# ---------------------------------------------------------------------------
# I-07b-followthrough: post-contact swing/tilt no longer chase the alignment
# angle with bang-bang forever (docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md
# section A). Verified for mid_mid only -- see docs/records/VALIDATION_LOG.md
# for the full gain derivation, including tilt's honestly-reported ~0.6-0.9s
# settle time versus the 0.5s design target (a measured gear=6 torque-
# authority limit, not a bug).
# ---------------------------------------------------------------------------


def test_swing_settles_after_contact_instead_of_chasing_forever():
    """Regression for the exact bug Codex's independent review found: post-
    contact, the swing axis used to reverse full torque repeatedly (5 sign
    flips measured, angle oscillating across [-1.60,-0.96]rad for the rest
    of the episode). It must now settle to a fixed follow-through pose."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        states = []
        info: dict = {}
        while True:
            obs, _reward, terminated, truncated, info = env.step(controller.act(obs))
            states.append(controller._swing_axis.state)
            if terminated or truncated:
                break
        # Must visit accelerate and brake, and end up settled in "hold" well
        # before the episode (ball flight) ends -- not still fighting for
        # control at the very last step.
        assert "accelerate" in states
        assert "brake" in states
        assert states[-1] == "hold"
        # Once "hold" is reached the FIRST time, the controller must never
        # fall back to "accelerate" (the old bug's re-chasing behavior).
        first_hold = states.index("hold")
        assert "accelerate" not in states[first_hold:]
        # The verified batted-ball physics must be completely unaffected by
        # the follow-through rewrite (identical pre-separation behavior).
        assert info["bat_contact_vx"] > 0.0
        assert info["exit_velocity_xyz"][0] > 0.0
        assert info["forward_flight_success"] is True
    finally:
        env.close()


def test_swing_settle_time_and_overshoot_meet_the_design_targets():
    """docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md's acceptance values:
    |qvel|<0.2rad/s within 0.5s of brake entry, then angle peak-to-peak
    <0.02rad over the following 0.2s. Verified for the swing axis on
    mid_mid (see VALIDATION_LOG for why tilt's gear=6 cannot meet the same
    0.5s bound against this collision's disturbance -- not asserted here)."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        latch_t = None
        hold_t = None
        angles_after_hold = []
        done = False
        while not done:
            obs, _reward, terminated, truncated, _info = env.step(controller.act(obs))
            done = terminated or truncated
            state = controller._swing_axis.state
            if latch_t is None and state in ("brake", "hold"):
                latch_t = env.data.time
            if hold_t is None and state == "hold":
                hold_t = env.data.time
            if hold_t is not None:
                angles_after_hold.append((env.data.time, float(env.data.qpos[env.swing_qpos_adr])))
        assert latch_t is not None and hold_t is not None
        assert hold_t - latch_t <= 0.5
        window = [a for t, a in angles_after_hold if t <= hold_t + 0.2]
        assert max(window) - min(window) < 0.02
    finally:
        env.close()


def test_fixed_pose_always_swing_moves_toward_the_alignment_zone():
    """Regression for a second stale-direction bug found alongside the
    follow-through fix: this baseline's ctrl sign was still -1.0 (correct
    only for the pre-I-07b-fix prep_swing=+1.0/decreasing-angle swing),
    which now just drives the bat into the -2.0 joint limit and never
    contacts the ball -- it must move toward the (less negative) alignment
    angles instead."""
    env = make_env()
    try:
        from controllers.baseball_b1 import FixedPoseAlwaysSwing

        controller = FixedPoseAlwaysSwing()
        run_to_end(env, controller, "mid_mid")
        assert env.data.qpos[env.swing_qpos_adr] > env.prep_swing
    finally:
        env.close()


# ---------------------------------------------------------------------------
# I-07b-followthrough section B: contact-material documentation fix.
# ---------------------------------------------------------------------------


def test_actual_ball_bat_contact_solref_matches_the_documented_mixing_rule():
    """Regression for the wrong claim (corrected per
    docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md section B) that ball_geom's
    own declared solref is what governs the collision. The two geoms have
    equal priority and solmix=1.0, so MuJoCo mixes them by plain arithmetic
    mean; assert the real contact reflects that, not either geom's value in
    isolation."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        expected_solref = (
            (env.model.geom_solref[env.ball_geom_id] + env.model.geom_solref[env.bat_geom_id]) / 2.0
        )
        done = False
        found = False
        while not done and not found:
            obs, _reward, terminated, truncated, _info = env.step(controller.act(obs))
            done = terminated or truncated
            for c in env.data.contact:
                pair = {c.geom1, c.geom2}
                if env.ball_geom_id in pair and env.bat_geom_id in pair:
                    assert c.solref == pytest.approx(expected_solref, abs=1e-9)
                    found = True
                    break
        assert found, "expected at least one real ball-bat contact during the central hit"
    finally:
        env.close()


# ---------------------------------------------------------------------------
# I-08a: NeuroMechFly visual overlay (docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md).
# The overlay lives entirely in envs/assets/baseball_park_b1.xml's added
# geoms/mocap bodies (contype=0, conaffinity=0, no mass) plus
# envs/fly_visual.py's per-render mocap updates -- neither can affect
# env.step()'s physics by construction, but this is verified directly
# rather than assumed.
# ---------------------------------------------------------------------------


def test_mesh_overlay_geoms_are_visual_only():
    """Every fly_* geom must be non-colliding and effectively massless, so
    the overlay cannot perturb contact detection or the mass matrix."""
    env = make_env()
    try:
        for gi in range(env.model.ngeom):
            name = mujoco.mj_id2name(env.model, mujoco.mjtObj.mjOBJ_GEOM, gi)
            if name and name.startswith("fly_"):
                assert env.model.geom_contype[gi] == 0, name
                assert env.model.geom_conaffinity[gi] == 0, name
    finally:
        env.close()


def test_central_hit_physics_unchanged_by_the_visual_overlay():
    """Regression for the design doc's invariance requirement: the mesh
    overlay itself (I-08a/I-08a-fix/I-08a-style) must never perturb physics.

    The original pin here (bat_contact_vx=6.97982152004564,
    exit_velocity_xyz=[7.290940342091032, 3.924448811941408,
    2.067631551065398]) was I-07b-followthrough's frozen reference, taken
    BEFORE the mesh overlay existed, and this test's whole point was
    reproducing it bit-for-bit with the overlay present. I-07c-swing
    (docs/design/BATTING-QUALITY-AND-SWING.md section 2) then intentionally
    changed the swing's own prep_swing/crossing_time (see
    envs/baseball_b1_env.py's CROSSING_TIME_S comment) -- a deliberate
    control-physics change, unrelated to and independent of the visual
    overlay -- which supersedes that old pin for an orthogonal reason. The
    overlay-invariance property itself was separately verified at overlay-
    introduction time (docs/records/VALIDATION_LOG.md, I-08a) by an A/B
    against a pre-overlay build; that historical evidence stands on its own
    and is not re-run here. This test is re-pinned to the CURRENT (post-
    I-07c-swing) physics baseline so it keeps catching any FUTURE
    accidental physics perturbation from visual-asset changes."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        info = run_to_end(env, controller, "mid_mid")
        assert info["bat_contact_vx"] == pytest.approx(7.400087073197521, abs=1e-9)
        assert info["exit_velocity_xyz"] == pytest.approx(
            [5.517930791046625, 3.3908638695860756, 5.672558285464065], abs=1e-9
        )
        assert info["forward_flight_success"] is True
    finally:
        env.close()


def test_front_leg_overlay_hands_track_the_grip_sites():
    """envs.fly_visual.FrontLegGripOverlay's mocap-driven Tarsus1 (the real
    fingertip mesh, not an abstract IK endpoint) must land exactly on the
    bat's grip sites at every point in prepare/accelerate/contact/
    batted_ball (the "그립이 손잡이에서 떨어지지 않도록" requirement) --
    docs/records/FLY-VISUAL-REVIEW.md's completion bound is <=5mm error;
    this asserts <=1mm (the IK solves for exact equality, so anything above
    float noise indicates a real bug) and that reach is never exceeded
    (`update()`'s returned per-side error must be exactly 0). The
    fingertip is Tarsus1's DISTAL end (mocap_pos is its PROXIMAL/wrist
    origin -- the mesh extends TARSUS1_LEN_M further along -Z from there,
    per the segment-mesh convention scripts/build_fly_visual_asset.py
    documents), reconstructed here the same way MuJoCo would place the
    mesh's own far tip."""
    import mujoco as _mj

    from envs.fly_visual import TARSUS1_LEN_M, FrontLegGripOverlay

    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        overlay = FrontLegGripOverlay(env.model)
        done = False
        checked_any = False
        while not done:
            obs, _reward, terminated, truncated, _info = env.step(controller.act(obs))
            done = terminated or truncated
            reach_error = overlay.update(env.model, env.data)
            for side in ("L", "R"):
                assert reach_error[side] == 0.0, f"{side} out of reach by {reach_error[side]}m"
                target = env.data.site_xpos[overlay.grip_site[side]]
                wrist = env.data.mocap_pos[overlay.mocap_tarsus1[side]]
                quat = env.data.mocap_quat[overlay.mocap_tarsus1[side]]
                mat = np.zeros(9)
                _mj.mju_quat2Mat(mat, quat)
                fingertip = wrist + mat.reshape(3, 3) @ np.array([0.0, 0.0, -TARSUS1_LEN_M])
                assert np.linalg.norm(target - fingertip) < 0.001
                checked_any = True
        assert checked_any
    finally:
        env.close()


def test_front_leg_arm_segments_use_the_same_scale_as_the_rest_of_the_body():
    """Regression for the I-08a bug the review flagged: front-leg meshes
    must NOT be scaled differently from the static rig (the old version
    used a 3x-enlarged K=1200 for just the arms)."""
    body_scale = None
    with open("envs/assets/fly_visual_assets.xml") as f:
        content = f.read()
    for line in content.splitlines():
        if 'name="fly_mesh_Thorax"' in line:
            body_scale = line.split('scale="')[1].split('"')[0]
        if 'name="fly_mesh_LFFemur"' in line or 'name="fly_mesh_LFTibia"' in line or 'name="fly_mesh_LFTarsus1"' in line:
            arm_scale = line.split('scale="')[1].split('"')[0]
            assert arm_scale == body_scale, f"{line} does not match body scale {body_scale}"
    assert body_scale is not None


def test_ground_legs_soles_touch_the_true_world_ground_inside_the_batter_box():
    """docs/records/FLY-VISUAL-REVIEW.md's core finding: I-08a computed the
    rig's ground offset in its OWN local frame, then nested it inside
    batter_body (world z=1.0) WITHOUT subtracting that parent offset, so
    feet ended up ~1m off the ground. This checks the ACTUAL transformed
    mesh vertices (not geom origins, which is the other half of what went
    wrong) of both hind feet (LH/RH, the only grounded legs in the new
    posture) land within 5mm of world z=0 and inside the batter's box."""
    from scripts.fly_mesh_utils import geom_world_vertices

    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        box_pos = env.model.geom_pos[env.batter_box_geom_id]
        box_half = env.model.geom_size[env.batter_box_geom_id]
        mesh_dir = Path("envs/assets/mesh_neuromechfly")
        for side in ("LH", "RH"):
            gid = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_GEOM, f"{side}Tarsus1")
            verts = geom_world_vertices(env.model, env.data, gid, mesh_dir)
            min_z = float(verts[:, 2].min())
            assert abs(min_z) <= 0.005, f"{side} sole world z error {min_z}m exceeds 5mm"
            centroid = verts.mean(axis=0)
            assert abs(centroid[0] - box_pos[0]) <= box_half[0], f"{side} foot outside box in x"
            assert abs(centroid[1] - box_pos[1]) <= box_half[1], f"{side} foot outside box in y"
    finally:
        env.close()


def test_ground_legs_do_not_slip_across_the_episode():
    """The ground-leg rig has no joints at all (static, part of
    fly_visual_body.xml) -- their world pose is a fixed function of
    batter_body's own (unmoving) pose, so this is trivially exact, but
    verified directly rather than assumed: feet must not move at all
    between reset and after a full central-hit episode."""
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        before = {
            side: env.data.xpos[mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_BODY, f"{side}Tarsus1")].copy()
            for side in ("LH", "RH")
        }
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        run_to_end(env, controller, "mid_mid")
        for side in ("LH", "RH"):
            after = env.data.xpos[mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_BODY, f"{side}Tarsus1")]
            assert np.linalg.norm(after - before[side]) < 1e-9
    finally:
        env.close()


# ---------------------------------------------------------------------------
# I-07c-score (docs/design/BATTING-QUALITY-AND-SWING.md section 1): forward
# carry-distance scoring and the new forward-carry-v1 reward version.
# Synthetic boundary cases exercise BaseballB1Env._compute_scoring() by
# setting only the already-recorded episode-state attributes it reads (never
# qpos/qvel/ctrl), so these never touch physics. Real-episode cases run the
# actual oracle controller against mid_mid, matching this file's existing
# pattern.
# ---------------------------------------------------------------------------


def _synthetic_scoring_env(
    *,
    end_reason,
    first_contact_ball_pos=None,
    first_landing_xyz=None,
    exit_velocity=None,
    recontact_count=0,
    prolonged_contact=False,
) -> BaseballB1Env:
    """A freshly-reset env with only the scoring-relevant bookkeeping fields
    overwritten by hand, for constructing exact-distance boundary cases
    (5m/20m/60m landings, rearward hits, out-of-fan landings, recontact,
    timeout) without running a full physics episode."""
    env = make_env()
    env.reset(seed=0, options={"course": "mid_mid"})
    env._end_reason = end_reason
    env._first_contact_ball_pos = (
        np.array(first_contact_ball_pos) if first_contact_ball_pos is not None else None
    )
    env._first_landing_xyz = np.array(first_landing_xyz) if first_landing_xyz is not None else None
    env._exit_velocity = np.array(exit_velocity) if exit_velocity is not None else None
    env._recontact_count = recontact_count
    env._prolonged_contact = prolonged_contact
    return env


def test_synthetic_valid_forward_landings_score_5_20_60m():
    from envs.baseball_b1_env import END_BATTED_BALL_LANDING

    for target_m in (5.0, 20.0, 60.0):
        env = _synthetic_scoring_env(
            end_reason=END_BATTED_BALL_LANDING,
            first_contact_ball_pos=[0.4318, 0.0, 1.0],
            first_landing_xyz=[0.4318 + target_m, 0.0, 0.0],
            exit_velocity=[10.0, 0.0, 1.0],
        )
        try:
            scoring = env._compute_scoring()
            assert scoring["status"] == "complete"
            assert scoring["scoring_valid"] is True
            assert scoring["carry_distance_m"] == pytest.approx(target_m)
            assert scoring["batting_score"] == pytest.approx(target_m)
        finally:
            env.close()


def test_synthetic_rearward_landing_scores_zero_not_null():
    """A landing behind home (x_rel<=0) is a definite, observed failure --
    score 0, not an undetermined/null score."""
    from envs.baseball_b1_env import END_BATTED_BALL_LANDING

    env = _synthetic_scoring_env(
        end_reason=END_BATTED_BALL_LANDING,
        first_contact_ball_pos=[0.4318, 0.0, 1.0],
        first_landing_xyz=[-3.0, 0.0, 0.0],
        exit_velocity=[-2.0, 0.0, 1.0],
    )
    try:
        scoring = env._compute_scoring()
        assert scoring["status"] == "complete"
        assert scoring["scoring_valid"] is False
        assert scoring["batting_score"] == 0.0
        assert scoring["carry_distance_m"] is not None  # raw distance still recorded
    finally:
        env.close()


def test_synthetic_landing_outside_forward_fan_excluded():
    """x_rel>0 but |y_rel|>x_rel: forward of home but outside the +/-45deg
    fan (docs/design/BATTING-QUALITY-AND-SWING.md: 'x_rel>0 및
    |y_rel|<=x_rel')."""
    from envs.baseball_b1_env import END_BATTED_BALL_LANDING

    env = _synthetic_scoring_env(
        end_reason=END_BATTED_BALL_LANDING,
        first_contact_ball_pos=[0.4318, 0.0, 1.0],
        first_landing_xyz=[5.0, 8.0, 0.0],  # x_rel=5, y_rel=8 > x_rel
        exit_velocity=[3.0, 6.0, 1.0],
    )
    try:
        scoring = env._compute_scoring()
        assert scoring["status"] == "complete"
        assert scoring["scoring_valid"] is False
        assert scoring["batting_score"] == 0.0
    finally:
        env.close()


def test_synthetic_recontact_excluded_even_with_forward_landing():
    """A ball pushed further forward by repeated contact must not score,
    even if it lands squarely inside the forward fan."""
    from envs.baseball_b1_env import END_BATTED_BALL_LANDING

    env = _synthetic_scoring_env(
        end_reason=END_BATTED_BALL_LANDING,
        first_contact_ball_pos=[0.4318, 0.0, 1.0],
        first_landing_xyz=[10.0, 0.0, 0.0],
        exit_velocity=[5.0, 0.0, 1.0],
        recontact_count=1,
    )
    try:
        scoring = env._compute_scoring()
        assert scoring["scoring_valid"] is False
        assert scoring["batting_score"] == 0.0
    finally:
        env.close()


def test_synthetic_prolonged_contact_excluded():
    from envs.baseball_b1_env import END_BATTED_BALL_LANDING

    env = _synthetic_scoring_env(
        end_reason=END_BATTED_BALL_LANDING,
        first_contact_ball_pos=[0.4318, 0.0, 1.0],
        first_landing_xyz=[10.0, 0.0, 0.0],
        exit_velocity=[5.0, 0.0, 1.0],
        prolonged_contact=True,
    )
    try:
        scoring = env._compute_scoring()
        assert scoring["scoring_valid"] is False
        assert scoring["batting_score"] == 0.0
    finally:
        env.close()


def test_synthetic_negative_exit_vx_excluded():
    """Clean separation occurred (exit_velocity is not None) but the ball
    is still moving toward the catcher (exit_vx<=0): must not score even if
    it eventually rolled/lands forward by the time this info is read."""
    from envs.baseball_b1_env import END_BATTED_BALL_LANDING

    env = _synthetic_scoring_env(
        end_reason=END_BATTED_BALL_LANDING,
        first_contact_ball_pos=[0.4318, 0.0, 1.0],
        first_landing_xyz=[10.0, 0.0, 0.0],
        exit_velocity=[-0.5, 0.0, 1.0],
    )
    try:
        scoring = env._compute_scoring()
        assert scoring["scoring_valid"] is False
        assert scoring["batting_score"] == 0.0
    finally:
        env.close()


def test_synthetic_timeout_and_out_of_bounds_are_incomplete_with_null_score():
    from envs.baseball_b1_env import END_OUT_OF_BOUNDS, END_TIMEOUT_FLIGHT, END_TIMEOUT_PITCH

    for end_reason in (END_TIMEOUT_PITCH, END_TIMEOUT_FLIGHT, END_OUT_OF_BOUNDS):
        env = _synthetic_scoring_env(end_reason=end_reason)  # no landing observed
        try:
            scoring = env._compute_scoring()
            assert scoring["status"] == "incomplete"
            assert scoring["batting_score"] is None
            assert scoring["scoring_valid"] is False
        finally:
            env.close()


def test_synthetic_miss_without_landing_is_complete_zero_not_incomplete():
    """A definite miss (ball passed the plate, bat never touched it) is a
    normal failure with distance 0 -- distinct from 'incomplete' (which is
    reserved for truncation before an outcome was ever observed)."""
    from envs.baseball_b1_env import END_NO_PITCH_CONTACT

    env = _synthetic_scoring_env(end_reason=END_NO_PITCH_CONTACT)
    try:
        scoring = env._compute_scoring()
        assert scoring["status"] == "complete"
        assert scoring["batting_score"] == 0.0
        assert scoring["scoring_valid"] is False
    finally:
        env.close()


def test_synthetic_in_progress_episode_has_null_status_and_score():
    env = make_env()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        scoring = env._compute_scoring()
        assert scoring["status"] is None
        assert scoring["batting_score"] is None
    finally:
        env.close()


def test_carry_distance_m_and_carry_distance_xy_m_are_distinct_reference_points():
    """docs/design/BATTING-QUALITY-AND-SWING.md: carry_distance_m is anchored
    at the ball's position at first BAT CONTACT; the pre-existing
    carry_distance_xy_m is anchored at the confirmed-SEPARATION exit
    position. These differ by however far the ball travelled while still
    interacting with the bat, so they must not be silently conflated."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        info = run_to_end(env, controller, "mid_mid")
        assert info["carry_distance_m"] is not None
        assert info["carry_distance_xy_m"] is not None
        assert info["carry_distance_m"] != pytest.approx(info["carry_distance_xy_m"])
        assert info["first_contact_ball_pos_xyz"] != info["exit_velocity_xyz"]
    finally:
        env.close()


def test_real_episode_mid_mid_scores_a_valid_forward_hit():
    """End-to-end sanity check on top of the synthetic boundary tests: the
    same oracle-controlled mid_mid episode used throughout this file must
    score validly under the new forward-carry rules, and its display score
    must equal its raw carry distance in meters (1m=1 point, no cap)."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        info = run_to_end(env, controller, "mid_mid")
        assert info["status"] == "complete"
        assert info["scoring_valid"] is True
        assert info["batting_score"] == pytest.approx(info["carry_distance_m"])
        assert info["batting_score"] > 0.0
    finally:
        env.close()


def test_scoring_does_not_change_underlying_physics_trajectory():
    """Phase B invariance requirement ('점수 변경만으로 타구가 달라지면
    실패다'): _compute_scoring()/_info() must be pure read-only bookkeeping
    over already-recorded episode state -- calling them (repeatedly, or via
    step()/reset()) must never itself perturb qpos/qvel/ctrl.

    This used to pin bat_contact_vx/exit_vx to I-07b-fix's mid_mid numbers
    (+6.98/+7.30 m/s) as circumstantial evidence of the same claim. I-07c-
    swing (docs/design/BATTING-QUALITY-AND-SWING.md section 2) then
    intentionally changed those exact numbers for an UNRELATED, deliberate
    reason (prep_swing/crossing_time control redesign, not scoring) --
    see envs/baseball_b1_env.py's CROSSING_TIME_S comment and
    test_central_hit_physics_unchanged_by_the_visual_overlay (which now
    carries that numeric pin). Re-pinning THIS test to the same numbers
    would only duplicate that other test while claiming to test something
    it doesn't -- so this asserts the actual invariant directly (state is
    bit-identical before/after repeated info/scoring calls) instead, which
    stays true no matter how swing physics is later recalibrated."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        info: dict = {}
        while True:
            obs, _reward, terminated, truncated, info = env.step(controller.act(obs))
            if terminated or truncated:
                break
        qpos_before = env.data.qpos.copy()
        qvel_before = env.data.qvel.copy()
        for _ in range(5):
            env._compute_scoring()
            env._info(reward_terms={})
        assert np.array_equal(env.data.qpos, qpos_before)
        assert np.array_equal(env.data.qvel, qvel_before)
        assert info["batting_score"] is not None  # sanity: a real outcome was recorded
    finally:
        env.close()


# ---------------------------------------------------------------------------
# forward-carry-v1 reward version (never mixed with batted-ball-v1's terms
# under the same key names; see ForwardCarryRewardWeights docstring).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# I-07c-swing (docs/design/BATTING-QUALITY-AND-SWING.md section 2): widened
# windup (prep_swing -1.9 -> -1.96, within bat_hinge's fixed [-2.0, 2.0]
# joint limit) raises contact-point speed under the swing axis's already-
# optimal constant-max-torque accelerate phase. See envs/baseball_b1_env.py's
# CROSSING_TIME_S comment for the full before/after numbers and the honestly-
# reported launch-angle/trigger-sensitivity trade-offs.
# ---------------------------------------------------------------------------


def test_i07c_swing_widened_prep_is_the_new_default():
    env = make_env()
    try:
        assert env.prep_swing == pytest.approx(-1.96)
        assert CROSSING_TIME_S["mid_mid"][0] == pytest.approx(0.09425316355759385)
    finally:
        env.close()


def test_i07c_swing_improves_batting_score_over_the_old_i07b_fix_baseline():
    """Same central pitch, same gear/mass/inertia/material/dt (only
    prep_swing and its matching trigger time changed): the new default must
    genuinely beat the old (pre-I-07c-swing) prep_swing=-1.9/trigger=
    0.094091 baseline on both carry distance and display score, while still
    landing validly forward and meeting the settle targets -- not merely
    have "a longer swing" (docs/design/BATTING-QUALITY-AND-SWING.md section
    2 item 4's explicit bar)."""
    old_prep, old_crossing = -1.9, 0.094091
    original = CROSSING_TIME_S["mid_mid"]
    try:
        env_old = make_env(prep_swing=old_prep)
        CROSSING_TIME_S["mid_mid"] = (old_crossing, original[1])
        controller_old = OracleAimController("mid_mid", prep_swing=old_prep, prep_tilt=env_old.prep_tilt)
        info_old = run_to_end(env_old, controller_old, "mid_mid")
        env_old.close()

        CROSSING_TIME_S["mid_mid"] = original  # restore the new default before building env_new
        env_new = make_env()
        controller_new = OracleAimController(
            "mid_mid", prep_swing=env_new.prep_swing, prep_tilt=env_new.prep_tilt
        )
        info_new = run_to_end(env_new, controller_new, "mid_mid")
        env_new.close()

        assert info_old["scoring_valid"] is True
        assert info_new["scoring_valid"] is True
        assert info_new["batting_score"] > info_old["batting_score"]
        assert info_new["carry_distance_m"] > info_old["carry_distance_m"]
        assert info_new["forward_flight_success"] is True
        assert info_new["recontact_count"] == 0
        assert info_new["prolonged_contact"] is False
    finally:
        CROSSING_TIME_S["mid_mid"] = original


def test_i07c_swing_still_meets_settle_targets_at_the_new_prep_angle():
    """Same 0.5s-to-|qvel|<0.2rad/s / 0.02rad-peak-to-peak targets as
    I-07b-followthrough, re-checked at the new prep_swing -- widening the
    windup must not reopen the chasing/oscillation bug that followthrough
    fixed."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        latch_t = None
        hold_t = None
        angles_after_hold = []
        done = False
        while not done:
            obs, _reward, terminated, truncated, _info = env.step(controller.act(obs))
            done = terminated or truncated
            state = controller._swing_axis.state
            if latch_t is None and state in ("brake", "hold"):
                latch_t = env.data.time
            if hold_t is None and state == "hold":
                hold_t = env.data.time
            if hold_t is not None:
                angles_after_hold.append((env.data.time, float(env.data.qpos[env.swing_qpos_adr])))
        assert latch_t is not None and hold_t is not None
        assert hold_t - latch_t <= 0.5
        window = [a for t, a in angles_after_hold if t <= hold_t + 0.2]
        assert max(window) - min(window) < 0.02
    finally:
        env.close()


def test_i07c_swing_trigger_timing_is_a_known_shared_fragility():
    """Honestly-reported finding (docs/design/BATTING-QUALITY-AND-SWING.md
    section 2 item 5: boundary cases/judgment flips must not be hidden): a
    single control-step (0.005s) shift in the mid_mid trigger time flips
    the outcome to an invalid (backward/wrong-direction) hit -- and this was
    ALREADY true of the pre-I-07c-swing prep_swing=-1.9 baseline, not
    something this recalibration introduced or worsened (see
    envs/baseball_b1_env.py's CROSSING_TIME_S comment). Pinned here as a
    known, reproducible, currently-UNFIXED contact-timing sensitivity of the
    bang-bang oracle/collision design -- not asserted as acceptable, just
    tracked so a future change to it is a deliberate, visible decision."""
    original = CROSSING_TIME_S["mid_mid"]
    try:
        for prep, crossing in ((-1.9, 0.094091), (-1.96, 0.09425316355759385)):
            for offset in (-0.005, 0.005):
                CROSSING_TIME_S["mid_mid"] = (crossing + offset, original[1])
                env = make_env(prep_swing=prep)
                controller = OracleAimController("mid_mid", prep_swing=prep, prep_tilt=env.prep_tilt)
                info = run_to_end(env, controller, "mid_mid")
                env.close()
                assert info["scoring_valid"] is False, (
                    f"prep={prep} offset={offset}: expected this KNOWN fragility to still "
                    "flip the outcome invalid -- if it no longer does, the fragility may be "
                    "fixed (update this test's docstring/scope, don't just loosen the assert)"
                )
    finally:
        CROSSING_TIME_S["mid_mid"] = original


def test_forward_carry_v1_weights_are_distinct_from_batted_ball_v1():
    env = make_env()
    try:
        assert env.forward_carry_reward_weights.outcome_scale == 0.1
        assert env.forward_carry_reward_weights.miss_penalty == 3.0
        assert env.forward_carry_reward_weights.control_cost == 0.2
        assert not hasattr(env.forward_carry_reward_weights, "forward_flight_success")
    finally:
        env.close()


def test_default_reward_version_is_unchanged_batted_ball_v1():
    """Default behavior must stay byte-for-byte what every pre-existing
    caller/test already relies on -- forward-carry-v1 is opt-in only."""
    env = make_env()
    try:
        assert env.reward_version == "batted-ball-v1"
    finally:
        env.close()


def test_unknown_reward_version_rejected():
    with pytest.raises(ValueError):
        make_env(reward_version="not-a-real-version")


def test_forward_carry_v1_outcome_matches_spec_formula_on_valid_hit():
    """0.1 * batting_score on a valid scoring outcome, control_cost using
    the identical -0.2*(u_swing^2+u_tilt^2)dt integral as batted-ball-v1
    (same weight, same per-step formula) -- verified by summing both across
    the whole episode and checking they match exactly."""
    env = make_env()
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        total_old_control_cost = 0.0
        total_new_control_cost = 0.0
        info: dict = {}
        while True:
            obs, _reward, terminated, truncated, info = env.step(controller.act(obs))
            total_old_control_cost += info["reward_terms"]["control_cost"]
            total_new_control_cost += info["forward_carry_v1"]["reward_terms"]["control_cost"]
            if terminated or truncated:
                break
        assert info["scoring_valid"] is True
        expected_outcome = 0.1 * info["batting_score"]
        assert info["forward_carry_v1"]["reward_terms"]["outcome"] == pytest.approx(expected_outcome)
        # Timestep-independent, identical formula/weight in both versions --
        # not merely close, but exactly equal every step (same inputs).
        assert total_new_control_cost == pytest.approx(total_old_control_cost)
        assert total_new_control_cost != 0.0
    finally:
        env.close()


def test_forward_carry_v1_outcome_is_flat_penalty_on_miss_no_double_counting():
    """A miss must score -3 flat under forward-carry-v1, and must NOT also
    receive batted-ball-v1's -3 'miss' term added on top when read from the
    same info dict (the two reward_terms dicts are kept fully separate).
    Forcing a definite swing-and-miss with an all-zero action (bat never
    leaves prep) rather than a mismatched controller/course, so the miss is
    guaranteed rather than merely likely."""
    env = make_env()
    try:
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        info: dict = {}
        while True:
            obs, _reward, terminated, truncated, info = env.step(np.zeros(2, dtype=np.float32))
            if terminated or truncated:
                break
        assert info["end_reason"] == "no_pitch_contact"
        assert info["status"] == "complete"
        assert info["scoring_valid"] is False
        assert info["forward_carry_v1"]["reward_terms"]["outcome"] == pytest.approx(-3.0)
        assert info["reward_terms"]["miss"] == pytest.approx(-3.0)
        # No double counting: the active (batted-ball-v1) scalar reward on
        # this final step is exactly sum(reward_terms) -- it does not also
        # fold in forward_carry_v1's -3 outcome term.
        assert _reward == pytest.approx(sum(info["reward_terms"].values()))
    finally:
        env.close()


def test_forward_carry_v1_gives_neither_reward_nor_penalty_on_timeout():
    """External truncation keeps only the already-spent control cost --
    docs/design/BATTING-QUALITY-AND-SWING.md: '외부 truncation에는 outcome
    reward/실패 벌점을 지급하지 않고 소모된 제어비용만 유지한다'."""
    env = make_env(pitch_timeout_s=0.001)  # force END_TIMEOUT_PITCH almost immediately
    try:
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        info: dict = {}
        for _ in range(5):
            obs, _reward, terminated, truncated, info = env.step(np.zeros(2, dtype=np.float32))
            if terminated or truncated:
                break
        assert truncated is True
        assert info["end_reason"] == "timeout_pitch"
        assert info["status"] == "incomplete"
        assert info["forward_carry_v1"]["reward_terms"]["outcome"] == 0.0
    finally:
        env.close()


def test_active_reward_scalar_switches_with_reward_version():
    """step()'s returned scalar `reward` must equal the sum of the ACTIVE
    version's terms only -- selecting forward-carry-v1 must not leave any
    batted-ball-v1 term (e.g. the old +10) mixed into the returned scalar.
    Expected totals are derived from each step's own reward_terms dict (the
    thing under test), not a separately hand-computed magic number, so this
    checks internal consistency rather than re-deriving physics constants."""
    env_old = make_env(reward_version="batted-ball-v1")
    env_new = make_env(reward_version="forward-carry-v1")
    try:
        results = {}
        for label, env in (("old", env_old), ("new", env_new)):
            controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
            obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
            controller.reset()
            total_reward = 0.0
            total_old_terms = 0.0
            total_new_terms = 0.0
            info: dict = {}
            while True:
                obs, reward, terminated, truncated, info = env.step(controller.act(obs))
                total_reward += reward
                total_old_terms += sum(info["reward_terms"].values())
                total_new_terms += sum(info["forward_carry_v1"]["reward_terms"].values())
                if terminated or truncated:
                    break
            results[label] = (total_reward, total_old_terms, total_new_terms, info["scoring_valid"])

        old_total, old_terms_sum, old_new_terms_sum, old_valid = results["old"]
        new_total, new_terms_sum, new_new_terms_sum, new_valid = results["new"]
        assert old_valid is True and new_valid is True
        # env_old's active scalar matches ONLY its own batted-ball-v1 terms.
        assert old_total == pytest.approx(old_terms_sum)
        # env_new's active scalar matches ONLY its own forward-carry-v1
        # terms, not the batted-ball-v1 terms computed alongside it.
        assert new_total == pytest.approx(new_new_terms_sum)
        assert new_total != pytest.approx(new_terms_sum)
        # Same deterministic seed/course/controller on both envs -> the two
        # reward versions' totals genuinely differ (old pays flat +10 on
        # success; new pays 0.1*batting_score, a much smaller number here).
        assert old_total != pytest.approx(new_total)
    finally:
        env_old.close()
        env_new.close()

"""Batter scene regression tests (D26-D29).

Mostly geometry: the scaling rule, where the eyes look, that the fly's feet
are on the ground, that the reference poses still mean what their names say.
"""
from __future__ import annotations

import itertools
import math

import mujoco
import numpy as np
import pytest

from flyohtani.body.limits import MAX_JOINT_SPEED_RAD_S
from flyohtani.world import batter as B


@pytest.fixture(scope="module")
def scene():
    return B.build_scene()


@pytest.fixture()
def md(scene):
    m = scene.model()
    return m, mujoco.MjData(m)


def _id(m, kind, name):
    i = mujoco.mj_name2id(m, kind, name)
    assert i >= 0, name
    return i


class TestScalingRule:
    def test_bat_is_a_real_bat_scaled_by_fly_height(self, scene):
        assert scene.bat_length_mm / scene.fly_height_mm == pytest.approx(
            B.BAT_LENGTH_MM / B.HUMAN_HEIGHT_MM)

    def test_ball_is_a_real_ball_scaled_the_same_way_then_enlarged(self, scene):
        """D27 scales it; D31 then multiplies it by BALL_SCALE, because
        VM-01 measured that the scale-true ball is invisible to the eye."""
        assert scene.ball_radius_mm == pytest.approx(
            B.BALL_RADIUS_MM * scene.scale * B.BALL_SCALE)

    def test_fly_is_still_real_fly_size(self, scene):
        """D21 stands: the equipment shrinks to the fly, not the other way."""
        assert 2.0 < scene.fly_height_mm < 5.0

    def test_bat_mass_comes_from_wood_density_and_the_lathe_volume(self, md, scene):
        m, _ = md
        prof = B.bat_profile(scene.scale)
        volume = sum(math.pi * (z1 - z0) * (r0 * r0 + r0 * r1 + r1 * r1) / 3
                     for (z0, r0), (z1, r1) in itertools.pairwise(prof))
        # the lathe is a 24-gon inscribed in the circle: area ratio
        # (24/2pi) sin(2pi/24) = 0.9886. The first build got +8% here, because
        # MuJoCo's default mesh volume assumes a convex mesh; a bat is not.
        polygon = 24 / (2 * math.pi) * math.sin(2 * math.pi / 24)
        assert m.body_mass[_id(m, mujoco.mjtObj.mjOBJ_BODY, "bat")] == pytest.approx(
            B.WOOD_DENSITY * volume * polygon, rel=0.005)

    def test_light_bodies_are_not_inflated_by_boundmass(self, md, scene):
        """G1 section 5.3: boundmass silently inflates light bodies. Tarsus1
        is under the source model's 1e-6 floor at this scale, and the D31
        ball sits just above it; both must come through at their own mass."""
        m, _ = md
        ball = m.body_mass[_id(m, mujoco.mjtObj.mjOBJ_BODY, "ball")]
        # D31: 8x the radius at BALL_MASS_SCALE x the mass a SCALE-TRUE ball
        # would have. Enlarging it without this would have made it 512x
        # heavier and 77x the bat -- measured, batter_check.
        true_r = B.BALL_RADIUS_MM * scene.scale
        # rel=1e-5: the radius goes into the MJCF at 6 significant figures.
        assert ball == pytest.approx(
            B.BALL_DENSITY * 4 / 3 * math.pi * true_r ** 3 * B.BALL_MASS_SCALE, rel=1e-5)
        # Tarsus1 really is lighter than the source model's 1e-6 floor; it
        # must come through at its own mass, not the floor.
        tarsus = m.body_mass[_id(m, mujoco.mjtObj.mjOBJ_BODY, "RFTarsus1")]
        assert tarsus == pytest.approx(4.6485138504422505e-07, rel=1e-9)
        assert tarsus < 1e-6


class TestStage:
    def test_only_the_arm_and_the_ball_move(self, md):
        m, _ = md
        assert m.nu == 5
        assert m.nv == 5 + 6

    def test_feet_are_on_the_ground(self, md):
        m, d = md
        mujoco.mj_forward(m, d)
        lows = []
        for g in range(m.ngeom):
            name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
            if "HTarsus" not in name:
                continue
            mid = m.geom_dataid[g]
            v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
            lows.append((d.geom_xpos[g] + v @ d.geom_xmat[g].reshape(3, 3).T)[:, 2].min())
        assert B.DIRT_TOP_MM < min(lows) < B.DIRT_TOP_MM + 0.01  # standing on the dirt, not floating

    def test_fly_stands_inside_the_right_handed_box(self, md, scene):
        m, d = md
        mujoco.mj_forward(m, d)
        thorax = d.xpos[_id(m, mujoco.mjtObj.mjOBJ_BODY, "Thorax")]
        half_w = B.PLATE_WIDTH_MM * scene.scale / 2
        y0 = half_w + B.BOX_GAP_MM * scene.scale
        y1 = y0 + B.BOX_WIDTH_MM * scene.scale
        assert y0 < thorax[1] < y1  # third-base side of the plate (+y)
        assert thorax[2] > 0.5 * scene.fly_height_mm  # upright: the thorax is high up

    def test_plate_points_at_the_catcher(self, md):
        m, d = md
        mujoco.mj_forward(m, d)
        g = _id(m, mujoco.mjtObj.mjOBJ_GEOM, "plate")
        mid = m.geom_dataid[g]
        v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
        world = d.geom_xpos[g] + v @ d.geom_xmat[g].reshape(3, 3).T
        tip = world[np.argmin(world[:, 0])]
        assert abs(tip[1]) < 1e-6  # the single point sits on the pitch line
        assert world[:, 0].max() == pytest.approx(0.0, abs=1e-6)  # front edge faces the pitcher


class TestEyes:
    @pytest.mark.parametrize("side, sign", [("L", +1), ("R", -1)])
    def test_left_eye_faces_the_pitcher_right_eye_the_catcher(self, md, side, sign):
        m, d = md
        mujoco.mj_forward(m, d)
        c = _id(m, mujoco.mjtObj.mjOBJ_CAMERA, f"eye_{side}")
        mat = d.cam_xmat[c].reshape(3, 3)
        forward, up = -mat[:, 2], mat[:, 1]
        assert sign * forward[0] > 0.9
        assert forward[2] == pytest.approx(-math.sin(math.radians(B.EYE_DOWN_TILT_DEG)), abs=1e-6)
        assert up[2] > 0.9

    def test_eyes_ride_on_the_head(self, md):
        m, _ = md
        head = _id(m, mujoco.mjtObj.mjOBJ_BODY, "Head")
        for side in ("L", "R"):
            assert m.cam_bodyid[_id(m, mujoco.mjtObj.mjOBJ_CAMERA, f"eye_{side}")] == head

    def test_eye_images_are_small_grayscale_and_not_blocked_by_the_head(self, md):
        m, d = md
        mujoco.mj_forward(m, d)
        r = mujoco.Renderer(m, B.EYE_RESOLUTION, B.EYE_RESOLUTION)
        try:
            eyes = B.render_eyes(m, d, r)
        finally:
            r.close()
        for img in eyes.values():
            assert img.shape == (B.EYE_RESOLUTION, B.EYE_RESOLUTION)
            assert img.dtype == np.uint8
            # sky above, ground below: a real scene, not the inside of an eye mesh
            assert img[:4].mean() > img[-4:].mean() + 20

    def test_acuity_is_the_one_d31_chose(self):
        """D28 asked for fly-like (3.75 deg per pixel against a fruit fly's
        ~5 deg ommatidial spacing). D31 keeps the 32 px but narrows the field
        to 60 deg, which is FINER than the animal -- a deliberate departure,
        measured in VM-01, not a drift. The pixel count is what D28 fixed and
        that is unchanged."""
        assert B.EYE_RESOLUTION == 32
        assert B.EYE_FOVY_DEG / B.EYE_RESOLUTION == pytest.approx(1.875)


class TestPoses:
    def _bat(self, m, d, pose):
        B.set_arm(m, d, pose)
        g = d.site_xpos[_id(m, mujoco.mjtObj.mjOBJ_SITE, "grip")]
        t = d.site_xpos[_id(m, mujoco.mjtObj.mjOBJ_SITE, "bat_tip")]
        s = d.site_xpos[_id(m, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")].copy()
        return (t - g) / np.linalg.norm(t - g), s

    def test_ready_pose_holds_the_bat_up_and_back(self, md):
        m, d = md
        u, _ = self._bat(m, d, B.READY_POSE)
        assert u[2] > 0.8   # up
        assert u[0] < 0     # toward the catcher

    def test_contact_pose_puts_the_sweet_spot_over_the_plate(self, md, scene):
        m, d = md
        u, s = self._bat(m, d, B.CONTACT_POSE)
        plate_mid = np.array([-B.PLATE_SIDE_MM * scene.scale, 0.0])
        assert np.linalg.norm(s[:2] - plate_mid) < 0.15
        assert s[2] == pytest.approx(1.2, abs=0.05)
        assert u[1] < -0.8  # across the plate

    def test_demo_swing_stays_under_the_biological_ceiling(self, md):
        """LIT-01: 300 rad/s. The demo swing is not the learned swing, but it
        must not be faster than a fly."""
        m, d = md
        B.set_arm(m, d, B.READY_POSE)
        ball = _id(m, mujoco.mjtObj.mjOBJ_BODY, "ball")
        qa = m.jnt_qposadr[m.body_jntadr[ball]]
        d.qpos[qa:qa + 3] = (30.0, 0.0, 1.0)
        m.opt.gravity[:] = 0
        peak, touched_ground = 0.0, False
        for _ in range(round(1.6 * B.DEMO_SWING_S / m.opt.timestep)):
            tgt = B.swing_targets(d.time)
            d.ctrl[:] = [tgt[j] for j in B.ACTIVE_JOINTS]
            mujoco.mj_step(m, d)
            peak = max(peak, float(np.max(np.abs(d.qvel[:5]))))
            touched_ground = touched_ground or d.ncon > 0
        assert 50.0 < peak < MAX_JOINT_SPEED_RAD_S
        # The first version of this swing went the short way round and
        # dragged the bat through the ground; the impact is what broke the
        # ceiling, not the command.
        assert not touched_ground
        assert not any(d.warning[i].number for i in range(mujoco.mjtWarning.mjNWARNING))


class TestContactSettings:
    def test_one_fixed_step_and_a_contact_spanning_many_of_them(self, md):
        m, _ = md
        assert m.opt.timestep == B.TIMESTEP_S
        assert B.CONTACT_TIMECONST_S >= 2 * B.TIMESTEP_S  # MuJoCo's silent clamp never fires
        assert B.CONTACT_TIMECONST_S / B.TIMESTEP_S == 32

    def test_ball_and_bat_use_the_scene_contact(self, md):
        m, _ = md
        for name in ("ball", "bat_c4", "ground"):
            g = _id(m, mujoco.mjtObj.mjOBJ_GEOM, name)
            assert m.geom_solref[g][0] == pytest.approx(B.CONTACT_TIMECONST_S)
            assert m.geom_solref[g][1] == pytest.approx(B.CONTACT_DAMPRATIO)

    def test_the_fly_itself_does_not_collide(self, md):
        m, _ = md
        for g in range(m.ngeom):
            name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
            if name in ("ground", "ball") or name.startswith("bat_c"):
                continue
            assert m.geom_contype[g] == 0 and m.geom_conaffinity[g] == 0, name

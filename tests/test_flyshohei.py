"""The pitcher: the arsenal, the geometry of a delivery, and the fly on the
mound.

No test here asserts that a pitch is hittable. Whether it is is a
measurement -- docs/records/VM-01-EYE-RATE.md -- and a test demanding it
would become a reason to keep softening the pitch until it passed.
"""
from __future__ import annotations

import mujoco
import numpy as np
import pytest

from flyohtani import units
from flyohtani.world import batter as B
from flyshohei import pitch as P


class TestArsenal:
    def test_a_pitch_is_registered_under_its_own_name(self):
        for name, pitch in P.ARSENAL.items():
            assert pitch.name == name

    def test_an_unknown_pitch_is_refused_rather_than_defaulted(self):
        """Silently throwing the standard pitch would measure the wrong
        thing under the right name."""
        with pytest.raises(KeyError):
            P.get("curveball")

    def test_the_standard_pitch_is_thrown_from_the_rubber(self):
        """D35. 1.0 is the pitcher's own hand; D32's 3.6 put it in mid-air."""
        assert P.STANDARD.distance_scale == 1.0
        assert P.FROM_MOUND

    def test_the_eye_can_keep_up_with_every_pitch_in_the_arsenal(self):
        """Flight time and eye rate are not independent (VM-01's hold-out
        failed on exactly this). A new pitch that outruns the eye should
        fail here rather than quietly go unseen."""
        for pitch in P.ARSENAL.values():
            assert B.min_eye_rate_hz(pitch.flight_s) <= B.EYE_RATE_HZ, pitch.name


class TestGeometry:
    scale = 3.737 / 1830.0

    def _strike(self, dz: float = 0.0) -> np.ndarray:
        return np.array([0.35, 0.0, 1.05 + dz])

    def test_the_ball_arrives_where_it_was_aimed(self):
        strike = self._strike()
        release, v0, flight = P.geometry(strike, self.scale)
        g = np.array([0.0, 0.0, -units.GRAVITY])
        landed = release + v0 * flight + 0.5 * g * flight ** 2
        assert landed == pytest.approx(strike, abs=1e-9)

    def test_the_hand_does_not_move_when_the_pitcher_aims_higher(self):
        """The D35 bug: deriving the release from the strike point made a
        high pitch appear LOWER in the eye than a low one, because the line
        pivots about the plate."""
        nominal = self._strike()
        releases = [P.geometry(self._strike(dz), self.scale, release_reference=nominal)[0]
                    for dz in (-0.35, 0.0, 0.45)]
        for r in releases[1:]:
            assert r == pytest.approx(releases[0], abs=1e-12)

    def test_the_pivot_bug_needs_a_release_out_in_front_to_exist(self):
        """Why the standard pitch is immune: at distance_scale 1.0 the
        release IS the hand, so the reference cannot matter. Pull it back
        out to where D32 threw from and the aim drags the hand with it --
        aiming 0.45 higher drops the release. Anything that moves the
        release out again has to pass a reference."""
        high = self._strike(0.45)
        far_no_ref = P.geometry(high, self.scale, distance_scale=3.6)[0]
        far_ref = P.geometry(high, self.scale, distance_scale=3.6,
                             release_reference=self._strike())[0]
        assert far_no_ref[2] < far_ref[2] - 1e-6

    def test_the_pitch_is_lofted_and_therefore_faster_than_the_straight_line(self):
        """Gravity, not choice: over 52 ms the ball falls, so it leaves the
        hand climbing, and the speed that gets it there exceeds
        distance / flight."""
        strike = self._strike()
        release, _, flight = P.geometry(strike, self.scale)
        straight = float(np.linalg.norm(strike - release)) / flight
        assert P.STANDARD.speed_mm_s(strike, self.scale) > straight
        assert P.STANDARD.launch_angle_deg(strike, self.scale) > 0.0

    def test_a_longer_flight_is_a_slower_pitch(self):
        strike = self._strike()
        slow = P.Pitch(name="slow", flight_s=P.STANDARD.flight_s * 1.5)
        assert slow.speed_mm_s(strike, self.scale) < P.STANDARD.speed_mm_s(strike, self.scale)


@pytest.fixture(scope="module")
def md():
    scene = B.build_scene()
    model = mujoco.MjModel.from_xml_string(scene.xml)
    data = mujoco.MjData(model)
    B.set_arm(model, data, B.READY_POSE)
    mujoco.mj_forward(model, data)
    return model, data, scene


def _id(model, kind, name):
    return mujoco.mj_name2id(model, kind, name)


def test_the_pitcher_is_on_the_rubber_and_cannot_touch_anything(md):
    """D35. It throws nothing -- `pitch.geometry` does -- but a viewer's
    first question is where the ball comes from, and before this there was
    no answer."""
    model, data, scene = md
    body = _id(model, mujoco.mjtObj.mjOBJ_BODY, "Pitcher")
    assert body >= 0
    assert data.xpos[body][0] == pytest.approx(P.PITCH_DISTANCE_MM * scene.scale, rel=1e-6)
    for g in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if name.startswith("P_"):
            assert model.geom_contype[g] == 0 and model.geom_conaffinity[g] == 0, name


def test_the_pitcher_stands_on_the_mound_rather_than_in_it(md):
    model, data, _ = md
    batter_head = data.xpos[_id(model, mujoco.mjtObj.mjOBJ_BODY, "Head")][2]
    pitcher_head = data.xpos[_id(model, mujoco.mjtObj.mjOBJ_BODY, "P_Head")][2]
    assert pitcher_head > batter_head, "the pitcher is sunk into the mound"

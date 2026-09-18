"""The ballpark: scenery that must stay scenery, and the one part of it that
is not decoration."""
from __future__ import annotations

import math

import mujoco
import pytest

from flyohtani.world import batter as B
from flyohtani.world import park as P


@pytest.fixture(scope="module")
def scene() -> B.Scene:
    return B.build_scene()


@pytest.fixture(scope="module")
def md(scene):
    model = mujoco.MjModel.from_xml_string(scene.xml)
    data = mujoco.MjData(model)
    B.set_arm(model, data, B.READY_POSE)
    mujoco.mj_forward(model, data)
    return model, data


def _id(model, kind, name):
    return mujoco.mj_name2id(model, kind, name)


def test_the_batters_eye_is_dark_straight_out_and_does_not_collide(md, scene):
    """D31c. In a real park the batter's eye is the dark section of the
    centre-field stands, and it is there for the reason VM-01 v3
    measured: against the bright sky a white ball reaches 6% contrast in
    this eye and is missed; against this it is seen from release."""
    m, d = md
    mujoco.mj_forward(m, d)
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or "" for g in range(m.ngeom)]
    dark = [g for g, n in enumerate(names) if n.startswith("batters_eye_")]
    assert dark, "no batter's eye in the park"
    for g in dark:
        assert m.geom_rgba[g][:3].max() < 0.2
        assert m.geom_contype[g] == 0 and m.geom_conaffinity[g] == 0
        assert d.geom_xpos[g][0] > P.FENCE_LINE_MM * scene.scale  # out past the fence
        assert abs(math.degrees(math.atan2(d.geom_xpos[g][1], d.geom_xpos[g][0]))) \
            <= P.BATTERS_EYE_HALF_ANGLE_DEG + 2  # dead centre

def test_the_park_is_scenery_only(md):
    """Every ballpark geom is visual: the ball lands on the ground plane,
    and nothing out there can touch the fly or the bat."""
    m, _ = md
    park = ("fence", "stand", "backstop", "foul_pole", "base_", "path_", "mound",
            "rubber", "infield_", "foul_line", "batters_eye_")
    for g in range(m.ngeom):
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if name.startswith(park):
            assert m.geom_contype[g] == 0 and m.geom_conaffinity[g] == 0, name

def test_the_fence_is_short_down_the_lines_and_deep_in_centre():
    assert P._fence_radius_mm(0.0) == pytest.approx(P.FENCE_CENTER_MM)
    assert P._fence_radius_mm(math.radians(45)) == pytest.approx(P.FENCE_LINE_MM)
    assert P._fence_radius_mm(math.radians(-45)) == pytest.approx(P.FENCE_LINE_MM)


def test_the_pitcher_is_on_the_rubber_and_cannot_touch_anything(md, scene):
    """D35. It throws nothing -- the launcher does -- but a viewer's first
    question is where the ball comes from, and before this there was no
    answer."""
    model, data = md
    body = _id(model, mujoco.mjtObj.mjOBJ_BODY, "Pitcher")
    assert body >= 0
    assert data.xpos[body][0] == pytest.approx(B.PITCH_DISTANCE_MM * scene.scale, rel=1e-6)
    for g in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if name.startswith("P_"):
            assert model.geom_contype[g] == 0 and model.geom_conaffinity[g] == 0, name


def test_the_pitcher_stands_on_the_mound_rather_than_in_it(md):
    model, data = md
    batter_head = data.xpos[_id(model, mujoco.mjtObj.mjOBJ_BODY, "Head")][2]
    pitcher_head = data.xpos[_id(model, mujoco.mjtObj.mjOBJ_BODY, "P_Head")][2]
    assert pitcher_head > batter_head, "the pitcher is sunk into the mound"

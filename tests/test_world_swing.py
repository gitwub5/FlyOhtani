"""The swing stepper and the ballistics, which three modules used to own a
copy of each."""
from __future__ import annotations

import mujoco
import numpy as np
import pytest

from flyohtani.world import batter as B
from flyohtani.world import swing as S


def test_phase_c_solves_the_same_parabola_the_simulator_walks():
    """The landing point is computed, not stepped. With no drag and no spin
    that is exact, and this is the check that it is not merely close."""
    pos = np.array([1.0, 0.0, 4.0])
    vel = np.array([300.0, 50.0, 200.0])
    t = S.time_to_ground(pos, vel, radius_mm=0.15)
    landed = S.ballistic(pos, vel, t)
    assert landed[2] == pytest.approx(0.15 + B.DIRT_TOP_MM, abs=1e-9)
    assert S.ballistic(pos, vel, t * 0.99)[2] > landed[2]


def test_a_ball_that_never_comes_down_is_reported_as_such():
    assert S.time_to_ground(np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 0.0]),
                            radius_mm=2.0) == float("inf")


def test_fair_territory_is_between_the_foul_lines():
    assert S.is_fair(np.array([10.0, 0.0]))
    assert S.is_fair(np.array([10.0, 9.9]))
    assert not S.is_fair(np.array([10.0, 10.1]))
    assert not S.is_fair(np.array([-1.0, 0.0]))


def test_the_swing_table_is_the_trajectory_swing_targets_describes():
    dt, n = 1e-4, 50
    table = S.swing_table(B.DEMO_SWING_S, B.DEMO_SWING_FOLLOW, dt, n, "middle")
    assert table.shape == (n, len(B.ACTIVE_JOINTS))
    for i in (0, 17, n - 1):
        want = B.swing_targets(i * dt, duration_s=B.DEMO_SWING_S,
                               follow=B.DEMO_SWING_FOLLOW, zone="middle")
        assert table[i] == pytest.approx([want[j] for j in B.ACTIVE_JOINTS])


def test_each_zone_gets_its_own_table():
    dt, n = 1e-4, 20
    high = S.swing_table(B.DEMO_SWING_S, B.DEMO_SWING_FOLLOW, dt, n, "high")
    low = S.swing_table(B.DEMO_SWING_S, B.DEMO_SWING_FOLLOW, dt, n, "low")
    assert not np.array_equal(high, low)


def test_the_bat_geoms_are_the_ones_that_can_touch_the_ball():
    model = mujoco.MjModel.from_xml_string(B.build_scene().xml)
    ids = S.bat_geom_ids(model)
    assert len(ids) == 5
    for g in ids:
        assert mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g).startswith("bat_c")
        assert model.geom_contype[g] != 0


def test_a_batted_ball_reports_what_it_did():
    hit = S.batted_ball(np.array([0.0, 0.0, 1.5]), np.array([400.0, 100.0, 300.0]), 0.15)
    assert hit.exit_speed_mm_s == pytest.approx(np.linalg.norm([400.0, 100.0, 300.0]))
    assert 0 < hit.launch_angle_deg < 90
    assert hit.spray_angle_deg == pytest.approx(np.degrees(np.arctan2(100.0, 400.0)))
    assert hit.carry_mm > 0 and hit.fair is True

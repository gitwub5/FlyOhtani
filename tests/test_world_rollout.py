"""The fast episode path, held against the slow one.

`rollout.run` exists only to be faster than `record.scenarios.run_pitch`; the
moment it answers differently it is worthless. These tests are the contract:
the criteria live in the module (pre-registered, before it was written) and
this file applies them.
"""
from __future__ import annotations

import numpy as np
import pytest

from flyohtani.record import scenarios as S
from flyohtani.world import batter as B
from flyohtani.world import rollout as R

# timing x aim-height pairs: a chopper, a line drive, and misses either side.
CASES = [(t, dz) for t in (-3.0, 0.0, 3.0) for dz in (0.0, 0.05)]


@pytest.fixture(scope="module")
def paired() -> list[tuple[tuple[float, float], object, R.Rollout]]:
    out = []
    for t, dz in CASES:
        ref, _ = S.run_pitch(S.PitchSpec(timing_ms=t, aim_offset_mm=(0.0, 0.0, dz)), record=False)
        fast = R.run(t, (0.0, 0.0, dz))
        out.append(((t, dz), ref, fast))
    return out


def test_it_agrees_about_contact(paired):
    for case, ref, fast in paired:
        assert ref.contact == fast.contact, case


def test_it_agrees_about_the_batted_ball(paired):
    for case, ref, fast in paired:
        if not ref.contact:
            continue
        assert abs(fast.exit_speed_mm_s - ref.exit_speed_mm_s) / ref.exit_speed_mm_s \
            <= R.MAX_EXIT_SPEED_REL, case
        assert abs(fast.launch_angle_deg - ref.launch_angle_deg) <= R.MAX_ANGLE_ERROR_DEG, case
        assert abs(fast.spray_angle_deg - ref.spray_angle_deg) <= R.MAX_ANGLE_ERROR_DEG, case
        assert abs(fast.carry_mm - ref.carry_mm) / ref.carry_mm <= R.MAX_CARRY_REL, case
        assert fast.fair == ref.fair, case


def test_it_agrees_about_the_swing_itself(paired):
    """Same arm, same trajectory: the peak joint speed is the one LIT-01's
    ceiling is checked against, so it may not drift."""
    for case, ref, fast in paired:
        assert fast.peak_joint_speed_rad_s == pytest.approx(ref.peak_joint_speed_rad_s, rel=0.02), case


def test_phase_c_solves_the_same_parabola_the_simulator_walks():
    """The landing point is computed, not stepped. With no drag and no spin
    that is exact, and this is the check that it is not merely close."""
    pos = np.array([1.0, 0.0, 4.0])
    vel = np.array([300.0, 50.0, 200.0])
    t = R.time_to_ground(pos, vel, radius_mm=0.15)
    landed = R.ballistic(pos, vel, t)
    assert landed[2] == pytest.approx(0.15 + B.DIRT_TOP_MM, abs=1e-9)
    assert R.ballistic(pos, vel, t * 0.99)[2] > landed[2]


def test_a_ball_that_never_comes_down_is_reported_as_such():
    assert R.time_to_ground(np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 0.0]),
                            radius_mm=2.0) == float("inf")


def test_fair_territory_is_between_the_foul_lines():
    assert R._fair(np.array([10.0, 0.0]))
    assert R._fair(np.array([10.0, 9.9]))
    assert not R._fair(np.array([10.0, 10.1]))
    assert not R._fair(np.array([-1.0, 0.0]))


def test_the_criteria_are_the_ones_that_were_registered():
    """A test that fails when someone loosens the contract instead of fixing
    the code. The numbers are in the module docstring's measurement table."""
    assert R.MAX_EXIT_SPEED_REL == 0.01
    assert R.MAX_ANGLE_ERROR_DEG == 0.5
    assert R.MAX_CARRY_REL == 0.02
    assert R.COARSE_DT_S == B.TIMESTEP_S, "coarsening the swing failed the criteria"

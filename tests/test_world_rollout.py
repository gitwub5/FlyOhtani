"""The fast episode path, held against the slow one.

The ballistics and fair-territory tests that used to live here moved to
tests/test_world_swing.py with the code they cover.

`rollout.run` exists only to be faster than `record.scenarios.run_pitch`; the
moment it answers differently it is worthless. These tests are the contract:
the criteria live in the module (pre-registered, before it was written) and
this file applies them.
"""
from __future__ import annotations

import pytest

from flyohtani.record import scenarios as S
from flyohtani.world import batter as B
from flyohtani.world import rollout as R
from flyshohei import pitch as P

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
        assert fast.fair == ref.fair, case
        if ref.fair:
            # Carry only where carry is read: rewards.carry_v1 pays for
            # distance on fair balls, and the two criteria above cannot both
            # hold on a glancing foul tip -- see R.MAX_CARRY_REL for the
            # measurement that says so.
            assert abs(fast.carry_mm - ref.carry_mm) / ref.carry_mm <= R.MAX_CARRY_REL, case


def test_it_agrees_about_the_swing_itself(paired):
    """Same arm, same trajectory: the peak joint speed is the one LIT-01's
    ceiling is checked against, so it may not drift."""
    for case, ref, fast in paired:
        assert fast.peak_joint_speed_rad_s == pytest.approx(ref.peak_joint_speed_rad_s, rel=0.02), case


def test_the_criteria_are_the_ones_that_were_registered():
    """A test that fails when someone loosens the contract instead of fixing
    the code. The numbers are in the module docstring's measurement table."""
    assert R.MAX_EXIT_SPEED_REL == 0.01
    assert R.MAX_ANGLE_ERROR_DEG == 0.5
    assert R.MAX_CARRY_REL == 0.02
    assert R.COARSE_DT_S == B.TIMESTEP_S, "coarsening the swing failed the criteria"


def test_the_swing_to_contact_constant_is_still_true():
    """B.SWING_TO_CONTACT_S is the corrected decision deadline (VM-01 used
    the whole swing and was 25 ms too strict). It is a measured number, so
    it gets a regression test rather than a comment."""
    t_star, _ = R.dry_swing(B.build_scene(), B.DEMO_SWING_S, B.DEMO_SWING_FOLLOW)
    assert t_star == pytest.approx(B.SWING_TO_CONTACT_S, abs=5e-4)


def test_the_eye_rate_rule_uses_the_corrected_deadline():
    need = B.min_eye_rate_hz()
    window = P.STANDARD.flight_s - B.SWING_TO_CONTACT_S - B.DECISION_LATENCY_S
    assert need == pytest.approx(B.MIN_DECISION_FRAMES / window)
    assert need < B.EYE_RATE_HZ, "the eye is faster than the rule requires"

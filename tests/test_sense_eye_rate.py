"""VM-01's measurement code, not its result.

The result (which combinations are usable) belongs in the evidence file and
docs/records/, not in an assertion here -- a test that asserts an outcome
would have to be edited whenever the measurement is redone, which is exactly
how a criterion gets quietly loosened.
"""
from __future__ import annotations

import math

import pytest

from flyohtani.sense import eye_rate as ER
from flyohtani.world import batter as B


def test_froude_duplicate_matches_the_recording_stack():
    """eye_rate._froude is a copy; if scenarios' version changes, this fails."""
    from flyohtani.record.scenarios import froude_speed

    for scale in (1.0, 2.042e-3, 1e-4):
        assert ER._froude(scale) == pytest.approx(froude_speed(scale))


def test_criteria_are_declared_before_use():
    assert ER.DETECT_THRESHOLD > 0
    assert ER.MIN_DECISION_FRAMES >= 2, "one frame cannot show expansion"
    assert ER.MIN_DISTINCT_SIZES >= 2
    assert 0 < ER.DECISION_LATENCY_S < B.DEMO_SWING_S


@pytest.fixture(scope="module")
def slow_combination() -> ER.Combination:
    """The cheapest cell in the grid: slowest ball, lowest eye rate."""
    return ER.measure(speed_scale=min(ER.SPEED_SCALES), eye_rate_hz=min(ER.EYE_RATES_HZ),
                      ball_scale=1.0)


@pytest.fixture(scope="module")
def fast_combination() -> ER.Combination:
    return ER.measure(speed_scale=1.0, eye_rate_hz=240, ball_scale=1.0)


def test_a_flat_pitch_closes_in_monotonically(fast_combination):
    distances = [f.distance_mm for f in fast_combination.frames]
    assert len(distances) >= 2
    assert distances == sorted(distances, reverse=True)
    sizes = [f.angular_diameter_deg for f in fast_combination.frames]
    assert sizes == sorted(sizes), "closing in must not shrink the ball"


def test_slowing_the_ball_alone_lobs_it(slow_combination):
    """Why DISTANCE_SCALES exists. Holding the release point at full distance
    and dropping the speed forces the pitcher to throw a rainbow, and V5 is
    what notices."""
    assert slow_combination.launch_angle_deg > ER.MAX_LAUNCH_DEG
    assert not slow_combination.v5_is_a_pitch
    closer = ER.measure(speed_scale=min(ER.SPEED_SCALES), eye_rate_hz=min(ER.EYE_RATES_HZ),
                        ball_scale=1.0, distance_scale=min(ER.DISTANCE_SCALES))
    assert closer.launch_angle_deg < slow_combination.launch_angle_deg


def test_field_of_view_is_recorded_per_frame(slow_combination):
    half = B.EYE_FOVY_DEG / 2
    for f in slow_combination.frames:
        assert f.in_fov == (f.off_axis_deg <= half)
    assert any(f.in_fov for f in slow_combination.frames)


def test_flight_time_matches_the_pitch_speed(fast_combination):
    c = fast_combination
    travelled = c.frames[0].distance_mm - c.frames[-1].distance_mm
    assert travelled == pytest.approx(c.pitch_speed_mm_s * c.frames[-1].t_s, rel=0.15)


def test_the_reference_render_has_no_ball_in_it(slow_combination):
    """Every detected pixel is the ball, so the first frame -- with the ball
    still 30+ mm away -- must be at or near zero."""
    assert slow_combination.frames[0].detected_px <= 1


def test_angular_size_agrees_with_geometry(slow_combination):
    f = slow_combination.frames[-1]
    expected = 2 * math.degrees(math.asin(slow_combination.ball_radius_mm / f.distance_mm))
    assert f.angular_diameter_deg == pytest.approx(expected, rel=1e-3)


def test_a_bigger_ball_covers_more_of_the_eye(slow_combination):
    big = ER.measure(speed_scale=min(ER.SPEED_SCALES), eye_rate_hz=min(ER.EYE_RATES_HZ),
                     ball_scale=max(ER.BALL_SCALES))
    assert big.ball_radius_mm > slow_combination.ball_radius_mm
    assert big.frames[-1].angular_diameter_deg > slow_combination.frames[-1].angular_diameter_deg
    assert big.peak_detected_px >= slow_combination.peak_detected_px

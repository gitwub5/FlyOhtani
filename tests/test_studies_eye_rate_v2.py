"""VM-01 v2's measurement code. As in v1, no assertion here states which
configuration passes -- that is the measurement's job, not the test's."""
from __future__ import annotations

import pytest

from flyohtani.studies import eye_rate as V1
from flyohtani.studies import eye_rate_v2 as V2


def test_the_hold_out_is_a_subset_that_decides_nothing():
    assert set(V2.HOLD_OUT_FLIGHTS_S) < set(V2.FLIGHT_TARGETS_S)
    assert set(V2.FLIGHT_TARGETS_S) - set(V2.HOLD_OUT_FLIGHTS_S), "nothing left to explore with"


def test_v2_keeps_v1s_thresholds_where_it_claims_to():
    """W1, W5, W6 are meant to be v1's criteria unchanged; if a future edit
    moves one, this is where it shows up."""
    assert V2.MAX_LAUNCH_DEG is V1.MAX_LAUNCH_DEG
    assert V2.MIN_DECISION_FRAMES is V1.MIN_DECISION_FRAMES
    assert V2.MAX_RENDER_OVERHEAD is V1.MAX_RENDER_OVERHEAD
    assert V2.DETECT_THRESHOLD is V1.DETECT_THRESHOLD


def test_the_demo_swing_is_now_faster_than_v2_assumed_was_possible():
    """This assertion used to run the other way, and the flip is the point.

    VM-01 v2 fixed SWING_FLOOR_S at 25 ms by deriving it from the stance it
    had: that arm peaked at 215 rad/s in 35 ms, so 25 ms would have put it at
    the 300 rad/s ceiling. The floor was therefore a property of a STANCE, not
    of the animal, and D37 found a stance that reaches the same contact poses
    in 19 ms inside the same ceiling by travelling 122.9 degrees instead of
    260.6. v2's constant is left exactly as it was -- it records what v2
    assumed, and that is why it is worth keeping."""
    from flyohtani.world import batter as B

    assert B.DEMO_SWING_S < V2.SWING_FLOOR_S


@pytest.fixture(scope="module")
def cell() -> V2.Cell:
    return V2.measure(distance_scale=2.0, eye_resolution=64, ball_scale=4.0,
                      flight_target_s=0.08, eye_rate_hz=240)


def test_the_pitch_lasts_as_long_as_asked(cell):
    assert cell.flight_s == pytest.approx(cell.flight_target_s, rel=1e-6)
    assert cell.pitch_speed_mm_s == pytest.approx(cell.release_distance_mm / cell.flight_s, rel=1e-3)


def test_a_farther_release_flattens_the_pitch(cell):
    """The reason v2 sweeps distance upward at all."""
    near = V2.measure(distance_scale=1.0, eye_resolution=64, ball_scale=4.0,
                      flight_target_s=0.08, eye_rate_hz=240)
    assert near.launch_angle_deg > cell.launch_angle_deg


def test_centroids_exist_exactly_when_pixels_do(cell):
    for f in cell.frames:
        assert (f.centroid_rc is None) == (f.detected_px == 0)
        if f.centroid_rc is not None:
            row, col = f.centroid_rc
            assert 0 <= row < cell.eye_resolution and 0 <= col < cell.eye_resolution


def test_signal_kind_agrees_with_the_two_halves_of_w4(cell):
    expansion = cell.distinct_sizes >= V2.MIN_DISTINCT_SIZES
    motion = cell.centroid_travel_px >= V2.MIN_CENTROID_TRAVEL_PX
    assert cell.w4_signal == (expansion or motion)
    assert cell.signal_kind == {(True, True): "both", (True, False): "expansion",
                                (False, True): "motion", (False, False): "none"}[(expansion, motion)]


def test_a_finer_eye_sees_the_same_ball_in_more_pixels(cell):
    coarse = V2.measure(distance_scale=2.0, eye_resolution=32, ball_scale=4.0,
                        flight_target_s=0.08, eye_rate_hz=240)
    assert coarse.deg_per_pixel > cell.deg_per_pixel
    assert cell.peak_detected_px >= coarse.peak_detected_px

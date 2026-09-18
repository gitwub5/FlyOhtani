"""Recording module tests: the videos are files a person can open, and
making them does not change what happened."""
from __future__ import annotations

import json
import math

import pytest

imageio = pytest.importorskip("imageio.v2")

from flyohtani.record import scenarios as S
from flyohtani.world import batter as B

COARSE = {"slow_frame_s": 5e-3, "flight_frame_s": 0.05, "max_flight_s": 0.2}


@pytest.fixture(scope="module")
def unrecorded():
    return S.run_pitch(record=False)[0]


def test_froude_speed_keeps_arc_shape():
    s = B.build_scene().scale
    assert S.froude_speed(s) == pytest.approx(40_000 * math.sqrt(s))
    assert 1500 < S.froude_speed(s) < 2200


def test_scripted_pitch_meets_the_demo_swing(unrecorded):
    """Regression on the timing logic: aimed at the dry-run sweet spot, the
    ball is hit."""
    assert unrecorded.contact
    assert unrecorded.exit_speed_mm_s > 0
    assert unrecorded.landed and unrecorded.carry_mm is not None
    assert unrecorded.warnings == {}
    assert unrecorded.peak_joint_speed_rad_s < 300.0


def test_an_early_pitch_is_a_miss_and_has_no_carry():
    out, _ = S.run_pitch(S.PitchSpec(timing_ms=-3.0), record=False)
    assert not out.contact
    assert out.carry_mm is None and out.fair is None  # a miss has no batted-ball result
    assert out.landing_xy_mm is not None and out.landing_xy_mm[0] < 0  # past the plate, catcher side


def test_the_timing_window_is_narrow_and_asymmetric():
    """Measured with the D36 swing: the ball is hit from -1 to +3 ms, but
    only 0 and +1 ms are fair. Being early misses entirely, being late
    pulls the ball foul -- which is what a real timing window looks like,
    and why `fair` is what the reward pays for rather than contact."""
    early, _ = S.run_pitch(S.PitchSpec(timing_ms=-3.0), record=False)
    on_time, _ = S.run_pitch(S.PitchSpec(timing_ms=0.0), record=False)
    late, _ = S.run_pitch(S.PitchSpec(timing_ms=3.0), record=False)
    assert not early.contact
    assert on_time.contact and on_time.fair
    assert late.contact and not late.fair


def test_recording_does_not_change_the_physics(tmp_path, unrecorded):
    out, _ = S.run_pitch(record=True, out_dir=tmp_path / "run", **COARSE)
    for field in ("contact", "contact_time_ms", "exit_speed_mm_s", "launch_angle_deg"):
        assert getattr(out, field) == getattr(unrecorded, field), field


def test_run_writes_a_playable_video_stills_and_a_manifest(tmp_path):
    out_dir = tmp_path / "run"
    out, _ = S.run_pitch(record=True, out_dir=out_dir, **COARSE)
    for name in ("video.mp4", "sheet.png", "final.png", "manifest.json"):
        assert (out_dir / name).stat().st_size > 0, name
    saved = json.loads((out_dir / "manifest.json").read_text())
    assert saved["scripted"] is True
    assert saved["outcome"]["contact"] == out.contact
    reader = imageio.get_reader(out_dir / "video.mp4")
    try:
        n = sum(1 for _ in reader)
    finally:
        reader.close()
    assert n == saved["files"]["frames"]


def test_frames_have_even_dimensions_for_h264(tmp_path):
    rec_dir = tmp_path / "swing"
    manifest = S.run_swing(out_dir=rec_dir, frame_s=0.01)
    assert manifest["peak_joint_speed_rad_s"] < 300.0
    frame = imageio.imread(rec_dir / "final.png")
    assert frame.shape[0] % 2 == 0 and frame.shape[1] % 2 == 0

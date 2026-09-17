"""VM-01 V2 (user follow-up): regression tests for vision/kalman_tracker.py
-- prediction during gaps, forbidden-channel leak check (same discipline
as tests/test_vision_v1.py), and latency/age behavior.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from vision.ball_detector import Detection
from vision.kalman_tracker import KalmanBallTracker
from vision.observation import VisionObservation
from vision.tracker import Proprioception

REPO_ROOT = Path(__file__).resolve().parent.parent
PROPRIO = Proprioception(0, 0, 0, 0, 0, 0, False, None)


def _det(x, y, unc=1.0):
    return Detection(detected=True, centroid_xy_px=(x, y), n_pixels=5, uncertainty_px=unc)


MISS = Detection(detected=False, centroid_xy_px=None, n_pixels=0, uncertainty_px=float("inf"))


class TestKalmanPrediction:
    def test_constant_velocity_sequence_converges_to_true_velocity(self):
        tracker = KalmanBallTracker()
        vx_true = 100.0
        for i in range(10):
            t = i * 0.1
            obs = tracker.update(_det(10 + vx_true * t, 10.0, unc=0.5), capture_timestamp_s=t, now_s=t, proprio=PROPRIO)
        assert obs.velocity_xy_px_s is not None
        assert abs(obs.velocity_xy_px_s[0] - vx_true) < 5.0
        assert abs(obs.velocity_xy_px_s[1]) < 5.0

    def test_prediction_extrapolates_position_during_a_gap(self):
        """The core V2 requirement: unlike vision/tracker.py's BallTracker
        (which HOLDS the last position static during a miss), the Kalman
        tracker must MOVE its position estimate forward using the velocity
        it already learned, even with no new detections."""
        tracker = KalmanBallTracker()
        vx_true = 200.0
        # Feed several real detections to let the filter learn the velocity.
        for i in range(5):
            t = i * 0.05
            tracker.update(_det(vx_true * t, 0.0, unc=0.5), capture_timestamp_s=t, now_s=t, proprio=PROPRIO)

        # Now simulate a gap: no detections for 0.1s.
        t_before_gap = 4 * 0.05
        obs_before = tracker.update(MISS, capture_timestamp_s=t_before_gap + 0.01, now_s=t_before_gap + 0.01, proprio=PROPRIO)
        obs_after_gap = tracker.update(MISS, capture_timestamp_s=t_before_gap + 0.10, now_s=t_before_gap + 0.10, proprio=PROPRIO)

        assert obs_before.position_xy_px is not None
        assert obs_after_gap.position_xy_px is not None
        # Position must have MOVED forward (predicted), not stayed frozen.
        moved = obs_after_gap.position_xy_px[0] - obs_before.position_xy_px[0]
        expected_move = vx_true * (0.10 - 0.01)
        assert moved > 5.0, "position estimate did not move during the gap -- prediction is not happening"
        assert abs(moved - expected_move) < 0.3 * expected_move

    def test_uncertainty_grows_during_a_gap(self):
        tracker = KalmanBallTracker()
        for i in range(5):
            t = i * 0.05
            obs_last_detected = tracker.update(_det(10 * i, 0.0, unc=0.5), capture_timestamp_s=t, now_s=t, proprio=PROPRIO)
        obs_gap = tracker.update(MISS, capture_timestamp_s=0.3, now_s=0.3, proprio=PROPRIO)
        assert obs_gap.uncertainty_px > obs_last_detected.uncertainty_px

    def test_cold_start_with_no_detection_has_no_position(self):
        tracker = KalmanBallTracker()
        obs = tracker.update(MISS, capture_timestamp_s=0.0, now_s=0.0, proprio=PROPRIO)
        assert obs.position_xy_px is None
        assert obs.velocity_xy_px_s is None

    def test_latency_lookahead_does_not_corrupt_internal_state(self):
        """Calling update() with now_s > capture_timestamp_s (latency)
        must not permanently advance the filter's own internal clock past
        capture_timestamp_s -- the next real frame's dt should still be
        computed from the last PROCESSED capture time, not the earlier
        look-ahead."""
        tracker = KalmanBallTracker()
        tracker.update(_det(0.0, 0.0, unc=0.5), capture_timestamp_s=0.0, now_s=0.0, proprio=PROPRIO)
        tracker.update(_det(10.0, 0.0, unc=0.5), capture_timestamp_s=0.05, now_s=0.08, proprio=PROPRIO)  # 30ms latency
        assert tracker.last_t == pytest.approx(0.05)


class TestNoForbiddenChannelLeak:
    def test_vision_observation_has_no_forbidden_fields(self):
        forbidden = {"ball_pos", "ball_vel", "remaining", "course", "phase", "end_reason", "scoring_valid"}
        assert forbidden.isdisjoint(VisionObservation.__dataclass_fields__.keys())

    def test_kalman_tracker_never_imports_evaluator_or_env(self):
        source = (REPO_ROOT / "vision" / "kalman_tracker.py").read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden_prefixes = ("vision.evaluator", "envs.")
        leaked = [m for m in imported if any(m == p or m.startswith(p) for p in forbidden_prefixes)]
        assert not leaked, f"kalman_tracker.py imports forbidden module(s): {leaked}"

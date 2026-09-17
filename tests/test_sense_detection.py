"""Sense-layer regression tests that need no simulator: synthetic-frame
detection, the clock/latency/age contract, the forbidden-channel leak
checks, and the evaluator's projection math.

The v1 counterparts of these tests also covered REAL RENDER tracking and
camera-head-following against the old 3-axis rig. Those are deliberately
absent, not silently dropped: the rig they rendered is gone, and Phase 1/3
(docs/PLAN.md) must bring them back against the NeuroMechFly-jointed body
before any detection number is reported again.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from flyohtani.sense.ball_detector import BALL_COLOR_RGB, BallDetector, Detection
from flyohtani.sense.evaluator import project_world_point
from flyohtani.sense.observation import VisionObservation
from flyohtani.sense.tracker import BallTracker, Proprioception

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestSyntheticMovingPoint:
    def test_detects_known_position_in_synthetic_frame(self):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[..., 1] = 100  # greenish background, not red
        true_x, true_y = 40, 20
        frame[true_y - 1 : true_y + 2, true_x - 1 : true_x + 2] = BALL_COLOR_RGB.astype(np.uint8)

        det = BallDetector().detect(frame)
        assert det.detected
        assert abs(det.centroid_xy_px[0] - true_x) < 1.0
        assert abs(det.centroid_xy_px[1] - true_y) < 1.0

    def test_moving_synthetic_point_tracked_across_frames(self):
        detector = BallDetector()
        tracker = BallTracker()
        proprio = Proprioception(0, 0, 0, 0, 0, 0, False, None)
        positions = [(10, 10), (20, 10), (30, 10), (40, 10)]
        estimated_velocities = []
        for i, (x, y) in enumerate(positions):
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            frame[y - 1 : y + 2, x - 1 : x + 2] = BALL_COLOR_RGB.astype(np.uint8)
            det = detector.detect(frame)
            t = i * 0.1
            obs = tracker.update(det, capture_timestamp_s=t, now_s=t, proprio=proprio)
            assert obs.detected
            if obs.velocity_xy_px_s is not None:
                estimated_velocities.append(obs.velocity_xy_px_s)
        # True velocity is (10px / 0.1s, 0) = (100, 0) px/s.
        assert len(estimated_velocities) >= 2
        vx, vy = estimated_velocities[-1]
        assert abs(vx - 100.0) < 5.0
        assert abs(vy) < 5.0

    def test_white_object_is_not_falsely_detected_as_red(self):
        """Regression for the color-confusion bug found while running
        v1's first render run: an earlier cosine-similarity-based
        redness score gave white pixels ~0.77 similarity to the ball's red
        (ABOVE that version's 0.55 threshold), causing the scene's own
        white foul line to dominate detection with 60-170px position
        error. "Excess red" (current implementation) must not do this."""
        frame = np.full((32, 32, 3), 240, dtype=np.uint8)  # pure bright white/gray
        det = BallDetector().detect(frame)
        assert not det.detected




class TestClockLatencyAge:
    def test_age_grows_when_no_new_detection_and_resets_on_new_one(self):
        tracker = BallTracker()
        proprio = Proprioception(0, 0, 0, 0, 0, 0, False, None)
        det_hit = Detection(detected=True, centroid_xy_px=(10.0, 10.0), n_pixels=5, uncertainty_px=1.0)
        det_miss = Detection(detected=False, centroid_xy_px=None, n_pixels=0, uncertainty_px=float("inf"))

        obs0 = tracker.update(det_hit, capture_timestamp_s=0.0, now_s=0.0, proprio=proprio)
        assert obs0.age_s == 0.0
        assert obs0.position_xy_px == (10.0, 10.0)

        obs1 = tracker.update(det_miss, capture_timestamp_s=0.05, now_s=0.05, proprio=proprio)
        assert obs1.detected is False
        assert obs1.position_xy_px == (10.0, 10.0)  # last valid estimate carried forward, per the tracker's age/uncertainty contract
        assert obs1.age_s > 0.0
        assert obs1.uncertainty_px > obs0.uncertainty_px  # uncertainty grows with age

        obs2 = tracker.update(det_hit, capture_timestamp_s=0.10, now_s=0.10, proprio=proprio)
        assert obs2.age_s == 0.0
        assert obs2.uncertainty_px == pytest.approx(1.0)

    def test_latency_reported_as_age_when_now_is_later_than_capture(self):
        tracker = BallTracker()
        proprio = Proprioception(0, 0, 0, 0, 0, 0, False, None)
        det_hit = Detection(detected=True, centroid_xy_px=(5.0, 5.0), n_pixels=3, uncertainty_px=1.0)
        obs = tracker.update(det_hit, capture_timestamp_s=1.000, now_s=1.015, proprio=proprio)
        assert obs.age_s == pytest.approx(0.015)

    def test_cold_start_has_no_position(self):
        tracker = BallTracker()
        proprio = Proprioception(0, 0, 0, 0, 0, 0, False, None)
        det_miss = Detection(detected=False, centroid_xy_px=None, n_pixels=0, uncertainty_px=float("inf"))
        obs = tracker.update(det_miss, capture_timestamp_s=0.0, now_s=0.0, proprio=proprio)
        assert obs.position_xy_px is None
        assert obs.velocity_xy_px_s is None


class TestNoForbiddenChannelLeak:
    def test_vision_observation_has_no_forbidden_fields(self):
        forbidden = {"ball_pos", "ball_vel", "remaining", "course", "phase", "end_reason", "scoring_valid"}
        assert forbidden.isdisjoint(VisionObservation.__dataclass_fields__.keys())

    @pytest.mark.parametrize("module_name", ["ball_detector", "tracker", "observation"])
    def test_policy_path_modules_never_import_evaluator_or_world(self, module_name):
        """Static (AST-based, not just grep) check: the modules a policy's
        code path would import must not import the evaluator (ground-truth
        only) nor any world/task module (which would make a ground-truth
        state read possible even if unused today).

        `flyohtani.world` and `flyohtani.task` do not exist yet -- they
        arrive in Phase 2/5. Listing them now is the point: the check is in
        place BEFORE the module that could leak exists.
        """
        source = (REPO_ROOT / "flyohtani" / "sense" / f"{module_name}.py").read_text()
        tree = ast.parse(source)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        forbidden_prefixes = ("flyohtani.sense.evaluator", "flyohtani.world", "flyohtani.task")
        leaked = [m for m in imported_modules if any(m == p or m.startswith(p) for p in forbidden_prefixes)]
        assert not leaked, f"{module_name}.py imports forbidden module(s): {leaked}"

    def test_detected_false_never_carries_a_ground_truth_fallback(self):
        # A cold-start miss must report None, never some default/zero
        # position that could be mistaken for a real (if wrong) estimate.
        tracker = BallTracker()
        proprio = Proprioception(0, 0, 0, 0, 0, 0, False, None)
        det_miss = Detection(detected=False, centroid_xy_px=None, n_pixels=0, uncertainty_px=float("inf"))
        obs = tracker.update(det_miss, capture_timestamp_s=0.0, now_s=0.0, proprio=proprio)
        assert obs.position_xy_px is None

class TestProjectionMath:
    def test_point_directly_in_front_projects_to_image_center(self):
        cam_pos = np.array([0.0, 0.0, 0.0])
        cam_mat = np.eye(3)  # right=+X, up=+Y, backward=+Z -> forward=-Z
        point = np.array([0.0, 0.0, -5.0])  # 5m in front
        proj = project_world_point(point, cam_pos, cam_mat, fovy_deg=90.0, width=100, height=100)
        assert proj.visible_in_frame
        assert proj.pixel_xy == pytest.approx((50.0, 50.0), abs=1e-6)

    def test_point_behind_camera_is_not_visible(self):
        cam_pos = np.array([0.0, 0.0, 0.0])
        cam_mat = np.eye(3)
        point = np.array([0.0, 0.0, 5.0])  # behind
        proj = project_world_point(point, cam_pos, cam_mat, fovy_deg=90.0, width=100, height=100)
        assert not proj.visible_in_frame

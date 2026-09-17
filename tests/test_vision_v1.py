"""VM-01 V1 (docs/tasks/VISUOMOTOR-PIVOT.md item 8): synthetic moving-point
unit test, real render tracking, camera head-following, clock/latency/age,
and forbidden-channel leak checks. Passing scripts/vm01_vision_baseline.py
once is not treated as validating this pipeline -- these are the actual
regression tests re-run on every `pytest`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import mujoco
import numpy as np
import pytest

from controllers.baseball_kc01a import ZeroTorqueController
from envs.baseball_kc01a_env import BaseballKC01aEnv
from vision.ball_detector import BALL_COLOR_RGB, BallDetector, Detection
from vision.evaluator import ball_ground_truth_pixel, project_world_point
from vision.eye_camera import EyeCamera
from vision.observation import VisionObservation
from vision.tracker import BallTracker, Proprioception

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
        scripts/vm01_vision_baseline.py: an earlier cosine-similarity-based
        redness score gave white pixels ~0.77 similarity to the ball's red
        (ABOVE that version's 0.55 threshold), causing the scene's own
        white foul line to dominate detection with 60-170px position
        error. "Excess red" (current implementation) must not do this."""
        frame = np.full((32, 32, 3), 240, dtype=np.uint8)  # pure bright white/gray
        det = BallDetector().detect(frame)
        assert not det.detected


class TestRealRenderTracking:
    def test_pitch_tracking_error_reasonable_near_contact(self):
        env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
        try:
            env.model.geom_contype[env.bat_geom_id] = 0
            env.model.geom_conaffinity[env.bat_geom_id] = 0
            cam_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_cam")
            env.model.cam_fovy[cam_id] = 60.0
            camera = EyeCamera(env.model, width=320, height=320, fps_hz=60.0)
            detector = BallDetector()
            controller = ZeroTorqueController()
            obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
            controller.reset()

            last_error = None
            step_i = 0
            while True:
                action = controller.act(obs)
                obs, _, terminated, truncated, _info = env.step(action)
                step_i += 1
                if step_i % 3 == 0:
                    frame, _manifest = camera.capture(env.data, grayscale=False)
                    det = detector.detect(frame)
                    gt = ball_ground_truth_pixel(env.model, env.data, env.ball_body_id, "eye_cam", 320, 320)
                    if det.detected and gt.pixel_xy is not None:
                        last_error = float(np.linalg.norm(np.array(det.centroid_xy_px) - np.array(gt.pixel_xy)))
                if terminated or truncated:
                    break
            camera.close()
            assert last_error is not None, "expected at least one detection near contact at 320px/60deg (docs/records/evidence/VM01-vision-baseline.json's own best-recall candidate)"
            assert last_error < 5.0
        finally:
            env.close()


class TestCameraFollowsHead:
    def test_position_nearly_stationary_direction_rotates_with_torso(self):
        env = BaseballKC01aEnv()
        try:
            env.reset(seed=0, options={"course": "mid_mid"})
            m, d = env.model, env.data
            cam_id = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "eye_cam")
            pos0 = d.cam_xpos[cam_id].copy()
            fwd0 = -d.cam_xmat[cam_id].reshape(3, 3)[:, 2].copy()

            d.qpos[env.torso_qpos_adr] = 0.3
            mujoco.mj_forward(m, d)
            pos1 = d.cam_xpos[cam_id].copy()
            fwd1 = -d.cam_xmat[cam_id].reshape(3, 3)[:, 2].copy()

            assert np.linalg.norm(pos1 - pos0) < 0.05  # eye is close to the torso_yaw axis
            angle0 = np.arctan2(fwd0[1], fwd0[0])
            angle1 = np.arctan2(fwd1[1], fwd1[0])
            assert abs((angle1 - angle0) - 0.3) < 0.01  # forward direction rotates BY torso_yaw's own delta
        finally:
            env.close()

    def test_projection_matches_a_rendered_bright_marker(self):
        """Verifies vision/evaluator.py's pinhole math against an actual
        rendered pixel location, not just algebra: places the ball at a
        known position, renders, finds its brightest/reddest pixel, and
        checks it's close to the formula's own prediction."""
        env = BaseballKC01aEnv()
        try:
            env.reset(seed=0, options={"course": "mid_mid"})
            m, d = env.model, env.data
            d.qpos[env.ball_qpos_adr : env.ball_qpos_adr + 3] = [3.0, 0.0, 1.2]
            d.qvel[env.ball_qvel_adr : env.ball_qvel_adr + 6] = 0.0
            mujoco.mj_forward(m, d)

            camera = EyeCamera(m, width=200, height=200, fps_hz=60.0)
            frame, _manifest = camera.capture(d, grayscale=False)
            camera.close()

            det = BallDetector().detect(frame)
            gt = ball_ground_truth_pixel(m, d, env.ball_body_id, "eye_cam", 200, 200)
            assert det.detected
            assert gt.pixel_xy is not None
            error = np.linalg.norm(np.array(det.centroid_xy_px) - np.array(gt.pixel_xy))
            assert error < 3.0
        finally:
            env.close()


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
        assert obs1.position_xy_px == (10.0, 10.0)  # last valid estimate carried forward, per VISION-01 section 5
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
    def test_policy_path_modules_never_import_evaluator_or_env(self, module_name):
        """Static (AST-based, not just grep) check: the modules a policy's
        code path would import must not import vision.evaluator (ground-
        truth-only) or any envs.* module (which would make a ground-truth
        state read possible even if unused today)."""
        source = (REPO_ROOT / "vision" / f"{module_name}.py").read_text()
        tree = ast.parse(source)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        forbidden_prefixes = ("vision.evaluator", "envs.")
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
        assert proj.behind_camera

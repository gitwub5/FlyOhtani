"""VM-01 V2 (user follow-up): evaluates vision/kalman_tracker.py's
prediction against the same occlusion/latency/miss conditions
scripts/vm01_vision_diagnostics.py already used for the plain BallTracker,
and DIRECTLY compares the two trackers' POSITION ERROR against the
evaluator-only ground truth during occlusion windows (where prediction
should matter) -- not just detection rate, which is a per-frame detector
property unaffected by which tracker consumes its output.

Ground truth is read ONLY here (this script), via vision.evaluator, to
score both trackers -- neither tracker module itself ever imports it
(tests/test_vision_v2.py checks this statically, same as V1).
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from controllers.baseball_kc01a import ZeroTorqueController
from envs.baseball_kc01a_env import BaseballKC01aEnv
from vision.ball_detector import BallDetector
from vision.evaluator import ball_ground_truth_pixel
from vision.eye_camera import EyeCamera
from vision.kalman_tracker import KalmanBallTracker
from vision.tracker import BallTracker, Proprioception

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

WIDTH, HEIGHT, FOVY = 320, 320, 60.0  # best-recall baseline candidate, docs/records/evidence/VM01-vision-baseline.json
FPS = 60.0
CONTROL_HZ = 200.0
TEST_SEEDS = [10, 11, 12, 13, 14]
OCCLUDE_WINDOW = (0.35, 0.42)


def run_pitch(seed: int, tracker, occlude_window=None) -> list[dict]:
    rng = np.random.default_rng(seed)
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0
        cam_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_cam")
        env.model.cam_fovy[cam_id] = FOVY
        env.RELEASE = env.RELEASE + rng.normal(0, 0.1, size=3)  # same jitter scale as scripts/vm01_vision_diagnostics.py

        camera = EyeCamera(env.model, width=WIDTH, height=HEIGHT, fps_hz=FPS)
        detector = BallDetector()
        controller = ZeroTorqueController()
        obs, _ = env.reset(seed=seed, options={"course": "mid_mid"})
        controller.reset()

        capture_every_n_steps = max(1, round(CONTROL_HZ / FPS))
        rows = []
        step_i = 0
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, _info = env.step(action)
            step_i += 1
            if step_i % capture_every_n_steps == 0:
                t = float(env.data.time)
                frame_rgb, _manifest = camera.capture(env.data, grayscale=False)
                occluded = occlude_window is not None and occlude_window[0] <= t <= occlude_window[1]
                frame_to_use = np.zeros_like(frame_rgb) if occluded else frame_rgb
                det = detector.detect(frame_to_use)
                gt = ball_ground_truth_pixel(env.model, env.data, env.ball_body_id, "eye_cam", WIDTH, HEIGHT)
                proprio = Proprioception(
                    float(env.data.qpos[env.torso_qpos_adr]), float(env.data.qvel[env.torso_qvel_adr]),
                    float(env.data.qpos[env.swing_qpos_adr]), float(env.data.qvel[env.swing_qvel_adr]),
                    float(env.data.qpos[env.tilt_qpos_adr]), float(env.data.qvel[env.tilt_qvel_adr]),
                    False, None,
                )
                track_obs = tracker.update(det, capture_timestamp_s=t, now_s=t, proprio=proprio)
                error_px = None
                if track_obs.position_xy_px is not None and gt.pixel_xy is not None:
                    error_px = float(np.linalg.norm(np.array(track_obs.position_xy_px) - np.array(gt.pixel_xy)))
                rows.append({"t": t, "occluded": occluded, "gt_visible": gt.visible_in_frame, "detected": det.detected, "tracker_error_px": error_px})
            if terminated or truncated:
                break
        camera.close()
        return rows
    finally:
        env.close()


def summarize(all_rows: list[dict]) -> dict:
    occ = [r for r in all_rows if r["occluded"] and r["gt_visible"] and r["tracker_error_px"] is not None]
    normal = [r for r in all_rows if not r["occluded"] and r["gt_visible"] and r["tracker_error_px"] is not None]
    return {
        "n_occluded_scored": len(occ),
        "n_normal_scored": len(normal),
        "mean_error_px_during_occlusion": float(np.mean([r["tracker_error_px"] for r in occ])) if occ else None,
        "median_error_px_during_occlusion": float(np.median([r["tracker_error_px"] for r in occ])) if occ else None,
        "mean_error_px_normal": float(np.mean([r["tracker_error_px"] for r in normal])) if normal else None,
    }


def main() -> None:
    result = {}
    for tracker_name, tracker_factory in (("BallTracker_hold_last", BallTracker), ("KalmanBallTracker_predict", KalmanBallTracker)):
        print(f"=== {tracker_name}, occlusion window {OCCLUDE_WINDOW} ===")
        all_rows = []
        for seed in TEST_SEEDS:
            tracker = tracker_factory()
            all_rows.extend(run_pitch(seed, tracker, occlude_window=OCCLUDE_WINDOW))
        s = summarize(all_rows)
        result[tracker_name] = s
        print(json.dumps(s, indent=2, default=str))

    old_err = result["BallTracker_hold_last"]["mean_error_px_during_occlusion"]
    new_err = result["KalmanBallTracker_predict"]["mean_error_px_during_occlusion"]
    print(f"\nDuring occlusion: hold-last mean error={old_err}px, Kalman-predict mean error={new_err}px")
    if old_err is not None and new_err is not None:
        print(f"  improvement: {old_err - new_err:.3f}px ({'better' if new_err < old_err else 'NOT better'})")
    result["comparison_note"] = (
        "This compares position error DURING an occlusion window specifically -- where a "
        "velocity-based prediction should help most (the ball keeps moving; holding the last "
        "position does not). Outside occlusion, both trackers see the same per-frame detections "
        "and are not expected to differ much."
    )

    out_path = OUT_DIR / "VM01-V2-tracking-comparison.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

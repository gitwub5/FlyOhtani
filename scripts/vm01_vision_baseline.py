"""VM-01 V1 (docs/tasks/VISUOMOTOR-PIVOT.md): read-only, non-contact
diagnostic -- renders the mid_mid pitch from the head-mounted eye camera
(vision/eye_camera.py, camera="eye_cam") across the resolution/FOV
candidates docs/design/VISION-01.md section 2 already proposed, runs the
classical ball_detector.py on every captured frame, and scores it against
the evaluator-only ground-truth pixel projection (vision/evaluator.py).
Does NOT wait for KC batting convergence -- bat collision is disabled
(same contype/conaffinity=0 technique already used by scripts/
kc01a_settle_diagnostics.py's run_noball_swing) and the controller is
ZeroTorqueController, so this only exercises the pitch, never a swing.

Outputs, kept SEPARATE from B1/KC output/profile paths (docs/tasks/
VISUOMOTOR-PIVOT.md V1 item 2):
- docs/records/evidence/VM01-vision-baseline.json: per-candidate detection
  metrics (position error / precision / recall / uncertainty, binned by
  distance).
- runs/vm01-vision/<candidate>/frame_*.png (gitignored): a handful of
  sample frames per candidate for visual sanity-check, NOT the full
  recording (thousands of frames would bloat runs/ for no analytical
  benefit beyond what the metrics already capture).

No text/score overlay is drawn on these frames (docs/tasks/
VISUOMOTOR-PIVOT.md V1 item 3: "정책 영상에 텍스트 overlay를 넣지 않는다") --
this is the actual would-be-policy-facing image, saved for eyeballing, not
a human-debug annotated demo video like demos/record_*.py's overlays.
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

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
RUNS_DIR = Path(__file__).resolve().parent.parent / "runs" / "vm01-vision"

CONTROL_HZ = 200.0  # 1 / (timestep * frame_skip) at KC-01a defaults

RESOLUTION_CANDIDATES = [128, 320]
FOVY_CANDIDATES = [60.0, 90.0]
BASELINE_FPS = 60.0
HIGH_FPS = 120.0


def run_candidate(width: int, height: int, fovy_deg: float, fps_hz: float) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0
        cam_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_cam")
        env.model.cam_fovy[cam_id] = fovy_deg

        camera = EyeCamera(env.model, width=width, height=height, fps_hz=fps_hz)
        detector = BallDetector()

        controller = ZeroTorqueController()
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        capture_every_n_steps = max(1, round(CONTROL_HZ / fps_hz))
        actual_fps = CONTROL_HZ / capture_every_n_steps

        sample_dir = RUNS_DIR / f"res{width}_fovy{int(fovy_deg)}_fps{int(fps_hz)}"
        sample_dir.mkdir(parents=True, exist_ok=True)
        n_saved_frames = 0
        max_saved_frames = 5

        rows = []
        step_i = 0
        info = {}
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            step_i += 1
            if step_i % capture_every_n_steps == 0:
                frame_rgb, manifest = camera.capture(env.data, grayscale=False)
                det = detector.detect(frame_rgb)
                gt = ball_ground_truth_pixel(env.model, env.data, env.ball_body_id, "eye_cam", width, height)

                pixel_error = None
                if det.detected and gt.pixel_xy is not None:
                    pixel_error = float(np.linalg.norm(np.array(det.centroid_xy_px) - np.array(gt.pixel_xy)))

                rows.append(
                    {
                        "t": manifest.capture_timestamp_s,
                        "distance_m": gt.distance_m,
                        "gt_visible_in_frame": gt.visible_in_frame,
                        "detected": det.detected,
                        "n_pixels": det.n_pixels,
                        "uncertainty_px": det.uncertainty_px,
                        "pixel_error_px": pixel_error,
                    }
                )
                if n_saved_frames < max_saved_frames and step_i % (capture_every_n_steps * 20) == 0:
                    import imageio

                    imageio.imwrite(sample_dir / f"frame_t{manifest.capture_timestamp_s:.3f}.png", frame_rgb)
                    n_saved_frames += 1
            if terminated or truncated:
                break
        camera.close()

        return {
            "width": width,
            "height": height,
            "fovy_deg": fovy_deg,
            "requested_fps_hz": fps_hz,
            "actual_fps_hz": actual_fps,
            "n_frames": len(rows),
            "rows": rows,
            "end_reason": info.get("end_reason"),
        }
    finally:
        env.close()


def summarize(candidate_result: dict) -> dict:
    rows = candidate_result["rows"]
    gt_visible = [r for r in rows if r["gt_visible_in_frame"]]
    detected = [r for r in rows if r["detected"]]
    true_positive = [r for r in rows if r["detected"] and r["gt_visible_in_frame"]]
    false_positive = [r for r in rows if r["detected"] and not r["gt_visible_in_frame"]]

    precision = len(true_positive) / len(detected) if detected else None
    recall = len(true_positive) / len(gt_visible) if gt_visible else None

    errors = [r["pixel_error_px"] for r in true_positive if r["pixel_error_px"] is not None]

    # Bin by distance (near/mid/far thirds of the observed range).
    distances = [r["distance_m"] for r in gt_visible]
    bins: dict[str, dict] = {}
    if distances:
        d_min, d_max = min(distances), max(distances)
        edges = [d_min, d_min + (d_max - d_min) / 3, d_min + 2 * (d_max - d_min) / 3, d_max + 1e-9]
        labels = ["near", "mid", "far"]  # ascending distance_m order: small distance = near the eye (late flight), large = far (early flight)
        for lo, hi, label in zip(edges[:-1], edges[1:], labels):
            in_bin = [r for r in gt_visible if lo <= r["distance_m"] < hi]
            det_in_bin = [r for r in in_bin if r["detected"]]
            bins[label] = {
                "distance_range_m": [lo, hi],
                "n": len(in_bin),
                "detection_rate": (len(det_in_bin) / len(in_bin)) if in_bin else None,
                "mean_n_pixels": float(np.mean([r["n_pixels"] for r in in_bin])) if in_bin else None,
            }

    return {
        "n_frames": len(rows),
        "n_gt_visible": len(gt_visible),
        "n_detected": len(detected),
        "n_true_positive": len(true_positive),
        "n_false_positive": len(false_positive),
        "precision": precision,
        "recall": recall,
        "mean_pixel_error_px": float(np.mean(errors)) if errors else None,
        "median_pixel_error_px": float(np.median(errors)) if errors else None,
        "by_distance_bin": bins,
    }


def main() -> None:
    result = {"candidates": []}
    print("=== VM-01 V1: vision baseline (resolution x FOV, read-only, non-contact) ===")
    for width in RESOLUTION_CANDIDATES:
        for fovy in FOVY_CANDIDATES:
            print(f"  running width={width} fovy={fovy} fps={BASELINE_FPS} ...")
            r = run_candidate(width, width, fovy, BASELINE_FPS)
            s = summarize(r)
            print(f"    n_frames={s['n_frames']} n_gt_visible={s['n_gt_visible']} precision={s['precision']} recall={s['recall']} mean_err_px={s['mean_pixel_error_px']}")
            result["candidates"].append({"config": {"width": width, "height": width, "fovy_deg": fovy, "fps_hz": BASELINE_FPS}, "summary": s})

    # One high-fps comparison at the baseline resolution/FOV.
    print(f"  running width=128 fovy=90 fps={HIGH_FPS} (fps comparison) ...")
    r = run_candidate(128, 128, 90.0, HIGH_FPS)
    s = summarize(r)
    result["candidates"].append({"config": {"width": 128, "height": 128, "fovy_deg": 90.0, "fps_hz": HIGH_FPS}, "summary": s})

    out_path = OUT_DIR / "VM01-vision-baseline.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

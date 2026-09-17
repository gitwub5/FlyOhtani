"""VM-01 V1 item 6 (docs/tasks/VISUOMOTOR-PIVOT.md): a SEPARATE diagnostic
profile checking "timetable memorization" vs real visual detection --
release-time/position/velocity jitter, occlusion, freeze, and delay. This
is the approved observation-evaluation scope V1 item 6 itself names
("승인된 관측 평가 범위"), explicitly distinct from the (not-started)
8-course/curveball work. dev/test split and ranges are fixed BEFORE
running (below), and this script never tunes vision/ball_detector.py's
threshold using these results (that would be evaluating on the tuning
set).
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

# Pre-registered BEFORE running: dev seeds used to pick nothing (the
# detector has no learned/tunable parameter this round besides the fixed
# REDNESS_THRESHOLD, which was fixed by the color-confusion bug fix, not
# by these results) -- test seeds are what is actually reported.
DEV_SEEDS = [0, 1]
TEST_SEEDS = [10, 11, 12, 13, 14]
RELEASE_JITTER_STD_M = 0.1  # +-10cm on release position, a modest fraction of the 16.5m release distance
VELOCITY_JITTER_STD_FRAC = 0.02  # +-2% on release velocity components

WIDTH, HEIGHT, FOVY = 320, 320, 60.0  # the best-recall baseline candidate from scripts/vm01_vision_baseline.py
FPS = 60.0
CONTROL_HZ = 200.0


def run_pitch_with_release_jitter(seed: int, occlude_window=None, freeze_window=None, latency_ticks: int = 0) -> dict:
    """occlude_window/freeze_window: (t_start, t_end) in seconds, or None.
    latency_ticks: whole CONTROL ticks (5ms) of delay between capture and
    the detector/tracker actually processing that frame -- modeled by
    simply DELAYING when a captured frame is handed to the detector,
    exactly matching VISION-01 section 5's "1 control tick / 3 tick"
    latency candidates (here: an arbitrary integer, not necessarily 1 or
    3, to see the effect scale honestly rather than only at the two
    proposed candidates)."""
    rng = np.random.default_rng(seed)
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0
        cam_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_cam")
        env.model.cam_fovy[cam_id] = FOVY

        # Jitter release position/velocity -- a genuinely different physical
        # trajectory per seed, not a relabeled replay of the same one.
        jitter_pos = rng.normal(0, RELEASE_JITTER_STD_M, size=3)
        env.RELEASE = env.RELEASE + jitter_pos
        # HORIZONTAL_SPEED jitter changes flight time/velocity together
        # (reset() derives ball_vel from RELEASE/target/flight_time itself,
        # so jittering HORIZONTAL_SPEED is the correct lever, not qvel
        # post-hoc which reset() would overwrite).
        env.HORIZONTAL_SPEED = env.HORIZONTAL_SPEED * (1.0 + rng.normal(0, VELOCITY_JITTER_STD_FRAC))

        camera = EyeCamera(env.model, width=WIDTH, height=HEIGHT, fps_hz=FPS)
        detector = BallDetector()
        controller = ZeroTorqueController()
        obs, _ = env.reset(seed=seed, options={"course": "mid_mid"})
        controller.reset()

        capture_every_n_steps = max(1, round(CONTROL_HZ / FPS))
        pending_frames: list[tuple[float, np.ndarray]] = []  # (capture_t, frame) queue for latency modeling
        rows = []
        step_i = 0
        frozen_frame = None
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, _info = env.step(action)
            step_i += 1
            if step_i % capture_every_n_steps == 0:
                t = float(env.data.time)
                frame_rgb, _manifest = camera.capture(env.data, grayscale=False)

                if freeze_window is not None and freeze_window[0] <= t <= freeze_window[1]:
                    if frozen_frame is None:
                        frozen_frame = frame_rgb.copy()
                    frame_to_use = frozen_frame
                elif occlude_window is not None and occlude_window[0] <= t <= occlude_window[1]:
                    frame_to_use = np.zeros_like(frame_rgb)  # simulates the bat/arm fully blocking the eye
                else:
                    frame_to_use = frame_rgb
                    frozen_frame = None

                pending_frames.append((t, frame_to_use))
                if len(pending_frames) > latency_ticks:
                    capture_t, delayed_frame = pending_frames.pop(0)
                    det = detector.detect(delayed_frame)
                    gt = ball_ground_truth_pixel(env.model, env.data, env.ball_body_id, "eye_cam", WIDTH, HEIGHT)
                    rows.append(
                        {
                            "capture_t": capture_t,
                            "processed_t": t,
                            "latency_s": t - capture_t,
                            "detected": det.detected,
                            "gt_visible": gt.visible_in_frame,
                            "occluded": occlude_window is not None and occlude_window[0] <= capture_t <= occlude_window[1],
                            "frozen": freeze_window is not None and freeze_window[0] <= capture_t <= freeze_window[1],
                        }
                    )
            if terminated or truncated:
                break
        camera.close()
        return {"seed": seed, "rows": rows, "release_jitter_m": jitter_pos.tolist()}
    finally:
        env.close()


def summarize_condition(name: str, seeds: list[int], **kwargs) -> dict:
    runs = [run_pitch_with_release_jitter(s, **kwargs) for s in seeds]
    all_rows = [r for run in runs for r in run["rows"]]
    occluded_rows = [r for r in all_rows if r["occluded"]]
    frozen_rows = [r for r in all_rows if r["frozen"]]
    normal_rows = [r for r in all_rows if not r["occluded"] and not r["frozen"]]

    def detect_rate(rows):
        gt_visible = [r for r in rows if r["gt_visible"]]
        return (sum(r["detected"] for r in gt_visible) / len(gt_visible)) if gt_visible else None

    return {
        "condition": name,
        "seeds": seeds,
        "n_runs": len(runs),
        "n_total_frames": len(all_rows),
        "detect_rate_normal_windows": detect_rate(normal_rows),
        "detect_rate_occluded_window": detect_rate(occluded_rows) if occluded_rows else None,
        "detect_rate_frozen_window": detect_rate(frozen_rows) if frozen_rows else None,
        "n_occluded_frames": len(occluded_rows),
        "n_frozen_frames": len(frozen_rows),
    }


def main() -> None:
    result = {}
    print("=== VM-01 V1 item 6: release jitter (baseline, no occlusion/freeze) ===")
    result["release_jitter_baseline"] = summarize_condition("release_jitter_baseline", TEST_SEEDS)
    print(json.dumps(result["release_jitter_baseline"], indent=2, default=str))

    print("\n=== occlusion window (0.35s-0.42s, simulating bat/arm blocking the eye) ===")
    result["occlusion"] = summarize_condition("occlusion", TEST_SEEDS, occlude_window=(0.35, 0.42))
    print(json.dumps(result["occlusion"], indent=2, default=str))
    occ = result["occlusion"]
    print(f"  detect_rate DURING occlusion: {occ['detect_rate_occluded_window']} (should be near 0 -- occlusion must actually suppress detection, not be ignored)")

    print("\n=== freeze window (0.35s-0.42s, repeating the last captured frame) ===")
    result["freeze"] = summarize_condition("freeze", TEST_SEEDS, freeze_window=(0.35, 0.42))
    print(json.dumps(result["freeze"], indent=2, default=str))
    print(
        "  NOTE (docs/tasks/VISUOMOTOR-PIVOT.md V1 item 7's own caution): a freeze window showing "
        "the SAME detect_rate as normal frames does not by itself mean 'vision is unused' -- the "
        "detector here is a per-frame classical detector with no temporal memory, so freezing the "
        "input to a frame where the ball WAS visible correctly keeps detecting it (the frozen pixels "
        "still show a ball-colored blob at the frozen position). What freezing tests is whether "
        "age_s and the tracker's position ESTIMATE stop updating (checked in tests/test_vision_v1.py), "
        "not the per-frame detector's own hit rate."
    )

    print("\n=== latency (0/1/3 control ticks = 0/5/15ms) ===")
    latency_results = {}
    for ticks in (0, 1, 3):
        r = summarize_condition(f"latency_{ticks}_ticks", TEST_SEEDS, latency_ticks=ticks)
        latency_results[str(ticks)] = r
        print(f"  latency={ticks} ticks: detect_rate={r['detect_rate_normal_windows']}")
    result["latency"] = latency_results

    out_path = OUT_DIR / "VM01-vision-diagnostics.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

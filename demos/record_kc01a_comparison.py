"""KC-01a deliverable: same-camera comparison video across the 4
coordination conditions (docs/design/KC-01a-TORSO-BAT-COORDINATION.md
section 6). Same camera, same playback rate, mid_mid only -- mirrors
demos/record_i07c_before_after.py's approach for B1. Each condition's
video is saved separately (same camera set) plus a manifest with the
outcome metrics, so comparison-video and comparison-table stay linked to
the same run.
"""
from __future__ import annotations

import json
from pathlib import Path

import imageio
import numpy as np
from PIL import Image, ImageDraw

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

CAMERAS = ["park_wide", "batter_side"]

CONDITIONS = {
    "arm_only": {"torso_target": 0.0, "swing_target": -1.298, "torso_ct": 999.0, "swing_ct": 0.09425316355759385},
    "torso_only": {"torso_target": 0.496, "swing_target": -1.96, "torso_ct": 0.360, "swing_ct": 999.0},
    "simultaneous": {"torso_target": -0.4, "swing_target": -0.726, "torso_ct": 0.096, "swing_ct": 0.096},
    "staggered": {"torso_target": -0.4, "swing_target": -0.726, "torso_ct": 0.242, "swing_ct": 0.122},
}


def _overlay_text(frame: np.ndarray, lines: list[str]) -> np.ndarray:
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    y = 10
    for line in lines:
        draw.rectangle([8, y - 2, 8 + 9 * len(line), y + 16], fill=(0, 0, 0))
        draw.text((10, y), line, fill=(255, 255, 0))
        y += 20
    return np.array(img)


def run_and_record(label: str, mode: str, cfg: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = BaseballKC01aEnv(render_mode="rgb_array", prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = TorsoBatController(
            mode, 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        frames: dict[str, list[np.ndarray]] = {cam: [] for cam in CAMERAS}
        info: dict = {}

        def capture(status: str, dist_line: str) -> None:
            for cam in CAMERAS:
                raw = env.render_rgb(cam)
                frames[cam].append(_overlay_text(raw, [f"KC-01a: {label}", f"status: {status}", dist_line]))

        capture("pitch", "distance: --")
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                if info["status"] == "incomplete":
                    status, dist_line = "undetermined", "distance: undetermined (incomplete)"
                elif info["batting_score"] is not None and info["batting_score"] > 0.0:
                    status, dist_line = "landed", f"score: {info['batting_score']:.1f}m (valid)"
                else:
                    status, dist_line = "landed" if info["end_reason"] == "batted_ball_landing" else "miss", "score: 0.0 (invalid/no hit)"
            elif info["contact_occurred"] and info["phase"] == "batted_ball":
                status, dist_line = "in-flight", "distance: (in-flight, not final)"
            elif info["phase"] == "bat_contact":
                status, dist_line = "batting", "distance: --"
            else:
                status, dist_line = "pitch", "distance: --"
            capture(status, dist_line)
            if terminated or truncated:
                break

        video_fps = round(1.0 / (env.model.opt.timestep * env.frame_skip))
        for cam in CAMERAS:
            path = out_dir / f"{cam}.mp4"
            imageio.mimsave(path, frames[cam], fps=video_fps, codec="libx264", quality=8)

        manifest = {
            "label": label,
            "mode": mode,
            "config": cfg,
            "end_reason": info["end_reason"],
            "status": info["status"],
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
            "exit_speed": info["exit_speed"],
            "bat_contact_vx": info["bat_contact_vx"],
            "video_fps": video_fps,
            "real_duration_s": env.data.time,
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest
    finally:
        env.close()


def main() -> None:
    base = Path("runs/kc01a-comparison/video")
    results = {}
    for mode, cfg in CONDITIONS.items():
        label = mode.upper()
        results[mode] = run_and_record(label, mode, cfg, base / mode)
        print(mode, "->", results[mode]["scoring_valid"], results[mode]["batting_score"])
    (base / "comparison_manifest.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

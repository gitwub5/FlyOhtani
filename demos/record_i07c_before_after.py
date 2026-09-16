"""I-07c-swing before/after recording (docs/design/BATTING-QUALITY-AND-SWING.md
section 3): same camera, same 1x playback rate, mid_mid only. "Before" is
the pre-I-07c-swing prep_swing=-1.9/trigger=0.094091 baseline (same physics
that shipped through I-08a-style's pose/color work); "after" is the new
default (prep_swing=-1.96, retuned trigger). Both runs carry the current
NeuroMechFly pose/color overlay (Phase A) unchanged -- only the swing
control parameters differ between the two videos.

On-screen overlay shows real distance (m), display score, and status
(투구/타격/비행중/착지/미확정) per frame -- an in-flight, not-yet-landed
distance is always labeled as such, never shown as if it were the final
score (docs/design/BATTING-QUALITY-AND-SWING.md section 1's explicit
requirement).
"""

from __future__ import annotations

import json
from pathlib import Path

import imageio
import numpy as np
from PIL import Image, ImageDraw

from controllers.baseball_b1 import CROSSING_TIME_S, OracleAimController
from envs.baseball_b1_env import BaseballB1Env

CAMERAS = ["park_wide", "batter_side"]

# English labels: PIL's default bitmap font used by ImageDraw.text() has no
# Korean glyphs (renders as tofu boxes without bundling a CJK font) -- the
# design doc's requirement is that pitch/batting/in-flight/landed/
# undetermined are visually DISTINGUISHED on screen, not that the on-screen
# string is specifically Korean text.
STATUS_LABEL = {
    "pitch": "pitch",
    "bat_contact": "batting",
    "batted_ball": "in-flight",
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


def run_and_record(
    label: str,
    prep_swing: float,
    swing_crossing_time: float,
    out_dir: Path,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    original = CROSSING_TIME_S["mid_mid"]
    CROSSING_TIME_S["mid_mid"] = (swing_crossing_time, original[1])
    env = BaseballB1Env(render_mode="rgb_array", prep_swing=prep_swing, prep_tilt=0.0)
    try:
        controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        frames: dict[str, list[np.ndarray]] = {cam: [] for cam in CAMERAS}
        info: dict = {}

        def capture(status: str, dist_line: str) -> None:
            for cam in CAMERAS:
                raw = env.render_rgb(cam)
                frames[cam].append(_overlay_text(raw, [f"{label}", f"status: {status}", dist_line]))

        capture(STATUS_LABEL["pitch"], "distance: --")
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            phase = info["phase"]
            # NOTE: env._phase is never actually set to a distinct "done"
            # value (docs/design/ENV-002-BATTED-BALL.md's state machine
            # comment is aspirational -- it stays "batted_ball" through the
            # landing step), so terminated/truncated must be checked FIRST,
            # or the final (landed) frame would be mislabeled "in-flight".
            if terminated or truncated:
                if info["status"] == "incomplete":
                    status = "undetermined"
                    dist_line = "distance: undetermined (incomplete)"
                elif info["batting_score"] is not None and info["batting_score"] > 0.0:
                    status = "landed"
                    dist_line = f"score: {info['batting_score']:.1f} (carry {info['carry_distance_m']:.1f}m)"
                else:
                    status = "landed" if info["end_reason"] == "batted_ball_landing" else "miss"
                    dist_line = "score: 0.0"
            elif phase == "batted_ball" and info["first_contact_ball_pos_xyz"] is not None:
                ball_xy_now = env.data.xpos[env.ball_body_id][:2]
                contact_xy = np.array(info["first_contact_ball_pos_xyz"])[:2]
                live_dist = float(np.linalg.norm(ball_xy_now - contact_xy))
                status = STATUS_LABEL["batted_ball"]
                dist_line = f"distance (in-flight, NOT final): {live_dist:.1f}m"
            else:
                status = STATUS_LABEL.get(phase, phase)
                dist_line = "distance: --"
            capture(status, dist_line)
            if terminated or truncated:
                break

        video_fps = round(1.0 / (env.model.opt.timestep * env.frame_skip))
        for cam in CAMERAS:
            path = out_dir / f"{cam}.mp4"
            imageio.mimsave(path, frames[cam], fps=video_fps, codec="libx264", quality=8)

        manifest = {
            "label": label,
            "prep_swing": prep_swing,
            "swing_crossing_time": swing_crossing_time,
            "end_reason": info["end_reason"],
            "status": info["status"],
            "bat_contact_vx": info["bat_contact_vx"],
            "exit_velocity_xyz": info["exit_velocity_xyz"],
            "exit_speed": info["exit_speed"],
            "launch_angle_rad": info["launch_angle_rad"],
            "forward_flight_success": info["forward_flight_success"],
            "scoring_valid": info["scoring_valid"],
            "carry_distance_m": info["carry_distance_m"],
            "landing_range_from_home_m": info["landing_range_from_home_m"],
            "batting_score": info["batting_score"],
            "recontact_count": info["recontact_count"],
            "prolonged_contact": info["prolonged_contact"],
            "first_landing_xyz": info["first_landing_xyz"],
            "reward_terms_batted_ball_v1": info["reward_terms"],
            "reward_terms_forward_carry_v1": info["forward_carry_v1"]["reward_terms"],
            "video_fps": video_fps,
            "real_duration_s": env.data.time,
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest
    finally:
        CROSSING_TIME_S["mid_mid"] = original
        env.close()


def main() -> None:
    base = Path("runs/env002-b1-i07c-swing")
    before = run_and_record("BEFORE (prep=-1.90)", -1.9, 0.094091, base / "before")
    after = run_and_record("AFTER (prep=-1.96)", -1.96, 0.09425316355759385, base / "after")

    comparison = {"before": before, "after": after}
    (base / "comparison.json").write_text(json.dumps(comparison, indent=2))
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()

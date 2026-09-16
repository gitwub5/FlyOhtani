"""I-07b-fix verification recording: ONE course (mid_mid) only.

Records the full pitch -> bat_contact -> batted_ball -> landing sequence for
the central fastball using OracleAimController, entirely through
BaseballB1Env.step() (no separate raw mj_step "post contact" loop, unlike
the pre-fix demos/record_baseball_b1_episode.py -- that script's post-hoc
loop sampled at physics_dt while the rest of the video was sampled at
control_dt, a 20x playback-rate mismatch documented in
docs/records/B1-BATTING-REVIEW.md. Here the whole episode is one
consistent control_dt-sampled loop, since the phase-based env now tracks
the ball all the way to landing inside step() itself).

Deliberately does NOT touch the other 8 courses or the old baseline runner
-- see docs/records/STATUS.md for why (I-07b-fix stages central-case
verification before the 9-course expansion).

I-07b-followthrough: also dumps a per-control-step angle/velocity/ctrl/
state/contact timeline (timeline.json) alongside the video, per the design
doc's acceptance-evidence requirement ("각도/각속도/torque/state/contact
timeline과 같은 1x배율 영상을 남긴다").
"""

from __future__ import annotations

import json
from pathlib import Path

import imageio
import numpy as np

from controllers.baseball_b1 import OracleAimController
from envs.baseball_b1_env import BaseballB1Env

CAMERAS = ["park_wide", "batter_side"]


def main(out_dir: Path = Path("runs/env002-b1-fix-verification/mid_mid")) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = BaseballB1Env(render_mode="rgb_array")
    controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
    obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
    controller.reset()

    frames: dict[str, list[np.ndarray]] = {cam: [] for cam in CAMERAS}
    timeline: list[dict] = []

    def capture() -> None:
        for cam in CAMERAS:
            frames[cam].append(env.render_rgb(cam))

    capture()
    info: dict = {}
    while True:
        action = controller.act(obs)
        obs, _, terminated, truncated, info = env.step(action)
        capture()
        timeline.append(
            {
                "t": env.data.time,
                "swing_state": controller._swing_axis.state,
                "swing_angle": float(env.data.qpos[env.swing_qpos_adr]),
                "swing_vel": float(env.data.qvel[env.swing_qvel_adr]),
                "swing_ctrl": float(action[0]),
                "tilt_state": controller._tilt_axis.state,
                "tilt_angle": float(env.data.qpos[env.tilt_qpos_adr]),
                "tilt_vel": float(env.data.qvel[env.tilt_qvel_adr]),
                "tilt_ctrl": float(action[1]),
                "contact_occurred": info["contact_occurred"],
                "phase": info["phase"],
            }
        )
        if terminated or truncated:
            break

    video_fps = round(1.0 / (env.model.opt.timestep * env.frame_skip))
    for cam in CAMERAS:
        path = out_dir / f"{cam}.mp4"
        imageio.mimsave(path, frames[cam], fps=video_fps, codec="libx264", quality=8)

    (out_dir / "timeline.json").write_text(json.dumps(timeline, indent=2))

    manifest = {
        "course": "mid_mid",
        "end_reason": info["end_reason"],
        "contact_occurred": info["contact_occurred"],
        "bat_contact_vx": info["bat_contact_vx"],
        "exit_velocity_xyz": info["exit_velocity_xyz"],
        "forward_flight_success": info["forward_flight_success"],
        "first_landing_xyz": info["first_landing_xyz"],
        "carry_distance_xy_m": info["carry_distance_xy_m"],
        "final_swing_state": controller._swing_axis.state,
        "final_tilt_state": controller._tilt_axis.state,
        "n_frames": len(frames[CAMERAS[0]]),
        "video_fps": video_fps,
        "real_duration_s": env.data.time,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    env.close()
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

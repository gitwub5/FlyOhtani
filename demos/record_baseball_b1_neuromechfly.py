"""I-08a-fix verification recording (docs/records/FLY-VISUAL-REVIEW.md):
NeuroMechFly visual overlay on the mid_mid central hit. Wide/behind-
catcher/batter-side full-body cameras plus a grip close-up, all at the
same real-time axis (one frame per control step, same fix as
demos/record_baseball_b1_mid_mid_fix.py) -- and, per the review's explicit
requirement, standalone FRONT/SIDE still frames at prepare/contact/settle,
checked before the continuous video.

The overlay (envs/fly_visual.py's FrontLegGripOverlay) is purely a render-
time concern: it is updated after every env.step(), never during it, and
cannot affect the physics trajectory -- see
tests/test_baseball_b1_env.py::test_central_hit_physics_unchanged_by_the_visual_overlay
for the frozen-reference-value proof.
"""

from __future__ import annotations

import json
from pathlib import Path

import imageio
import mujoco
import numpy as np

from controllers.baseball_b1 import OracleAimController
from envs.baseball_b1_env import BaseballB1Env
from envs.fly_visual import FrontLegGripOverlay

FULL_BODY_CAMERAS = ["park_wide", "behind_catcher", "batter_side"]

# Standalone front/side + grip-closeup cameras, verified by direct render
# inspection during I-08a-fix (docs/records/VALIDATION_LOG.md) to frame the
# recentered character correctly.
STILL_CAMERAS = {
    "front": {"lookat": [0.2, 0.9, 0.9], "distance": 2.5, "azimuth": 0, "elevation": -10},
    "side": {"lookat": [0.2, 0.9, 0.8], "distance": 2.5, "azimuth": 90, "elevation": -10},
    "grip_closeup": {"lookat": [0.2, 0.9, 0.9], "distance": 1.2, "azimuth": 60, "elevation": -10},
}
STILL_MOMENTS = ["prepare", "contact", "settle"]


def _make_cam(spec: dict) -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.lookat = spec["lookat"]
    cam.distance = spec["distance"]
    cam.azimuth = spec["azimuth"]
    cam.elevation = spec["elevation"]
    return cam


def main(out_dir: Path = Path("runs/env002-b1-neuromechfly/mid_mid")) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stills_dir = out_dir / "stills"
    stills_dir.mkdir(parents=True, exist_ok=True)

    env = BaseballB1Env(render_mode="rgb_array")
    overlay = FrontLegGripOverlay(env.model)
    controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
    obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
    controller.reset()
    overlay.update(env.model, env.data)

    renderer = mujoco.Renderer(env.model, width=960, height=720)
    still_cams = {name: _make_cam(spec) for name, spec in STILL_CAMERAS.items()}

    def save_stills(moment: str) -> None:
        for name, cam in still_cams.items():
            renderer.update_scene(env.data, camera=cam)
            img = renderer.render()
            imageio.imwrite(stills_dir / f"{moment}_{name}.png", img)

    save_stills("prepare")

    frames: dict[str, list[np.ndarray]] = {cam: [] for cam in FULL_BODY_CAMERAS}
    frames["grip_closeup"] = []
    grip_cam = still_cams["grip_closeup"]

    def capture_video_frame() -> None:
        for cam in FULL_BODY_CAMERAS:
            frames[cam].append(env.render_rgb(cam))
        renderer.update_scene(env.data, camera=grip_cam)
        frames["grip_closeup"].append(renderer.render())

    capture_video_frame()
    info: dict = {}
    prev_phase = "pitch"
    contact_saved = False
    while True:
        action = controller.act(obs)
        obs, _, terminated, truncated, info = env.step(action)
        overlay.update(env.model, env.data)
        capture_video_frame()
        if not contact_saved and info["phase"] in ("bat_contact", "batted_ball") and prev_phase == "pitch":
            save_stills("contact")
            contact_saved = True
        prev_phase = info["phase"]
        if terminated or truncated:
            break
    save_stills("settle")

    video_fps = round(1.0 / (env.model.opt.timestep * env.frame_skip))
    for cam, frs in frames.items():
        path = out_dir / f"{cam}.mp4"
        imageio.mimsave(path, frs, fps=video_fps, codec="libx264", quality=8)

    manifest = {
        "course": "mid_mid",
        "end_reason": info["end_reason"],
        "bat_contact_vx": info["bat_contact_vx"],
        "exit_velocity_xyz": info["exit_velocity_xyz"],
        "forward_flight_success": info["forward_flight_success"],
        "first_landing_xyz": info["first_landing_xyz"],
        "n_frames": len(frames["park_wide"]),
        "video_fps": video_fps,
        "real_duration_s": env.data.time,
        "cameras": list(frames.keys()),
        "stills": [f"{m}_{c}.png" for m in STILL_MOMENTS for c in STILL_CAMERAS],
        "note": "physics identical to the pre-overlay reference in VALIDATION_LOG "
        "(the overlay only adds contype=0/conaffinity=0 render-time geoms + mocap "
        "bodies updated after each step, never during it).",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    env.close()
    renderer.close()
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

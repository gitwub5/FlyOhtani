"""KC-01a same-direction condition (docs/design/KC-01a-DIRECTION-CONTRACT.md
section 4 item 6 deliverable): a TOP-DOWN video (custom free mjvCamera, not
one of envs/assets/baseball_park_kc01a.xml's named cameras -- none of them
looks straight down) for the OLD counter-rotating `staggered_swing_and_torso`
(diagnostic record, unchanged) and the NEW `same_direction_staggered`
condition side by side, so torso/swing/world-bat rotation SENSE is visually
checkable, not just inferred from signed numbers. Overlay text shows sim
time and torso/swing/world-bat angle+angular velocity every frame.
"""
from __future__ import annotations

import json
from pathlib import Path

import imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "runs" / "kc01a-same-direction-video"
SEARCH_RESULT_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence" / "KC-01a-same-direction-search.json"
)

CONDITIONS = {
    "staggered_swing_and_torso_OLD_counter_rotating": {
        "mode": "staggered",
        "torso_target": -0.4,
        "swing_target": -0.726,
        "torso_ct": 0.242,
        "swing_ct": 0.122,
    },
    # same_direction_staggered filled in from the search result at runtime
}


def _top_down_camera() -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat = np.array([0.1, 0.3, 1.0])
    cam.distance = 6.0
    cam.azimuth = 90.0
    cam.elevation = -89.0  # straight down
    return cam


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

        renderer = mujoco.Renderer(env.model, width=640, height=640)
        cam = _top_down_camera()
        frames = []
        info: dict = {}

        def capture(status: str) -> None:
            torso_a = float(env.data.qpos[env.torso_qpos_adr])
            torso_v = float(env.data.qvel[env.torso_qvel_adr])
            swing_a = float(env.data.qpos[env.swing_qpos_adr])
            swing_v = float(env.data.qvel[env.swing_qvel_adr])
            renderer.update_scene(env.data, camera=cam)
            raw = renderer.render()
            lines = [
                f"KC-01a top-down: {label}",
                f"t={env.data.time:.3f}s status={status}",
                f"torso: angle={torso_a:+.3f}rad vel={torso_v:+.2f}rad/s",
                f"swing: angle={swing_a:+.3f}rad vel={swing_v:+.2f}rad/s",
                f"world_bat: angle={torso_a + swing_a:+.3f}rad vel={torso_v + swing_v:+.2f}rad/s",
            ]
            frames.append(_overlay_text(raw, lines))

        capture("pitch")
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                status = "landed" if info.get("scoring_valid") else "landed(invalid)/miss"
            elif info.get("contact_occurred") and info.get("phase") == "batted_ball":
                status = "in-flight"
            elif info.get("phase") == "bat_contact":
                status = "batting"
            else:
                status = "pitch"
            capture(status)
            if terminated or truncated:
                break

        video_fps = round(1.0 / (env.model.opt.timestep * env.frame_skip))
        path = out_dir / "top_down.mp4"
        imageio.mimsave(path, frames, fps=video_fps, codec="libx264", quality=8)
        renderer.close()

        manifest = {
            "label": label,
            "mode": mode,
            "config": cfg,
            "end_reason": info["end_reason"],
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest
    finally:
        env.close()


def main() -> None:
    search = json.loads(SEARCH_RESULT_PATH.read_text())
    trig = search["trigger_search"]
    conditions = dict(CONDITIONS)
    conditions["same_direction_staggered_NEW"] = {
        "mode": "staggered",
        "torso_target": search["chosen_torso_target"],
        "swing_target": search["chosen_swing_target"],
        "torso_ct": trig["torso_crossing_time_s"],
        "swing_ct": trig["swing_crossing_time_s"],
    }

    results = {}
    for name, cfg in conditions.items():
        print(f"recording {name} ...")
        results[name] = run_and_record(name, cfg["mode"], cfg, OUT_DIR / name)
        print(" ->", results[name]["scoring_valid"], results[name]["batting_score"])
    (OUT_DIR / "manifest.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

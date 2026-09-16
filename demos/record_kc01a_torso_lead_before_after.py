"""KC-01a torso-lead before/after video (user follow-up): top-down (custom
free camera, as in demos/record_kc01a_same_direction.py) AND side view
(the XML's own named "batter_side" camera, via env.render_rgb) for BEFORE
(`same_direction_staggered`, ~10ms fixed command offset -- shown to have
~0ms actual motion-onset lead, scripts/kc01a_torso_lead_analysis.py) and
AFTER (`torso_lead_handoff`, torso_target=0.5/torso_ct=0.33/
handoff_fraction=0.5 -- a genuine ~225ms control-trigger lead, scripts/
kc01a_torso_lead_handoff_validation.py, dt-converged/settled/grip-
reachable). Overlay marks torso rotation onset, swing rotation onset, and
first bat-ball contact on every frame, and states BOTH the real-time frame
rate and the slow-motion factor actually used (physics runs at its own
frame_skip*timestep cadence; this script renders every physics-timestep-
matched control step at native fps AND writes a second, slowed-down copy
at 1/8x by simply lowering the encoded fps -- the frame CONTENT is
identical, only playback speed changes, so no motion is exaggerated or
invented, per the user's "외형 애니메이션으로 움직임을 과장하지 마"
instruction).
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

OUT_DIR = Path(__file__).resolve().parent.parent / "runs" / "kc01a-torso-lead-before-after"
ONSET_QVEL_THRESHOLD = 0.05
SLOWMO_FACTOR = 8  # playback fps divided by this; real-time fps unchanged in content

CONDITIONS = {
    "before_same_direction_staggered_10ms_offset": {
        "mode": "staggered",
        "torso_target": 0.3,
        "swing_target": -1.7099999999999997,
        "torso_ct": 0.12200000000000004,
        "swing_ct": 0.11200000000000004,
        "handoff_fraction": None,
    },
    "after_torso_lead_handoff_225ms": {
        "mode": "torso_lead_handoff",
        "torso_target": 0.5,
        "swing_target": -1.9640000000000004,
        "torso_ct": 0.33,
        "swing_ct": 999.0,
        "handoff_fraction": 0.5,
    },
}


def _top_down_camera() -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat = np.array([0.1, 0.3, 1.0])
    cam.distance = 6.0
    cam.azimuth = 90.0
    cam.elevation = -89.0
    return cam


def _overlay(frame: np.ndarray, lines: list[str]) -> np.ndarray:
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    y = 10
    for line in lines:
        draw.rectangle([8, y - 2, 8 + 9 * len(line), y + 16], fill=(0, 0, 0))
        draw.text((10, y), line, fill=(255, 255, 0))
        y += 20
    return np.array(img)


def run_and_record(label: str, cfg: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = BaseballKC01aEnv(render_mode="rgb_array", prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        kwargs = {}
        if cfg["handoff_fraction"] is not None:
            kwargs["handoff_fraction"] = cfg["handoff_fraction"]
        controller = TorsoBatController(
            cfg["mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"], **kwargs
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        renderer = mujoco.Renderer(env.model, width=640, height=640)
        top_cam = _top_down_camera()

        torso_onset_t = swing_onset_t = contact_t = None
        top_frames, side_frames = [], []
        info: dict = {}

        def capture():
            torso_a = float(env.data.qpos[env.torso_qpos_adr])
            torso_v = float(env.data.qvel[env.torso_qvel_adr])
            swing_a = float(env.data.qpos[env.swing_qpos_adr])
            swing_v = float(env.data.qvel[env.swing_qvel_adr])
            t = float(env.data.time)
            lines = [
                f"KC-01a: {label}",
                f"t={t:.3f}s  torso_a={torso_a:+.3f}rad v={torso_v:+.2f}rad/s",
                f"swing_a={swing_a:+.3f}rad v={swing_v:+.2f}rad/s",
                f"torso onset={torso_onset_t}  swing onset={swing_onset_t}  contact={contact_t}",
            ]
            renderer.update_scene(env.data, camera=top_cam)
            top_frames.append(_overlay(renderer.render(), ["[TOP-DOWN] " + lines[0], *lines[1:]]))
            side_frames.append(_overlay(env.render_rgb("batter_side"), ["[SIDE] " + lines[0], *lines[1:]]))

        capture()
        while True:
            t = float(env.data.time)
            torso_v = float(env.data.qvel[env.torso_qvel_adr])
            swing_v = float(env.data.qvel[env.swing_qvel_adr])
            if torso_onset_t is None and abs(torso_v) > ONSET_QVEL_THRESHOLD:
                torso_onset_t = round(t, 4)
            if swing_onset_t is None and abs(swing_v) > ONSET_QVEL_THRESHOLD:
                swing_onset_t = round(t, 4)
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            if contact_t is None and info.get("contact_occurred"):
                contact_t = round(float(env.data.time), 4)
            capture()
            if terminated or truncated:
                break

        native_fps = round(1.0 / (env.model.opt.timestep * env.frame_skip))
        slow_fps = max(1, native_fps // SLOWMO_FACTOR)
        for name, frames in (("top_down", top_frames), ("side", side_frames)):
            imageio.mimsave(out_dir / f"{name}_realtime_{native_fps}fps.mp4", frames, fps=native_fps, codec="libx264", quality=8)
            imageio.mimsave(out_dir / f"{name}_slowmo_{SLOWMO_FACTOR}x_{slow_fps}fps.mp4", frames, fps=slow_fps, codec="libx264", quality=8)
        renderer.close()

        manifest = {
            "label": label,
            "config": cfg,
            "torso_motion_onset_t": torso_onset_t,
            "swing_motion_onset_t": swing_onset_t,
            "first_contact_time_s": contact_t,
            "actual_motion_lead_s": None if (torso_onset_t is None or swing_onset_t is None) else round(swing_onset_t - torso_onset_t, 4),
            "native_fps_realtime": native_fps,
            "slowmo_factor": SLOWMO_FACTOR,
            "slowmo_encoded_fps": slow_fps,
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        return manifest
    finally:
        env.close()


def main() -> None:
    results = {}
    for name, cfg in CONDITIONS.items():
        print(f"recording {name} ...")
        results[name] = run_and_record(name, cfg, OUT_DIR / name)
        print(" ->", json.dumps(results[name], default=str))
    (OUT_DIR / "manifest.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()

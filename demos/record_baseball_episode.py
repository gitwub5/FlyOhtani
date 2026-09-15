from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import imageio
import mujoco
import numpy as np

from controllers.baseball_scripted import BaseballScriptedSwing
from envs import BaseballB0Env

DEV_SEEDS = range(20)
CAMERAS = ["park_wide", "behind_catcher", "batter_side", "fly_pov"]


class ZeroController:
    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return np.zeros(1, dtype=np.float32)


class RandomController:
    def __init__(self, action_space, rng: np.random.Generator) -> None:
        self.action_space = action_space
        self._rng = rng

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return self._rng.uniform(
            self.action_space.low, self.action_space.high, size=self.action_space.shape
        ).astype(np.float32)


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def run_episode(env: BaseballB0Env, controller, seed: int) -> dict:
    obs, _ = env.reset(seed=seed)
    controller.reset()
    total_reward = 0.0
    info: dict = {}
    while True:
        obs, reward, terminated, truncated, info = env.step(controller.act(obs))
        total_reward += reward
        if terminated or truncated:
            break
    timing_error = info.get("timing_error")
    return {
        "reward": float(total_reward),
        "hit": bool(info.get("hit", False)),
        "end_reason": str(info.get("end_reason")),
        "timing_error": float(timing_error) if timing_error is not None else float("nan"),
        "contact_velocity_post_contact": float(info.get("contact_velocity_post_contact", 0.0)),
    }


def run_held_pose_episode(env: BaseballB0Env, angle: float, seed: int) -> dict:
    env.reset(seed=seed)
    env.set_held_pose(angle)
    total_reward = 0.0
    info: dict = {}
    while True:
        _, reward, terminated, truncated, info = env.step(np.zeros(1, dtype=np.float32))
        total_reward += reward
        if terminated or truncated:
            break
    env.set_held_pose(None)
    timing_error = info.get("timing_error")
    return {
        "reward": float(total_reward),
        "hit": bool(info.get("hit", False)),
        "end_reason": str(info.get("end_reason")),
        "timing_error": float(timing_error) if timing_error is not None else float("nan"),
        "contact_velocity_post_contact": float(info.get("contact_velocity_post_contact", 0.0)),
    }


def run_baseline(name: str, seeds: range) -> list[dict]:
    env = BaseballB0Env()
    try:
        if name == "held_rest":
            return [run_held_pose_episode(env, env.prep_angle, seed=s) for s in seeds]
        if name == "zero_torque":
            controller = ZeroController()
        elif name == "random":
            controller = RandomController(env.action_space, np.random.default_rng(min(seeds)))
        elif name == "scripted":
            controller = BaseballScriptedSwing(prep_angle=env.prep_angle)
        else:
            raise ValueError(name)
        return [run_episode(env, controller, seed=s) for s in seeds]
    finally:
        env.close()


def summarize(name: str, results: list[dict]) -> dict:
    n = len(results)
    hits = sum(r["hit"] for r in results)
    hit_rate = hits / n
    ci_lo, ci_hi = wilson_ci(hits, n)
    mean_reward = sum(r["reward"] for r in results) / n
    end_reasons = Counter(r["end_reason"] for r in results)
    print(
        f"[{name}] n={n} hits={hits} hit_rate={hit_rate:.3f} "
        f"wilson95%=({ci_lo:.3f},{ci_hi:.3f}) mean_reward={mean_reward:.3f} "
        f"end_reasons={dict(end_reasons)}"
    )
    return {
        "n": n,
        "hits": hits,
        "hit_rate": hit_rate,
        "wilson95": [ci_lo, ci_hi],
        "mean_reward": mean_reward,
        "end_reasons": dict(end_reasons),
    }


def record_video(out_dir: Path, seed: int = 0, post_contact_steps: int = 60) -> dict[str, str]:
    """Runs one scripted-controller episode, saving a per-camera MP4 of
    pitch -> swing -> contact. Continues rendering (not scoring: env.step()
    would raise after termination) a short post-contact follow-through purely
    via direct mj_step calls, for a more legible replay."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = BaseballB0Env(render_mode="rgb_array")
    controller = BaseballScriptedSwing(prep_angle=env.prep_angle)
    obs, _ = env.reset(seed=seed)
    controller.reset()

    frames: dict[str, list[np.ndarray]] = {cam: [] for cam in CAMERAS}
    events: list[dict] = []

    def capture(tag: str) -> None:
        for cam in CAMERAS:
            frames[cam].append(env.render_rgb(cam))
        events.append({"t": float(env.data.time), "tag": tag})

    capture("release")
    info: dict = {}
    while True:
        obs, _reward, terminated, truncated, info = env.step(controller.act(obs))
        capture("hit" if info.get("hit") else "step")
        if terminated or truncated:
            break

    # Post-terminal follow-through: rendering only, bypasses env.step()'s
    # terminal guard on purpose (no reward/contact scoring happens here).
    for _ in range(post_contact_steps):
        mujoco.mj_step(env.model, env.data)
        capture("post_contact")

    paths: dict[str, str] = {}
    for cam in CAMERAS:
        path = out_dir / f"{cam}.mp4"
        imageio.mimsave(path, frames[cam], fps=30, codec="libx264", quality=8)
        paths[cam] = str(path)

    manifest = {
        "seed": seed,
        "end_reason": info.get("end_reason"),
        "hit": info.get("hit"),
        "contact_time_s": info.get("contact_time_s"),
        "planned_arrival_s": info.get("planned_arrival_s"),
        "signed_timing_error_s": info.get("signed_timing_error_s"),
        "launch_speed_total_m_s": info.get("launch_speed_total_m_s"),
        "launch_speed_horizontal_m_s": info.get("launch_speed_horizontal_m_s"),
        "frame_count": len(frames[CAMERAS[0]]),
        "playback_fps": 30,
        "control_dt_s": env.model.opt.timestep * env.frame_skip,
        "cameras": paths,
        "events": events,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    env.close()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="ENV-002 B0 baseline runner / video recorder.")
    parser.add_argument(
        "--mode", choices=["baselines", "video", "all"], default="all"
    )
    parser.add_argument("--out", type=Path, default=Path("runs/env002-b0-demo"))
    args = parser.parse_args()

    results = {}
    if args.mode in ("baselines", "all"):
        for name in ["zero_torque", "held_rest", "random", "scripted"]:
            r = run_baseline(name, DEV_SEEDS)
            results[name] = summarize(name, r)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "baseline_results.json").write_text(json.dumps(results, indent=2))

    if args.mode in ("video", "all"):
        manifest = record_video(args.out / "video")
        print("video manifest:", json.dumps({k: v for k, v in manifest.items() if k != "events"}, indent=2))


if __name__ == "__main__":
    main()

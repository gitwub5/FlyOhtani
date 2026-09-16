from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import imageio
import numpy as np

from controllers.baseball_b1 import FixedPoseAlwaysSwing, OracleAimController, ScriptedAimController
from envs.baseball_b1_env import COURSES, BaseballB1Env

DEV_SEEDS = range(20)
CAMERAS = ["park_wide", "behind_catcher", "batter_side", "fly_pov"]


class ZeroController:
    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return np.zeros(2, dtype=np.float32)


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


def run_episode(env: BaseballB1Env, controller, course: str, seed: int) -> dict:
    obs, _ = env.reset(seed=seed, options={"course": course})
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
        "course": course,
        "reward": float(total_reward),
        "hit": bool(info.get("hit", False)),
        "end_reason": str(info.get("end_reason")),
        "timing_error": float(timing_error) if timing_error is not None else float("nan"),
        "contact_velocity_post_contact": float(info.get("contact_velocity_post_contact", 0.0)),
    }


def run_held_pose_episode(env: BaseballB1Env, course: str, seed: int) -> dict:
    env.reset(seed=seed, options={"course": course})
    env.set_held_pose(env.prep_swing, env.prep_tilt)
    total_reward = 0.0
    info: dict = {}
    while True:
        _, reward, terminated, truncated, info = env.step(np.zeros(2, dtype=np.float32))
        total_reward += reward
        if terminated or truncated:
            break
    timing_error = info.get("timing_error")
    return {
        "course": course,
        "reward": float(total_reward),
        "hit": bool(info.get("hit", False)),
        "end_reason": str(info.get("end_reason")),
        "timing_error": float(timing_error) if timing_error is not None else float("nan"),
        "contact_velocity_post_contact": float(info.get("contact_velocity_post_contact", 0.0)),
    }


def make_controller(name: str, env: BaseballB1Env, course: str, seed: int):
    if name == "zero_torque":
        return ZeroController()
    if name == "random":
        return RandomController(env.action_space, np.random.default_rng(seed))
    if name == "always_swing_fixed_pose":
        return FixedPoseAlwaysSwing()
    if name == "scripted":
        return ScriptedAimController(prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
    if name == "oracle":
        return OracleAimController(course, prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
    raise ValueError(name)


def run_baseline_for_course(name: str, course: str, seeds: range) -> list[dict]:
    env = BaseballB1Env()
    try:
        if name == "held_rest":
            return [run_held_pose_episode(env, course, seed=s) for s in seeds]
        return [
            run_episode(env, make_controller(name, env, course, seed=min(seeds)), course, seed=s)
            for s in seeds
        ]
    finally:
        env.close()


def summarize_course(name: str, course: str, results: list[dict]) -> dict:
    n = len(results)
    hits = sum(r["hit"] for r in results)
    hit_rate = hits / n
    ci_lo, ci_hi = wilson_ci(hits, n)
    end_reasons = Counter(r["end_reason"] for r in results)
    row = {
        "controller": name,
        "course": course,
        "n": n,
        "hits": hits,
        "hit_rate": hit_rate,
        "wilson95": [ci_lo, ci_hi],
        "mean_reward": sum(r["reward"] for r in results) / n,
        "end_reasons": dict(end_reasons),
        "mean_timing_error_on_hit": (
            float(np.nanmean([r["timing_error"] for r in results if r["hit"]]))
            if hits
            else None
        ),
    }
    return row


def run_all_baselines(seeds: range = DEV_SEEDS) -> list[dict]:
    names = ["zero_torque", "held_rest", "random", "always_swing_fixed_pose", "scripted"]
    rows = []
    for course in COURSES:
        for name in names:
            r = run_baseline_for_course(name, course, seeds)
            row = summarize_course(name, course, r)
            rows.append(row)
            print(
                f"[{name:24s}][{course:10s}] hit_rate={row['hit_rate']:.2f} "
                f"({row['hits']}/{row['n']}) end_reasons={row['end_reasons']}"
            )
    # oracle: reachability diagnosis, kept in a separate list/label
    for course in COURSES:
        r = run_baseline_for_course("oracle", course, seeds)
        row = summarize_course("oracle[reachability-only]", course, r)
        rows.append(row)
        print(
            f"[oracle-diag            ][{course:10s}] hit_rate={row['hit_rate']:.2f} "
            f"({row['hits']}/{row['n']}) end_reasons={row['end_reasons']}"
        )
    return rows


def record_course_video(course: str, out_dir: Path, seed: int = 0, post_contact_steps: int = 60) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = BaseballB1Env(render_mode="rgb_array")
    controller = ScriptedAimController(prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
    obs, _ = env.reset(seed=seed, options={"course": course})
    controller.reset()

    frames: dict[str, list[np.ndarray]] = {cam: [] for cam in CAMERAS}

    def capture() -> None:
        for cam in CAMERAS:
            frames[cam].append(env.render_rgb(cam))

    capture()
    info: dict = {}
    while True:
        obs, _, terminated, truncated, info = env.step(controller.act(obs))
        capture()
        if terminated or truncated:
            break

    import mujoco

    for _ in range(post_contact_steps):
        mujoco.mj_step(env.model, env.data)
        capture()

    paths = {}
    for cam in CAMERAS:
        path = out_dir / f"{cam}.mp4"
        imageio.mimsave(path, frames[cam], fps=30, codec="libx264", quality=8)
        paths[cam] = str(path)

    manifest = {
        "course": course,
        "end_reason": info.get("end_reason"),
        "hit": info.get("hit"),
        "contact_time_s": info.get("contact_time_s"),
        "planned_arrival_s": info.get("planned_arrival_s"),
        "target": info.get("target"),
        "cameras": paths,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    env.close()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="ENV-002 B1 baseline runner / per-course video recorder.")
    parser.add_argument("--mode", choices=["baselines", "video", "all"], default="all")
    parser.add_argument("--out", type=Path, default=Path("runs/env002-b1-demo"))
    args = parser.parse_args()

    if args.mode in ("baselines", "all"):
        rows = run_all_baselines()
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "baseline_results.json").write_text(json.dumps(rows, indent=2))

    if args.mode in ("video", "all"):
        for course in COURSES:
            manifest = record_course_video(course, args.out / "video" / course)
            print(f"video[{course}]:", manifest["hit"], manifest["end_reason"])


if __name__ == "__main__":
    main()

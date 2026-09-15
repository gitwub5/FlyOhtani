from __future__ import annotations

import argparse
import math
from collections import Counter

import mujoco
import numpy as np

from controllers import ConstantAngleController, ScriptedSwingController
from envs import FlyBatterEnv

DEV_SEEDS = range(20)
TEST_SEEDS = range(1000, 1100)


class ZeroController:
    """Always outputs zero torque -- the "zero_torque" (passive) baseline."""

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return np.zeros(1, dtype=np.float32)


class RandomController:
    """Uniform random action each step -- the "random" baseline. Has its own
    RNG stream, independent of the environment's, so using it never changes
    another controller's ball-placement sequence for the same env seed."""

    def __init__(self, action_space, rng: np.random.Generator) -> None:
        self.action_space = action_space
        self._rng = rng

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return self._rng.uniform(
            self.action_space.low, self.action_space.high, size=self.action_space.shape
        ).astype(np.float32)


def make_controller(name: str, env: FlyBatterEnv, seed: int, constant_angle: float | None = None):
    if name == "scripted":
        return ScriptedSwingController(prep_angle=env.prep_angle)
    if name == "zero_torque":
        return ZeroController()
    if name == "random":
        return RandomController(env.action_space, np.random.default_rng(seed))
    if name == "best_constant_angle":
        angle = env.prep_angle if constant_angle is None else constant_angle
        return ConstantAngleController(target_angle=angle)
    raise ValueError(f"unknown controller: {name}")


def run_episode(env: FlyBatterEnv, controller, seed: int) -> dict:
    obs, _ = env.reset(seed=seed)
    controller.reset()
    total_reward = 0.0
    final_info: dict = {}

    while True:
        action = controller.act(obs)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        final_info = info
        if terminated or truncated:
            break

    timing_error = final_info.get("timing_error")
    return {
        "reward": float(total_reward),
        "hit": bool(final_info.get("hit", False)),
        "end_reason": str(final_info.get("end_reason")),
        "timing_error": float(timing_error) if timing_error is not None else float("nan"),
        "signed_timing_error_s": final_info.get("signed_timing_error_s"),
        "contact_velocity_post_contact": float(
            final_info.get("contact_velocity_post_contact", 0.0)
        ),
    }


def run_held_pose_episode(env: FlyBatterEnv, angle: float, seed: int) -> dict:
    """held_rest diagnostic: forcibly re-pins the hinge to `angle` after every
    control step (approx. a fixed pose; not a real actuated policy -- see
    docs/design/ENV-001-interception.md's "held 계열은 ... 기하 진단").
    """
    env.reset(seed=seed)
    env.data.qpos[env.swing_qpos_adr] = angle
    env.data.qvel[env.swing_qvel_adr] = 0.0
    mujoco.mj_forward(env.model, env.data)
    total_reward = 0.0
    final_info: dict = {}

    while True:
        _obs, reward, terminated, truncated, info = env.step(np.zeros(1, dtype=np.float32))
        total_reward += reward
        final_info = info
        if terminated or truncated:
            break
        env.data.qpos[env.swing_qpos_adr] = angle
        env.data.qvel[env.swing_qvel_adr] = 0.0
        mujoco.mj_forward(env.model, env.data)

    timing_error = final_info.get("timing_error")
    return {
        "reward": float(total_reward),
        "hit": bool(final_info.get("hit", False)),
        "end_reason": str(final_info.get("end_reason")),
        "timing_error": float(timing_error) if timing_error is not None else float("nan"),
        "contact_velocity_post_contact": float(
            final_info.get("contact_velocity_post_contact", 0.0)
        ),
    }


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def run_baseline(
    name: str, seeds: range, render_mode: str | None, constant_angle: float | None = None
) -> list[dict]:
    env = FlyBatterEnv(render_mode=render_mode)
    try:
        if name == "held_rest":
            return [run_held_pose_episode(env, env.prep_angle, seed=s) for s in seeds]
        controller = make_controller(name, env, seed=min(seeds), constant_angle=constant_angle)
        return [run_episode(env, controller, seed=s) for s in seeds]
    finally:
        env.close()


def summarize(name: str, results: list[dict]) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FlyOhtani episodes with a chosen baseline.")
    parser.add_argument(
        "--controller",
        choices=["scripted", "zero_torque", "random", "held_rest", "best_constant_angle", "all"],
        default="scripted",
    )
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--render", choices=["none", "human", "rgb_array"], default="none")
    args = parser.parse_args()

    render_mode = None if args.render == "none" else args.render
    seeds = DEV_SEEDS if args.split == "dev" else TEST_SEEDS
    names = (
        ["scripted", "zero_torque", "random", "held_rest", "best_constant_angle"]
        if args.controller == "all"
        else [args.controller]
    )

    for name in names:
        results = run_baseline(name, seeds, render_mode)
        summarize(name, results)


if __name__ == "__main__":
    main()

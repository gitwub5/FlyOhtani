from __future__ import annotations

import argparse
from collections import Counter

import numpy as np

from controllers import ScriptedSwingController
from envs import FlyBatterEnv


class ZeroController:
    """Always outputs zero torque -- the "motionless" baseline."""

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return np.zeros(1, dtype=np.float32)


class RandomController:
    """Uniform random action each step -- the "random" baseline."""

    def __init__(self, action_space, rng: np.random.Generator) -> None:
        self.action_space = action_space
        self._rng = rng

    def reset(self) -> None:
        pass

    def act(self, obs: np.ndarray) -> np.ndarray:
        return self._rng.uniform(
            self.action_space.low, self.action_space.high, size=self.action_space.shape
        ).astype(np.float32)


def make_controller(name: str, env: FlyBatterEnv, seed: int):
    if name == "scripted":
        return ScriptedSwingController()
    if name == "none":
        return ZeroController()
    if name == "random":
        return RandomController(env.action_space, np.random.default_rng(seed))
    raise ValueError(f"unknown controller: {name}")


def run_episode(env: FlyBatterEnv, controller, seed: int) -> dict[str, float]:
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
        "hit": float(final_info.get("hit", False)),
        "end_reason": str(final_info.get("end_reason")),
        "timing_error": float(timing_error) if timing_error is not None else float("nan"),
        "contact_velocity": float(final_info.get("contact_velocity", 0.0)),
    }


def run_baseline(name: str, episodes: int, seed: int, render_mode: str | None) -> list[dict]:
    env = FlyBatterEnv(render_mode=render_mode)
    try:
        controller = make_controller(name, env, seed)
        return [run_episode(env, controller, seed=seed + i) for i in range(episodes)]
    finally:
        env.close()


def summarize(name: str, results: list[dict]) -> None:
    n = len(results)
    hit_rate = sum(r["hit"] for r in results) / n
    mean_reward = sum(r["reward"] for r in results) / n
    end_reasons = Counter(r["end_reason"] for r in results)
    print(
        f"[{name}] episodes={n} hit_rate={hit_rate:.3f} mean_reward={mean_reward:.3f} "
        f"end_reasons={dict(end_reasons)}"
    )
    for idx, result in enumerate(results, start=1):
        print(
            f"  episode={idx} reward={result['reward']:.3f} hit={bool(result['hit'])} "
            f"end_reason={result['end_reason']} "
            f"timing_error={result['timing_error']:.4f} "
            f"contact_velocity={result['contact_velocity']:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FlyOhtani episodes with a chosen baseline.")
    parser.add_argument(
        "--controller",
        choices=["scripted", "none", "random", "all"],
        default="scripted",
        help="'all' runs scripted/none/random under the same seed for comparison.",
    )
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--render", choices=["none", "human", "rgb_array"], default="none")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    render_mode = None if args.render == "none" else args.render
    names = ["scripted", "none", "random"] if args.controller == "all" else [args.controller]

    for name in names:
        results = run_baseline(name, args.episodes, args.seed, render_mode)
        summarize(name, results)


if __name__ == "__main__":
    main()

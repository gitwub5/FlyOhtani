from __future__ import annotations

import argparse

import numpy as np

from controllers import ScriptedSwingController
from envs import FlyBatterEnv


def run_episode(env: FlyBatterEnv, controller: ScriptedSwingController) -> dict[str, float]:
    obs, _ = env.reset()
    controller.reset()
    total_reward = 0.0
    final_info = {}

    while True:
        action = controller.act(obs)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        final_info = info
        if terminated or truncated:
            break

    return {
        "reward": float(total_reward),
        "hit": float(final_info.get("hit", False)),
        "timing_error": float(final_info.get("timing_error", np.nan)),
        "contact_velocity": float(final_info.get("contact_velocity", 0.0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scripted FlyOhtani episodes.")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--render", choices=["none", "human", "rgb_array"], default="none")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    render_mode = None if args.render == "none" else args.render
    env = FlyBatterEnv(render_mode=render_mode, seed=args.seed)
    controller = ScriptedSwingController()

    try:
        results = [run_episode(env, controller) for _ in range(args.episodes)]
    finally:
        env.close()

    hit_rate = sum(result["hit"] for result in results) / len(results)
    mean_reward = sum(result["reward"] for result in results) / len(results)
    print(f"episodes={len(results)} hit_rate={hit_rate:.3f} mean_reward={mean_reward:.3f}")
    for idx, result in enumerate(results, start=1):
        print(
            f"episode={idx} reward={result['reward']:.3f} hit={bool(result['hit'])} "
            f"timing_error={result['timing_error']:.4f} "
            f"contact_velocity={result['contact_velocity']:.4f}"
        )


if __name__ == "__main__":
    main()

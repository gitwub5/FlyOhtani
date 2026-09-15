from __future__ import annotations

import argparse

from envs import FlyBatterEnv


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a PPO baseline for FlyOhtani.")
    parser.add_argument("--timesteps", type=int, default=100_000)
    parser.add_argument("--model-out", default="ppo_fly_ohtani")
    args = parser.parse_args()

    try:
        from stable_baselines3 import PPO
    except ImportError as exc:
        raise SystemExit('Install RL dependencies with: pip install -e ".[rl]"') from exc

    env = FlyBatterEnv()
    model = PPO("MlpPolicy", env, verbose=1)
    model.learn(total_timesteps=args.timesteps)
    model.save(args.model_out)
    env.close()


if __name__ == "__main__":
    main()

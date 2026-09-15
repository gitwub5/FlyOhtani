from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def plot_rewards(rewards: np.ndarray, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(rewards, label="episode reward")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Reward")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot episode rewards from a .npy file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reward_curve.png"))
    args = parser.parse_args()

    rewards = np.load(args.input)
    plot_rewards(rewards, args.out)


if __name__ == "__main__":
    main()

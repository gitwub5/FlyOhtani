from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def plot_weight_heatmap(weights: np.ndarray, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    image = ax.imshow(weights, aspect="auto", cmap="viridis")
    ax.set_xlabel("Post-synaptic neuron")
    ax.set_ylabel("Pre-synaptic neuron")
    fig.colorbar(image, ax=ax, label="Weight")
    fig.tight_layout()
    fig.savefig(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot a weight matrix from a .npy file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, default=Path("weight_heatmap.png"))
    args = parser.parse_args()

    weights = np.load(args.input)
    plot_weight_heatmap(weights, args.out)


if __name__ == "__main__":
    main()

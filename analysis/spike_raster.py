from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def plot_spike_raster(spikes: np.ndarray, out_path: Path) -> None:
    time_idx, neuron_idx = np.nonzero(spikes)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.scatter(time_idx, neuron_idx, s=4, color="black")
    ax.set_xlabel("Time step")
    ax.set_ylabel("Neuron")
    fig.tight_layout()
    fig.savefig(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot a spike raster from a 2D .npy array.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, default=Path("spike_raster.png"))
    args = parser.parse_args()

    spikes = np.load(args.input)
    plot_spike_raster(spikes, args.out)


if __name__ == "__main__":
    main()

"""I-07c-swing deliverable (docs/design/BATTING-QUALITY-AND-SWING.md section
3: '위/측면 배트 궤적 그림'): top (XY) and side (XZ) bat-tip world
trajectory plots, before (prep_swing=-1.9) vs after (prep_swing=-1.96), for
the mid_mid course."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.swing_experiment import run_episode

OUT_DIR = Path("runs/env002-b1-i07c-swing")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    before, before_tl = run_episode(-1.9, 0.094091)
    after, after_tl = run_episode(-1.96, 0.09425316355759385)

    fig, (ax_top, ax_side) = plt.subplots(1, 2, figsize=(12, 5))

    for label, tl, color in (("before (prep=-1.90)", before_tl, "tab:blue"), ("after (prep=-1.96)", after_tl, "tab:orange")):
        pts = np.array([row["bat_tip_world"] for row in tl])
        contact_idx = next((i for i, row in enumerate(tl) if row["contact_occurred"]), None)
        ax_top.plot(pts[:, 0], pts[:, 1], color=color, label=label, linewidth=1.2)
        ax_side.plot(pts[:, 0], pts[:, 2], color=color, label=label, linewidth=1.2)
        if contact_idx is not None:
            ax_top.scatter([pts[contact_idx, 0]], [pts[contact_idx, 1]], color=color, marker="x", s=80, zorder=5)
            ax_side.scatter([pts[contact_idx, 0]], [pts[contact_idx, 2]], color=color, marker="x", s=80, zorder=5)

    ax_top.set_xlabel("world x (m)")
    ax_top.set_ylabel("world y (m)")
    ax_top.set_title("bat-tip trajectory, top view (XY)\n(x marks bat/ball contact)")
    ax_top.legend()
    ax_top.axis("equal")

    ax_side.set_xlabel("world x (m)")
    ax_side.set_ylabel("world z (m)")
    ax_side.set_title("bat-tip trajectory, side view (XZ)\n(x marks bat/ball contact)")
    ax_side.legend()
    ax_side.axis("equal")

    fig.suptitle("I-07c-swing: mid_mid bat-tip trajectory, before vs after")
    fig.tight_layout()
    out_path = OUT_DIR / "bat_tip_trajectory_before_after.png"
    fig.savefig(out_path, dpi=150)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

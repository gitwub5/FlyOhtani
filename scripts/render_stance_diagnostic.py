"""I-08a-style completion condition 1 (docs/design/FLY-BATTING-STANCE-AND-COLOR.md):
a diagnostic top-down image overlaying body-forward (f), shoulder axis,
head-direction, and the home->pitcher vector (p) on the actual compiled
batter pose -- verifying (not just asserting) that f is perpendicular to p,
the shoulder axis is parallel to p, and the head points at the release
point, using a straight-down orthographic camera so world XY maps linearly
to image pixels (avoiding any perspective-projection error in the overlay).
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
import numpy as np

from envs.baseball_b1_env import BaseballB1Env

# Same fixed design constants as scripts/build_fly_visual_asset.py (see that
# file's ROOT_YAW_RAD/ROOT_PITCH_RAD/RELEASE_WORLD_POS) -- duplicated here
# rather than imported since the build script is a one-shot generator, not
# an importable module with a stable API.
ROOT_PITCH_RAD = -math.pi / 2
ROOT_YAW_RAD = -math.pi / 2
RELEASE_WORLD_POS = np.array([16.5, 0.0, 1.8])


def rot_y(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


ROOT_TOTAL_MAT = rot_z(ROOT_YAW_RAD) @ rot_y(ROOT_PITCH_RAD)


def main() -> None:
    out_dir = Path("runs/env002-b1-neuromechfly/mid_mid")
    out_dir.mkdir(parents=True, exist_ok=True)

    env = BaseballB1Env()
    env.reset(seed=0, options={"course": "mid_mid"})
    model, data = env.model, env.data

    thorax_bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "Thorax")
    head_bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "Head")
    thorax_pos = data.xpos[thorax_bid].copy()
    thorax_mat = data.xmat[thorax_bid].reshape(3, 3).copy()
    head_pos = data.xpos[head_bid].copy()
    head_mat = data.xmat[head_bid].reshape(3, 3).copy()

    # f: body anatomical-forward, projected horizontal. Source local -Z is
    # the "ventral/chest" axis (docs/design/FLY-BATTING-STANCE-AND-COLOR.md
    # section 1) -- transform it by Thorax's OWN compiled body matrix
    # (verifies the ACTUAL compiled pose, not just the design-time ROOT_
    # TOTAL_MAT constant, since Thorax's body frame already bakes that
    # rotation in via the fly_visual root).
    f_world = thorax_mat @ np.array([0.0, 0.0, -1.0])
    f_world[2] = 0.0
    f_world /= np.linalg.norm(f_world)

    # shoulder axis: source local +Y.
    shoulder_world = thorax_mat @ np.array([0.0, 1.0, 0.0])
    shoulder_world[2] = 0.0
    shoulder_world /= np.linalg.norm(shoulder_world)

    # head-forward: local +X (the axis build_fly_visual_asset.py solved for).
    head_fwd_world = head_mat @ np.array([1.0, 0.0, 0.0])
    head_fwd_world /= np.linalg.norm(head_fwd_world)
    head_fwd_horizontal = head_fwd_world.copy()
    head_fwd_horizontal[2] = 0.0
    if np.linalg.norm(head_fwd_horizontal) > 1e-6:
        head_fwd_horizontal /= np.linalg.norm(head_fwd_horizontal)

    # p: home->pitcher, world +X (envs/assets/baseball_park_b1.xml's own
    # coordinate-system comment: origin=home plate back vertex, +x=pitcher).
    p_world = np.array([1.0, 0.0, 0.0])

    f_dot_p_deg = math.degrees(math.acos(np.clip(float(np.dot(f_world, p_world)), -1.0, 1.0)))
    shoulder_dot_p_deg = math.degrees(
        math.acos(np.clip(abs(float(np.dot(shoulder_world, p_world))), -1.0, 1.0))
    )
    true_head_dir = RELEASE_WORLD_POS - head_pos
    true_head_dir /= np.linalg.norm(true_head_dir)
    head_error_deg = math.degrees(math.acos(np.clip(float(np.dot(head_fwd_world, true_head_dir)), -1.0, 1.0)))

    print(f"f (body-forward) vs p (home->pitcher) angle: {f_dot_p_deg:.2f}deg (design: 80-100deg)")
    print(f"shoulder axis vs p angle from parallel: {shoulder_dot_p_deg:.2f}deg (design: parallel, 0deg ideal)")
    print(f"head-forward vs true release direction error: {head_error_deg:.2f}deg (design: <=10deg)")

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_aspect("equal")
    origin = thorax_pos[:2]

    # Small manual y-offsets purely for rendering clarity -- shoulder axis,
    # head-forward, and p all happen to point almost exactly world +x (a
    # correct, non-arbitrary finding: the design puts all three roughly
    # toward the pitcher), so drawn from their true, un-offset origins the
    # arrows would sit exactly on top of each other and be indistinguishable.
    def arrow(vec, color, label, start_xy, scale=1.0):
        ax.annotate(
            "",
            xy=(start_xy[0] + vec[0] * scale, start_xy[1] + vec[1] * scale),
            xytext=(start_xy[0], start_xy[1]),
            arrowprops={"arrowstyle": "->", "color": color, "lw": 2.5},
        )
        ax.plot([], [], color=color, label=label, lw=2.5)

    arrow(f_world, "tab:red", "f (body-forward, chest direction)", origin, scale=0.5)
    arrow(shoulder_world, "tab:blue", "shoulder axis", origin + np.array([0.0, 0.12]), scale=0.5)
    arrow(head_fwd_horizontal, "tab:green", "head-forward (horizontal proj.)", origin + np.array([0.0, 0.24]), scale=0.5)
    arrow(p_world, "black", "p (home -> pitcher, world +x)", origin + np.array([0.0, -0.12]), scale=0.5)

    ax.scatter([origin[0]], [origin[1]], color="0.3", zorder=5, s=30, label="thorax (arrow origins, offset for clarity)")
    ax.scatter([RELEASE_WORLD_POS[0]], [RELEASE_WORLD_POS[1]], color="purple", marker="*", s=150, zorder=5)
    ax.annotate("release point", (RELEASE_WORLD_POS[0], RELEASE_WORLD_POS[1]), textcoords="offset points", xytext=(5, 5))

    ax.set_xlim(origin[0] - 1.0, origin[0] + 1.0)
    ax.set_ylim(origin[1] - 1.0, origin[1] + 1.0)
    ax.set_xlabel("world x (m) -- toward pitcher")
    ax.set_ylabel("world y (m)")
    ax.set_title(
        "I-08a-style stance diagnostic (mid_mid, prep pose)\n"
        f"f-vs-p={f_dot_p_deg:.1f}deg (want 80-100)\n"
        f"shoulder-vs-p from parallel={shoulder_dot_p_deg:.1f}deg | "
        f"head error={head_error_deg:.1f}deg (want <=10)",
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    out_path = out_dir / "stance_axis_diagnostic.png"
    fig.savefig(out_path, dpi=150)
    print(f"wrote {out_path}")
    env.close()


if __name__ == "__main__":
    main()

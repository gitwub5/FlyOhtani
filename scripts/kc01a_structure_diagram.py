"""KC-01a deliverable: kinematic-chain structure diagram (docs/design/
KC-01a-TORSO-BAT-COORDINATION.md section 1's text tree, rendered as a
figure). Pure documentation output -- draws boxes/arrows from constants
copied from the design doc, does not run any physics."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT_DIR = Path(__file__).resolve().parent.parent / "runs" / "kc01a-comparison"

CX = 2.3  # main spine x-center
W = 2.6


def box(ax, y_bottom, h, text, x_center=CX, w=W, fc="#eef3fb", ec="#3a5a8a"):
    x = x_center - w / 2
    patch = FancyBboxPatch(
        (x, y_bottom), w, h, boxstyle="round,pad=0.02,rounding_size=0.02", fc=fc, ec=ec, lw=1.5
    )
    ax.add_patch(patch)
    ax.text(x_center, y_bottom + h / 2, text, ha="center", va="center", fontsize=8.5)
    return (x_center, y_bottom), (x_center, y_bottom + h)  # (bottom_anchor, top_anchor)


def arrow(ax, p_from, p_to, label=None, label_dx=0.05):
    a = FancyArrowPatch(p_from, p_to, arrowstyle="-|>", mutation_scale=14, color="#333333", lw=1.5)
    ax.add_patch(a)
    if label:
        mx, my = (p_from[0] + p_to[0]) / 2, (p_from[1] + p_to[1]) / 2
        ax.text(mx + label_dx, my, label, fontsize=7.5, color="#555555", va="center")


def main() -> None:
    fig, ax = plt.subplots(figsize=(7.5, 11))
    ax.set_xlim(-0.3, 5.0)
    ax.set_ylim(0, 13)
    ax.axis("off")

    gap = 0.35
    y = 11.6
    h0 = 0.9
    world_bottom, _world_top = box(ax, y, h0, "world\n(fixed)", fc="#f0f0f0", ec="#555555")
    y -= h0 + gap

    h1 = 1.5
    torso_bottom, torso_top = box(
        ax,
        y,
        h1,
        "torso_body\npos=(0.1,0.9,1.0), base fixed\n[joint] torso_yaw: hinge, axis (0,0,1)\nrange +/-0.6 rad, gear 30\nmass 35kg (engineering assumption)",
    )
    arrow(ax, world_bottom, torso_top)
    y -= h1 + gap

    h2 = 1.1
    bat_body_bottom, bat_body_top = box(
        ax,
        y,
        h2,
        "bat_body\nlocal pos (0.15,-0.25,0)\n[joint] bat_hinge (swing): axis (0,0,1)\nrange +/-2.0 rad, gear 30 (= B1)",
    )
    arrow(ax, torso_bottom, bat_body_top, "child of\ntorso_body", label_dx=1.55)
    y -= h2 + gap

    h3 = 1.1
    tilt_bottom, tilt_top = box(
        ax,
        y,
        h3,
        "bat_tilt_body\n[joint] bat_tilt_hinge: axis (0,-1,0)\nrange +/-0.6 rad, gear 6 (= B1)",
    )
    arrow(ax, bat_body_bottom, tilt_top, "child of\nbat_body", label_dx=1.55)
    y -= h3 + gap

    h4 = 0.9
    _geom_bottom, geom_top = box(
        ax, y, h4, "bat_geom (capsule) + grip_L / grip_R\nmass 0.9kg (= B1)"
    )
    arrow(ax, tilt_bottom, geom_top, "child of\nbat_tilt_body", label_dx=1.55)
    y -= h4 + 0.6

    # fly_visual branch, offset to the left of torso_body
    vis_x = 0.5
    _vis_bottom, vis_top = box(
        ax,
        torso_bottom[1] - 1.35,
        1.15,
        "fly_visual_body.xml\n(NeuroMechFly rig,\nmassless, non-colliding)\nfollows torso_yaw via\nordinary kinematics",
        x_center=vis_x,
        w=2.1,
        fc="#fdf3e7",
        ec="#a06a1f",
    )
    arrow(ax, (torso_bottom[0] - 0.6, torso_bottom[1] + 0.15), vis_top, "child of\ntorso_body", label_dx=0.1)

    ax.text(
        4.2,
        (bat_body_top[1] + tilt_bottom[1]) / 2,
        "World-frame bat yaw\n≈ torso_yaw + local\nswing angle (exact\nrelation is nonlinear\nvia bat_body's own\noffset -- section 1).\n\nContact-point velocity\n= full-Jacobian mj_jac()\nover ALL qvel, so\ntorso_yaw's contribution\nis included automatically.",
        fontsize=7.5,
        ha="left",
        va="center",
        style="italic",
        color="#444444",
    )

    ax.text(
        CX,
        y - 0.2,
        "Reaction: bat/ball impact reaches torso_yaw through this same chain\n"
        "(verified: qfrc_constraint spikes on torso_yaw during contact --\n"
        "tests/test_baseball_kc01a_env.py). Base stays fixed this round: torso\n"
        "rotates in place, no ground reaction force / leg support yet (KC-01b).",
        fontsize=8,
        ha="center",
        va="top",
        color="#333333",
    )

    ax.set_title("KC-01a kinematic chain (mid_mid)", fontsize=13, fontweight="bold", pad=10)
    fig.tight_layout()
    out_path = OUT_DIR / "kc01a_structure_diagram.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

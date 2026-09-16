"""KC-01a deliverable: torso/bat angle and velocity graphs across the 4
comparison conditions (docs/design/KC-01a-TORSO-BAT-COORDINATION.md
section 6). Reads the timelines scripts/kc01a_compare_conditions.py wrote
to docs/records/evidence/KC-01a-timelines/<condition>.json; does not
re-run any physics."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

TIMELINE_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence" / "KC-01a-timelines"
OUT_DIR = Path(__file__).resolve().parent.parent / "runs" / "kc01a-comparison"

CONDITIONS = ["arm_only", "torso_only", "simultaneous", "staggered"]
COLORS = {"arm_only": "tab:blue", "torso_only": "tab:orange", "simultaneous": "tab:green", "staggered": "tab:red"}


def load(cond: str) -> list[dict]:
    return json.loads((TIMELINE_DIR / f"{cond}.json").read_text())


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False)
    ax_torso_angle, ax_torso_vel, ax_swing_angle, ax_swing_vel = axes.flatten()

    for cond in CONDITIONS:
        rows = load(cond)
        t = [r["t"] for r in rows]
        color = COLORS[cond]
        ax_torso_angle.plot(t, [r["torso_angle"] for r in rows], label=cond, color=color)
        ax_torso_vel.plot(t, [r["torso_vel"] for r in rows], label=cond, color=color)
        ax_swing_angle.plot(t, [r["swing_angle"] for r in rows], label=cond, color=color)
        ax_swing_vel.plot(t, [r["swing_vel"] for r in rows], label=cond, color=color)
        # mark first-contact time if any
        contact_rows = [r["t"] for r in rows if r["contact_occurred"]]
        if contact_rows:
            for ax in (ax_torso_angle, ax_torso_vel, ax_swing_angle, ax_swing_vel):
                ax.axvline(contact_rows[0], color=color, linestyle=":", alpha=0.4)

    ax_torso_angle.set_title("torso_yaw angle (rad)")
    ax_torso_vel.set_title("torso_yaw velocity (rad/s)")
    ax_swing_angle.set_title("bat_hinge (swing) angle (rad)")
    ax_swing_vel.set_title("bat_hinge (swing) velocity (rad/s)")
    for ax in axes.flatten():
        ax.set_xlabel("time (s)")
        ax.axhline(0, color="k", lw=0.5)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)

    fig.suptitle(
        "KC-01a mid_mid: torso/bat angle & velocity per condition\n"
        "(dotted vertical line = that condition's first bat-ball contact)"
    )
    fig.tight_layout()
    out_path = OUT_DIR / "kc01a_angle_velocity_comparison.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")

    # Second figure: control signals (ctrl) per condition, to show WHEN
    # each axis is actually being driven.
    fig2, axes2 = plt.subplots(4, 1, figsize=(10, 10), sharex=False)
    for ax, cond in zip(axes2, CONDITIONS, strict=True):
        rows = load(cond)
        t = [r["t"] for r in rows]
        ax.plot(t, [r["torso_ctrl"] for r in rows], label="torso_ctrl", color="tab:purple")
        ax.plot(t, [r["swing_ctrl"] for r in rows], label="swing_ctrl", color="tab:brown")
        contact_rows = [r["t"] for r in rows if r["contact_occurred"]]
        if contact_rows:
            ax.axvline(contact_rows[0], color="k", linestyle=":", alpha=0.5, label="first contact")
        ax.set_title(cond)
        ax.set_ylim(-1.1, 1.1)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(alpha=0.3)
    axes2[-1].set_xlabel("time (s)")
    fig2.suptitle("KC-01a mid_mid: control signals per condition (when each axis is driven)")
    fig2.tight_layout()
    out_path2 = OUT_DIR / "kc01a_control_signals_comparison.png"
    fig2.savefig(out_path2, dpi=150)
    print(f"Wrote {out_path2}")


if __name__ == "__main__":
    main()

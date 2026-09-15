"""I-07a-1 item A: contact-boundary numerical convergence investigation for
BaseballB0Env, across physics_dt candidates, with control_dt/initial-state/
action-clock held fixed per docs/implementation/WORK_PACKAGES.md's I-07a-1
protocol.

Two independent experiments, run separately so action-clock quantization and
physics-dt effects are not conflated:

  A1. Torque-timetable replay: record the exact per-control-step ctrl
      sequence from one canonical scripted run (control_dt=0.005s fixed),
      then replay that exact sequence (no controller re-invocation) at each
      candidate physics_dt, with frame_skip = round(control_dt/dt) so the
      action clock stays at the same 5ms grid for every dt.

  A2. Fine onset diagnostic: swing torque switches at the same *physical*
      time for every dt, checked at physics-substep resolution (frame_skip=1
      for this experiment only), removing the control_dt grid as a variable
      entirely. Used to locate the hit/miss boundary onset time precisely.

Outputs (this script writes both under runs/i07a1-convergence/):
  - onset_scan.csv: A2 results for a coarse 1ms scan over [0.12, 0.22]s at
    each dt, plus refined points near any transition.
  - replay_schedule.csv: A1 per-dt outcome for the fixed recorded schedule.
  - convergence.png: contact time / min surface gap vs onset time, one
    subplot per dt, boundary markers.
  - summary.json: boundary locations, pairwise differences, decision.

Run: .venv/bin/python analysis/env002_dt_convergence.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from controllers.baseball_scripted import BaseballScriptedSwing
from envs.baseball_env import BaseballB0Env

OUT_DIR = Path("runs/i07a1-convergence")
CONTROL_DT = 0.005
DT_CANDIDATES = [0.0005, 0.00025, 0.000125, 0.0000625]
SEED = 0


def ball_bat_gap(env: BaseballB0Env) -> float:
    """Closest-approach distance between the ball's surface and the bat
    capsule's surface (negative if overlapping), computed independently of
    the contact solver -- a continuous geometric measure usable even when
    MuJoCo reports no discrete contact."""
    ball_pos = env.data.xpos[env.ball_body_id]
    ball_r = env.model.geom_size[env.ball_geom_id][0]
    origin = env.data.geom_xpos[env.bat_geom_id]
    xmat = env.data.geom_xmat[env.bat_geom_id].reshape(3, 3)
    z_axis = xmat[:, 2]
    half_len = env.model.geom_size[env.bat_geom_id][1]
    bat_r = env.model.geom_size[env.bat_geom_id][0]
    p0 = origin - half_len * z_axis
    p1 = origin + half_len * z_axis
    d = p1 - p0
    t = np.clip(np.dot(ball_pos - p0, d) / np.dot(d, d), 0, 1)
    closest = p0 + t * d
    center_dist = float(np.linalg.norm(closest - ball_pos))
    return center_dist - ball_r - bat_r


def run_fine_onset(dt: float, onset_time: float, seed: int = SEED) -> dict:
    """A2: frame_skip=1 (action clock == physics clock); ctrl switches to
    swing_ctrl the first substep where data.time >= onset_time."""
    env = BaseballB0Env(frame_skip=1)
    env.model.opt.timestep = dt
    env.max_steps = 10**7
    controller = BaseballScriptedSwing(prep_angle=env.prep_angle)
    env.reset(seed=seed)
    min_gap = float("inf")
    swinging = False
    onset_actual = None
    info: dict = {}
    while True:
        if not swinging and env.data.time >= onset_time:
            swinging = True
            onset_actual = float(env.data.time)
        action = np.array([controller.swing_ctrl if swinging else 0.0], dtype=np.float32)
        _, _, terminated, truncated, info = env.step(action)
        min_gap = min(min_gap, ball_bat_gap(env))
        if terminated or truncated:
            break
    env.close()
    return {
        "dt": dt,
        "onset_requested": onset_time,
        "onset_actual": onset_actual,
        "hit": bool(info["hit"]),
        "end_reason": info["end_reason"],
        "contact_time_s": info["contact_time_s"],
        "min_surface_gap_m": min_gap,
        "bat_angle_at_end": None,  # filled by caller if needed
    }


def record_canonical_schedule(dt: float = 0.0005, seed: int = SEED) -> list[float]:
    """Runs the scripted controller once at control_dt=CONTROL_DT and
    records the ctrl issued at every control step, for A1's no-controller
    replay."""
    frame_skip = round(CONTROL_DT / dt)
    env = BaseballB0Env(frame_skip=frame_skip)
    env.model.opt.timestep = dt
    controller = BaseballScriptedSwing(prep_angle=env.prep_angle)
    obs, _ = env.reset(seed=seed)
    controller.reset()
    schedule = []
    while True:
        action = controller.act(obs)
        schedule.append(float(action[0]))
        obs, _, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            break
    env.close()
    return schedule


def replay_schedule(dt: float, schedule: list[float], seed: int = SEED) -> dict:
    """A1: same control_dt=CONTROL_DT grid (frame_skip scaled to dt), ctrl
    taken from the recorded schedule by control-step index, no controller
    logic re-invoked."""
    frame_skip = round(CONTROL_DT / dt)
    env = BaseballB0Env(frame_skip=frame_skip)
    env.model.opt.timestep = dt
    env.max_steps = max(len(schedule) + 20, env.max_steps)
    env.reset(seed=seed)
    info: dict = {}
    for i, ctrl in enumerate(schedule):
        action = np.array([ctrl], dtype=np.float32)
        _, _, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
    env.close()
    return {
        "dt": dt,
        "frame_skip": frame_skip,
        "control_dt": dt * frame_skip,
        "steps_replayed": i + 1,
        "hit": bool(info.get("hit")),
        "end_reason": info.get("end_reason"),
        "contact_time_s": info.get("contact_time_s"),
    }


def refine_boundary(dt: float, lo: float, hi: float, min_res: float = 0.0000625) -> float:
    """Bisect [lo(miss), hi(hit)] (or vice versa) down to min_res resolution
    (default 0.0625ms) and return the boundary onset time (midpoint of the
    final bracket)."""
    hit_lo = run_fine_onset(dt, lo)["hit"]
    hit_hi = run_fine_onset(dt, hi)["hit"]
    if hit_lo == hit_hi:
        return float("nan")  # no transition in this bracket
    while (hi - lo) > min_res:
        mid = (lo + hi) / 2
        hit_mid = run_fine_onset(dt, mid)["hit"]
        if hit_mid == hit_lo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- A2: coarse scan, 1ms resolution, 0.12..0.22s ---
    scan_times = np.round(np.arange(0.12, 0.2201, 0.001), 6)
    scan_rows = []
    per_dt_scan: dict[float, list[dict]] = {dt: [] for dt in DT_CANDIDATES}
    for dt in DT_CANDIDATES:
        for t in scan_times:
            r = run_fine_onset(dt, float(t))
            per_dt_scan[dt].append(r)
            scan_rows.append(r)
        print(f"dt={dt}: coarse scan done")

    # locate the single hit/miss transition bracket per dt (assumes monotonic
    # miss->hit->miss-again is NOT expected here; verify and report if found)
    boundaries: dict[float, list[float]] = {}
    for dt in DT_CANDIDATES:
        hits = [r["hit"] for r in per_dt_scan[dt]]
        transitions = [
            i for i in range(len(hits) - 1) if hits[i] != hits[i + 1]
        ]
        edges = []
        for i in transitions:
            lo, hi = float(scan_times[i]), float(scan_times[i + 1])
            edge = refine_boundary(dt, lo, hi)
            edges.append(edge)
        boundaries[dt] = edges
        print(f"dt={dt}: {len(transitions)} transition(s) in scan -> refined boundaries {edges}")

    # refine further to 0.125ms then 0.0625ms explicitly for the two finest dts
    fine_boundaries: dict[float, list[float]] = {}
    for dt in DT_CANDIDATES:
        fine_boundaries[dt] = [
            refine_boundary(dt, b - 0.0005, b + 0.0005, min_res=0.0000625)
            if not np.isnan(b)
            else float("nan")
            for b in boundaries[dt]
        ]

    # --- A1: torque-timetable replay ---
    schedule = record_canonical_schedule(dt=0.0005, seed=SEED)
    replay_rows = [replay_schedule(dt, schedule, seed=SEED) for dt in DT_CANDIDATES]

    # --- write CSVs ---
    with (OUT_DIR / "onset_scan.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "dt",
                "onset_requested",
                "onset_actual",
                "hit",
                "end_reason",
                "contact_time_s",
                "min_surface_gap_m",
            ],
        )
        w.writeheader()
        for r in scan_rows:
            w.writerow({k: r[k] for k in w.fieldnames})

    with (OUT_DIR / "replay_schedule.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(replay_rows[0].keys()))
        w.writeheader()
        for r in replay_rows:
            w.writerow(r)

    # --- decision ---
    finest_two = sorted(DT_CANDIDATES)[:2]
    boundary_diffs = {}
    if fine_boundaries[finest_two[0]] and fine_boundaries[finest_two[1]]:
        b0 = fine_boundaries[finest_two[0]][0]
        b1 = fine_boundaries[finest_two[1]][0]
        boundary_diffs["finest_two_diff_s"] = None if (np.isnan(b0) or np.isnan(b1)) else abs(b0 - b1)

    # common-hit contact time agreement, among onsets >1ms from any dt's boundary
    all_boundaries = [b for edges in fine_boundaries.values() for b in edges if not np.isnan(b)]
    agreement_rows = []
    for t in scan_times:
        if all_boundaries and min(abs(t - b) for b in all_boundaries) <= 0.001:
            continue  # too close to a boundary, skip from the "far" agreement check
        hits = {dt: next(r for r in per_dt_scan[dt] if r["onset_requested"] == t)["hit"] for dt in DT_CANDIDATES}
        agree = len(set(hits.values())) == 1
        agreement_rows.append({"onset": float(t), "agree": agree, "hits": hits})
    n_far = len(agreement_rows)
    n_agree = sum(1 for r in agreement_rows if r["agree"])

    common_hit_time_diffs = []
    for t in scan_times:
        rows = {dt: next(r for r in per_dt_scan[dt] if r["onset_requested"] == t) for dt in DT_CANDIDATES}
        if all(rows[dt]["hit"] for dt in DT_CANDIDATES):
            times = [rows[dt]["contact_time_s"] for dt in DT_CANDIDATES]
            common_hit_time_diffs.append(max(times) - min(times))

    summary = {
        "dt_candidates": DT_CANDIDATES,
        "control_dt_s": CONTROL_DT,
        "seed": SEED,
        "scan_range_s": [0.12, 0.22],
        "scan_resolution_s": 0.001,
        "boundaries_per_dt_coarse": boundaries,
        "boundaries_per_dt_refined_0.0625ms": fine_boundaries,
        "finest_two_dt": finest_two,
        "boundary_diff_finest_two_s": boundary_diffs.get("finest_two_diff_s"),
        "far_from_boundary_agreement": f"{n_agree}/{n_far}",
        "common_hit_contact_time_max_diff_s": max(common_hit_time_diffs) if common_hit_time_diffs else None,
        "replay_schedule_outcomes": replay_rows,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))

    # --- plot ---
    fig, axes = plt.subplots(len(DT_CANDIDATES), 1, figsize=(8, 10), sharex=True)
    for ax, dt in zip(axes, DT_CANDIDATES):
        rows = per_dt_scan[dt]
        xs = [r["onset_requested"] for r in rows]
        gaps = [r["min_surface_gap_m"] for r in rows]
        colors = ["tab:green" if r["hit"] else "tab:red" for r in rows]
        ax.scatter(xs, gaps, c=colors, s=10)
        ax.axhline(0, color="gray", linewidth=0.5)
        for b in fine_boundaries[dt]:
            if not np.isnan(b):
                ax.axvline(b, color="black", linestyle="--", linewidth=1)
        ax.set_ylabel(f"dt={dt}\nmin gap (m)")
    axes[-1].set_xlabel("swing onset time (s)")
    fig.suptitle("ENV-002 B0: min ball-bat surface gap vs swing onset, by physics_dt\n(green=hit, red=miss, dashed=refined boundary)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "convergence.png", dpi=120)
    print(f"saved plot to {OUT_DIR / 'convergence.png'}")


if __name__ == "__main__":
    main()

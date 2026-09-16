"""KC-01a calibration (docs/design/KC-01a-TORSO-BAT-COORDINATION.md section
2): reproduces the numbers frozen in envs/kc01a/config.py and the XML's own
gear -- run this to regenerate/verify them, not to discover new ones on
every run (the trigger-time sweeps are a coarse, first-working-window
search, not a global optimizer; re-running can land on a different point
in a working window, which is fine, but won't necessarily reproduce the
exact frozen values bit-for-bit). Three independent steps:

1. Target-angle geometry search (mid_mid only): for each coordination
   condition, minimize the bat capsule's distance to the course target
   point over the axes that are free to move.
2. torso_motor gear sweep: no-ball, arm held at prep, ctrl=+1 on torso
   alone, time to reach 0.5rad, smallest gear meeting a 0.30s budget.
3. Trigger-time sweep per condition: run full mid_mid episodes with the
   step-2 gear and step-1 targets, sweep crossing time(s), report the
   first stable (repeated-neighbor) valid-hit window found.

Writes docs/design/KC-01a-calibration.json with everything, and prints a
summary. Takes ~1-2 minutes (many short episodes).
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball.courses import COURSES
from envs.baseball_kc01a_env import BaseballKC01aEnv

TARGET = COURSES["mid_mid"].copy()
CONTACT_THRESHOLD = 0.0366 + 0.025  # ball radius + bat capsule radius
SWING_LIMIT = (-2.0, 2.0)
TILT_LIMIT = (-0.6, 0.6)
TORSO_LIMIT = (-0.6, 0.6)
PREP_TORSO, PREP_SWING, PREP_TILT = 0.0, -1.96, 0.0


def _clip(v, lim):
    return float(np.clip(v, lim[0], lim[1]))


def bat_closest_distance(env: BaseballKC01aEnv, torso: float, swing: float, tilt: float) -> float:
    env.data.qpos[env.torso_qpos_adr] = torso
    env.data.qpos[env.swing_qpos_adr] = swing
    env.data.qpos[env.tilt_qpos_adr] = tilt
    mujoco.mj_forward(env.model, env.data)
    p0 = env.data.geom_xpos[env.bat_geom_id].copy()
    mat = env.data.geom_xmat[env.bat_geom_id].reshape(3, 3)
    # capsule cylinder axis is canonicalized to the geom's own LOCAL Z for
    # a fromto-defined capsule (verified against B1's own known
    # ALIGNMENT['mid_mid'] solution).
    axis = mat @ np.array([0.0, 0.0, 1.0])
    half_len = 0.425
    p1, p2 = p0 - axis * half_len, p0 + axis * half_len
    seg = p2 - p1
    t = np.clip(np.dot(TARGET - p1, seg) / np.dot(seg, seg), 0.0, 1.0)
    closest = p1 + t * seg
    return float(np.linalg.norm(TARGET - closest))


def grid_refine(env, torso_fixed, swing_range, tilt_range, coarse=0.02, fine=0.002):
    swing_range = (max(swing_range[0], SWING_LIMIT[0]), min(swing_range[1], SWING_LIMIT[1]))
    tilt_range = (max(tilt_range[0], TILT_LIMIT[0]), min(tilt_range[1], TILT_LIMIT[1]))
    best = None
    for sw in np.arange(*swing_range, coarse):
        for ti in np.arange(*tilt_range, coarse):
            d = bat_closest_distance(env, torso_fixed, sw, ti)
            if best is None or d < best[0]:
                best = (d, sw, ti)
    _, sw0, ti0 = best
    best = None
    for sw in np.arange(_clip(sw0 - coarse, SWING_LIMIT), _clip(sw0 + coarse, SWING_LIMIT), fine):
        for ti in np.arange(_clip(ti0 - coarse, TILT_LIMIT), _clip(ti0 + coarse, TILT_LIMIT), fine):
            d = bat_closest_distance(env, torso_fixed, sw, ti)
            if best is None or d < best[0]:
                best = (d, sw, ti)
    return best


def torso_only_search(env, swing_fixed, tilt_fixed, torso_range, coarse=0.01, fine=0.001):
    torso_range = (max(torso_range[0], TORSO_LIMIT[0]), min(torso_range[1], TORSO_LIMIT[1]))
    best = None
    for to in np.arange(*torso_range, coarse):
        d = bat_closest_distance(env, to, swing_fixed, tilt_fixed)
        if best is None or d < best[0]:
            best = (d, to)
    _, to0 = best
    best = None
    for to in np.arange(_clip(to0 - coarse, TORSO_LIMIT), _clip(to0 + coarse, TORSO_LIMIT), fine):
        d = bat_closest_distance(env, to, swing_fixed, tilt_fixed)
        if best is None or d < best[0]:
            best = (d, to)
    return best


def step1_geometry(env) -> dict:
    d1, sw1, ti1 = grid_refine(env, 0.0, (-2.0, 2.0), (-0.6, 0.6))
    d2, to2 = torso_only_search(env, PREP_SWING, PREP_TILT, (-0.6, 0.6))
    shared = {}
    for tt in (-0.2, -0.3, -0.4, -0.5):
        d, sw, ti = grid_refine(env, tt, (-2.0, 2.0), (-0.6, 0.6))
        shared[tt] = {"dist": d, "swing": sw, "tilt": ti}
    return {
        "arm_only": {"dist": d1, "swing_target": sw1, "tilt_target": ti1},
        "torso_only": {"dist": d2, "torso_target": to2, "reachable": d2 <= CONTACT_THRESHOLD},
        "shared_candidates": shared,
        "contact_threshold_m": CONTACT_THRESHOLD,
    }


def step2_gear_sweep(env, candidate_gears, time_budget_s=0.30, target_angle=0.5) -> dict:
    results = {}
    for gear in candidate_gears:
        env.model.actuator_gear[env.torso_actuator_id, 0] = gear
        env.reset(seed=0, options={"course": "mid_mid"})
        env.set_held_pose(None, env.prep_swing, env.prep_tilt)
        t_reach = None
        for _ in range(400):
            _, _, terminated, truncated, _ = env.step(np.array([1.0, 0.0, 0.0], dtype=np.float32))
            if abs(float(env.data.qpos[env.torso_qpos_adr])) >= target_angle:
                t_reach = float(env.data.time)
                break
            if terminated or truncated:
                break
        results[gear] = t_reach
    env.model.actuator_gear[env.torso_actuator_id, 0] = 30.0  # restore XML default
    passing = [g for g, t in results.items() if t is not None and t <= time_budget_s]
    return {"results": results, "time_budget_s": time_budget_s, "chosen_gear": min(passing) if passing else None}


def run_episode(mode, torso_target, swing_target, torso_ct, swing_ct):
    """The non-participating axis is held by the controller's own hold-gain
    P-control (crossing_time=999.0, never triggered) -- NOT
    env.set_held_pose()'s hard qpos/qvel override. Using the hard lock here
    was tried first and found to change the ball-bat collision's effective
    dynamics enough to eliminate every valid arm_only hit across a wide
    trigger-time search (docs/design/KC-01a-TORSO-BAT-COORDINATION.md
    section 5) -- a real finding about this contact model's sensitivity,
    not a reason to keep searching for a hard-locked solution."""
    env = BaseballKC01aEnv(prep_torso=PREP_TORSO, prep_swing=PREP_SWING, prep_tilt=PREP_TILT)
    try:
        controller = TorsoBatController(
            mode, PREP_TORSO, PREP_SWING, PREP_TILT, torso_target, swing_target, torso_ct, swing_ct
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        info = {}
        while True:
            obs, _, term, trunc, info = env.step(controller.act(obs))
            if term or trunc:
                break
        return info
    finally:
        env.close()


def step3_trigger_sweeps() -> dict:
    out = {}

    best = None
    for ct in np.arange(0.085, 0.105, 0.0005):
        info = run_episode("arm_only", 0.0, -1.298, 999.0, ct)
        if info["scoring_valid"] and (best is None or info["batting_score"] > best[1]):
            best = (ct, info["batting_score"], info["bat_contact_vx"])
    out["arm_only"] = {"swing_crossing_time_s": 0.09425316355759385, "note": "reuses B1's own value; see spec section 5"}

    best = None
    for ct in np.arange(0.15, 0.45, 0.005):
        info = run_episode("torso_only", 0.496, PREP_SWING, ct, 999.0)
        vx = info["bat_contact_vx"] or -999
        if best is None or vx > best[1]:
            best = (ct, vx, info["scoring_valid"])
    out["torso_only"] = {"best_crossing_time_s": best[0], "best_bat_contact_vx": best[1], "ever_valid": best[2]}

    best = None
    for ct in np.arange(0.06, 0.40, 0.002):
        info = run_episode("simultaneous", -0.4, -0.726, ct, ct)
        if info["scoring_valid"] and (best is None or info["batting_score"] > best[1]):
            best = (ct, info["batting_score"], info["bat_contact_vx"])
    out["simultaneous"] = {"crossing_time_s": 0.096, "search_best": best}

    best = None
    for swing_ct in np.arange(0.08, 0.20, 0.004):
        for offset in np.arange(0.02, 0.16, 0.01):
            info = run_episode("staggered", -0.4, -0.726, swing_ct + offset, swing_ct)
            if info["scoring_valid"] and (best is None or info["batting_score"] > best[1]):
                best = (swing_ct, offset, info["batting_score"], info["bat_contact_vx"])
    out["staggered"] = {"swing_crossing_time_s": 0.122, "torso_lead_s": 0.12, "search_best": best}

    return out


def main() -> None:
    env = BaseballKC01aEnv()
    print("=== step 1: target geometry ===")
    geometry = step1_geometry(env)
    print(json.dumps(geometry, indent=2, default=str))

    print("\n=== step 2: torso_motor gear sweep ===")
    gear_sweep = step2_gear_sweep(env, [5, 10, 15, 20, 25, 30, 35, 40, 60, 80, 100])
    print(json.dumps(gear_sweep, indent=2, default=str))
    env.close()

    print("\n=== step 3: trigger-time sweeps (mid_mid) ===")
    triggers = step3_trigger_sweeps()
    print(json.dumps(triggers, indent=2, default=str))

    out_path = Path(__file__).resolve().parent.parent / "docs" / "design" / "KC-01a-calibration.json"
    out_path.write_text(
        json.dumps({"geometry": geometry, "gear_sweep": gear_sweep, "triggers": triggers}, indent=2, default=str)
    )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

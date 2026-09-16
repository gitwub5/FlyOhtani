"""KC-01a torso_lead_handoff search, v2 -- CORRECTED (docs/design/
KC-01a-DIRECTION-CONTRACT.md section 8). scripts/kc01a_torso_lead_handoff_
search.py's own winning candidate (torso_target=0.5) is preserved as a
labeled reference/diagnostic result, NOT deleted, because it revealed a
real gap in the earlier methodology: nothing checked that swing was
actually commanded in the SAME direction as torso, that swing's own
displacement was non-trivial, or that either axis's follow-through target
stayed inside its own joint range. That candidate had torso_dir=+1,
swing_dir=-1 (opposite), swing displacement of only -0.004rad (not a real
arm swing), and BOTH follow-through targets outside range (torso
0.5+0.15=0.65 > 0.6; swing -1.964-0.4=-2.364 < -2.0) -- none of which the
old search or the acceptance battery ever checked.

This version:
1. Applies controllers.baseball_kc01a.validate_same_direction_candidate()
   to every (torso_target, swing_target) pair BEFORE running any episode --
   an invalid candidate is excluded regardless of what score it would
   produce.
2. Re-derives swing_target under a DIRECTION- AND DISPLACEMENT-CONSTRAINED
   geometry search (swing_target restricted to >= prep_swing +
   MIN_SWING_DISPLACEMENT, not the old unconstrained closest-approach
   search that degenerates toward "torso does everything, swing barely
   moves or moves backward" as torso_target grows).
3. Uses the now-fixed (signed-progress) torso_lead_handoff trigger.
4. After finding valid+scoring candidates, checks whether each axis
   actually settles via ACTIVE BRAKING (final angle with margin from its
   own joint range) rather than by resting against a hard joint-limit
   stop, and prefers those.

gear/material/joint ranges are never touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from controllers.baseball_kc01a import (
    SWING_RANGE,
    TORSO_RANGE,
    TorsoBatController,
    validate_same_direction_candidate,
)
from envs.baseball.courses import COURSES
from envs.baseball_kc01a_env import BaseballKC01aEnv
from envs.fly_visual import FrontLegGripOverlay

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
TARGET = COURSES["mid_mid"].copy()
CONTACT_THRESHOLD = 0.0366 + 0.025
PREP_TORSO, PREP_SWING, PREP_TILT = 0.0, -1.96, 0.0
MIN_SWING_DISPLACEMENT = 0.3
JOINT_MARGIN = 0.02
SETTLE_MARGIN = 0.02  # how far from its own hard limit an axis's angle must stay to count as "not hitting the stop"

TORSO_TARGET_CANDIDATES = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]


def _clip(v, lim):
    return float(np.clip(v, lim[0], lim[1]))


def bat_closest_distance(env, torso, swing, tilt) -> float:
    env.data.qpos[env.torso_qpos_adr] = torso
    env.data.qpos[env.swing_qpos_adr] = swing
    env.data.qpos[env.tilt_qpos_adr] = tilt
    mujoco.mj_forward(env.model, env.data)
    p0 = env.data.geom_xpos[env.bat_geom_id].copy()
    mat = env.data.geom_xmat[env.bat_geom_id].reshape(3, 3)
    axis = mat @ np.array([0.0, 0.0, 1.0])
    half_len = 0.425
    p1, p2 = p0 - axis * half_len, p0 + axis * half_len
    seg = p2 - p1
    t = np.clip(np.dot(TARGET - p1, seg) / np.dot(seg, seg), 0.0, 1.0)
    closest = p1 + t * seg
    return float(np.linalg.norm(TARGET - closest))


def grid_refine_constrained(env, torso_fixed, swing_range, tilt_range, coarse=0.02, fine=0.002):
    """Same two-pass coarse->fine grid search as scripts/
    kc01a_same_direction_search.py's grid_refine, but the caller supplies a
    swing_range already restricted to the intended-direction, minimum-
    displacement region -- this function does not silently widen it."""
    swing_range = (max(swing_range[0], SWING_RANGE[0]), min(swing_range[1], SWING_RANGE[1]))
    tilt_range = (max(tilt_range[0], -0.6), min(tilt_range[1], 0.6))
    best = None
    for sw in np.arange(*swing_range, coarse):
        for ti in np.arange(*tilt_range, coarse):
            d = bat_closest_distance(env, torso_fixed, sw, ti)
            if best is None or d < best[0]:
                best = (d, sw, ti)
    _, sw0, ti0 = best
    best = None
    for sw in np.arange(_clip(sw0 - coarse, swing_range), _clip(sw0 + coarse, swing_range), fine):
        for ti in np.arange(_clip(ti0 - coarse, tilt_range), _clip(ti0 + coarse, tilt_range), fine):
            d = bat_closest_distance(env, torso_fixed, sw, ti)
            if best is None or d < best[0]:
                best = (d, sw, ti)
    return best


def constrained_geometry_search(env) -> dict:
    out = {}
    for tt in TORSO_TARGET_CANDIDATES:
        swing_lo = PREP_SWING + MIN_SWING_DISPLACEMENT  # same-direction (positive) + minimum displacement
        d, sw, ti = grid_refine_constrained(env, tt, (swing_lo, 2.0), (-0.6, 0.6))
        valid, reasons = validate_same_direction_candidate(PREP_TORSO, PREP_SWING, tt, sw)
        out[tt] = {
            "dist": d,
            "swing_target": sw,
            "tilt_target": ti,
            "reachable_geometrically": d <= CONTACT_THRESHOLD,
            "pre_filter_valid": valid,
            "pre_filter_reasons": reasons,
        }
    return out


def run_episode(torso_target, swing_target, torso_ct, handoff_fraction, record_settle=False):
    env = BaseballKC01aEnv(prep_torso=PREP_TORSO, prep_swing=PREP_SWING, prep_tilt=PREP_TILT)
    try:
        controller = TorsoBatController(
            "torso_lead_handoff", PREP_TORSO, PREP_SWING, PREP_TILT, torso_target, swing_target, torso_ct, 999.0,
            handoff_fraction=handoff_fraction,
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        torso_trig_t = swing_trig_t = None
        history = {"torso": [], "swing": []} if record_settle else None
        info = {}
        while True:
            t = float(env.data.time)
            if torso_trig_t is None and controller._torso_triggered:
                torso_trig_t = t
            if swing_trig_t is None and controller._swing_triggered:
                swing_trig_t = t
            action = controller.act(obs)
            if history is not None:
                history["torso"].append((t, float(env.data.qpos[env.torso_qpos_adr]), float(env.data.qvel[env.torso_qvel_adr]), controller._torso_axis.state))
                history["swing"].append((t, float(env.data.qpos[env.swing_qpos_adr]), float(env.data.qvel[env.swing_qvel_adr]), controller._swing_axis.state))
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        control_lead = None if (torso_trig_t is None or swing_trig_t is None) else swing_trig_t - torso_trig_t
        result = {
            "torso_target": torso_target,
            "swing_target": swing_target,
            "torso_ct": torso_ct,
            "handoff_fraction": handoff_fraction,
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
            "control_lead_s": control_lead,
        }
        if history is not None:
            result["history"] = history
        return result
    finally:
        env.close()


def settles_by_active_braking(history: list, joint_range: tuple[float, float]) -> dict:
    """Whether the LAST 0.3s of this axis's recorded history keeps the
    angle with SETTLE_MARGIN of its own hard joint-limit stop -- a proxy
    for "stopped because the PD brake actually converged", not "stopped
    because it is pinned against the mechanical limit" (docs/records/
    KC-01a-VALIDATION.md A12's finding that the earlier candidate's torso
    settled at 0.603rad, i.e. pressed against its own 0.6rad limit)."""
    if not history:
        return {"applicable": False}
    t_end = history[-1][0]
    tail = [h for h in history if h[0] >= t_end - 0.3]
    max_abs_angle = max(abs(h[1]) for h in tail)
    lo, hi = joint_range
    assert -lo == hi, "joint_range assumed symmetric (TORSO_RANGE/SWING_RANGE both are)"
    dist_from_limit = hi - max_abs_angle
    return {
        "applicable": True,
        "max_abs_angle_in_tail": max_abs_angle,
        "joint_range": joint_range,
        "distance_from_nearest_limit": dist_from_limit,
        "settles_by_active_braking": dist_from_limit >= SETTLE_MARGIN,
    }


def grip_reachability(torso_target, swing_target, torso_ct, handoff_fraction) -> dict:
    env = BaseballKC01aEnv(prep_torso=PREP_TORSO, prep_swing=PREP_SWING, prep_tilt=PREP_TILT)
    try:
        controller = TorsoBatController(
            "torso_lead_handoff", PREP_TORSO, PREP_SWING, PREP_TILT, torso_target, swing_target, torso_ct, 999.0,
            handoff_fraction=handoff_fraction,
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        overlay = FrontLegGripOverlay(env.model)
        max_err = 0.0
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, _info = env.step(action)
            errs = overlay.update(env.model, env.data)
            max_err = max(max_err, errs["L"], errs["R"])
            if terminated or truncated:
                break
        return {"max_grip_reach_error_m": max_err, "always_reachable": max_err <= 1e-9}
    finally:
        env.close()


def main() -> None:
    env = BaseballKC01aEnv()
    print("=== constrained geometry search (same-direction, min displacement, pre-filtered) ===")
    geometry = constrained_geometry_search(env)
    env.close()
    for tt, g in geometry.items():
        print(f"  torso={tt}: dist={g['dist']:.4f} swing={g['swing_target']:.4f} reachable={g['reachable_geometrically']} pre_filter_valid={g['pre_filter_valid']} reasons={g['pre_filter_reasons']}")

    feasible = {tt: g for tt, g in geometry.items() if g["reachable_geometrically"] and g["pre_filter_valid"]}
    print(f"\nfeasible AND pre-filter-valid: {list(feasible.keys())}")
    if not feasible:
        raise RuntimeError("no candidate is both geometrically reachable and passes the pre-filter")

    print("\n=== episode search over feasible candidates ===")
    results = []
    for tt, g in feasible.items():
        for ct in [0.15, 0.20, 0.25, 0.30, 0.36]:
            for hf in [0.15, 0.3, 0.5, 0.7]:
                r = run_episode(tt, g["swing_target"], ct, hf)
                results.append(r)

    valid = [r for r in results if r["scoring_valid"]]
    print(f"total={len(results)} valid={len(valid)}")

    print("\n=== checking active-braking settle for valid candidates (best-score-first) ===")
    valid.sort(key=lambda r: -r["batting_score"])
    active_brake_candidates = []
    for r in valid[:15]:
        full = run_episode(r["torso_target"], r["swing_target"], r["torso_ct"], r["handoff_fraction"], record_settle=True)
        torso_settle = settles_by_active_braking(full["history"]["torso"], TORSO_RANGE)
        swing_settle = settles_by_active_braking(full["history"]["swing"], SWING_RANGE)
        both_active = torso_settle.get("settles_by_active_braking") and swing_settle.get("settles_by_active_braking")
        print(f"  torso={r['torso_target']} ct={r['torso_ct']} hf={r['handoff_fraction']} score={r['batting_score']:.3f} "
              f"control_lead={r['control_lead_s']} torso_settle_active={torso_settle.get('settles_by_active_braking')} "
              f"swing_settle_active={swing_settle.get('settles_by_active_braking')}")
        if both_active:
            active_brake_candidates.append({**r, "torso_settle": torso_settle, "swing_settle": swing_settle})

    print(f"\nvalid + both axes settle via active braking: {len(active_brake_candidates)}")
    best = active_brake_candidates[0] if active_brake_candidates else None
    if best:
        grip = grip_reachability(best["torso_target"], best["swing_target"], best["torso_ct"], best["handoff_fraction"])
        best["grip"] = grip
        print(f"BEST (active-braking-settle, in-range): {json.dumps(best, indent=2, default=str)}")
    else:
        print("NO candidate found that is valid, scores, AND settles both axes via active braking within this search space.")

    out = {
        "geometry_search": geometry,
        "feasible_torso_targets": list(feasible.keys()),
        "n_total": len(results),
        "n_valid": len(valid),
        "n_valid_and_active_braking_settle": len(active_brake_candidates),
        "top_valid_candidates_checked": [
            {k: v for k, v in c.items() if k != "history"} for c in active_brake_candidates
        ],
        "best": ({k: v for k, v in best.items() if k != "history"} if best else None),
    }
    out_path = OUT_DIR / "KC-01a-torso-lead-handoff-search-v2.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

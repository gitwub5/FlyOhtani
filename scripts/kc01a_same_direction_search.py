"""KC-01a same-direction kinetic-chain condition (docs/design/
KC-01a-DIRECTION-CONTRACT.md): the existing `simultaneous_swing_and_torso`/
`staggered_swing_and_torso` conditions drive torso_yaw NEGATIVE while
bat_hinge (swing) drives POSITIVE -- since both hinges share the same world
Z axis with bat_hinge a descendant of torso_yaw, world bat angular velocity
= torso_yaw_vel + swing_vel, so opposite signs partially CANCEL instead of
adding (docs/design/KC-01a-DIRECTION-CONTRACT.md section 1-2). That sign was
never chosen for a physical reason -- scripts/kc01a_calibrate.py's own
`step1_geometry` only ever swept torso in (-0.2, -0.3, -0.4, -0.5). This
script removes that restriction, searches POSITIVE torso targets (same sign
as swing, a genuine additive kinetic chain), and re-derives everything that
depends on the target-angle sign: swing/tilt target (geometry), grip
reachability, and trigger timing -- not just the torso target's sign.

Preserves scripts/kc01a_calibrate.py and its output untouched (this is an
additive, separate search); the negative-torso conditions stay as-is
(diagnostic record, docs/design/KC-01a-DIRECTION-CONTRACT.md section 3).
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball.courses import COURSES
from envs.baseball_kc01a_env import BaseballKC01aEnv
from envs.fly_visual import FrontLegGripOverlay

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
TARGET = COURSES["mid_mid"].copy()
CONTACT_THRESHOLD = 0.0366 + 0.025
SWING_LIMIT = (-2.0, 2.0)
TILT_LIMIT = (-0.6, 0.6)
TORSO_LIMIT = (-0.6, 0.6)
PREP_TORSO, PREP_SWING, PREP_TILT = 0.0, -1.96, 0.0

# Same-direction candidates only: torso_target > 0, matching swing_dir=+1
# (docs/design/KC-01a-DIRECTION-CONTRACT.md section 4, item 1). The old
# search's negative sweep (-0.2..-0.5) is NOT reproduced here -- that
# restriction is exactly what is being removed.
TORSO_POSITIVE_CANDIDATES = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]


def _clip(v, lim):
    return float(np.clip(v, lim[0], lim[1]))


def bat_closest_distance(env: BaseballKC01aEnv, torso: float, swing: float, tilt: float) -> float:
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


def step_geometry(env) -> dict:
    """Same-direction analogue of kc01a_calibrate.py's step1_geometry
    `shared` search, but torso restricted to the POSITIVE candidates
    above instead of the old script's hardcoded negative sweep."""
    out = {}
    for tt in TORSO_POSITIVE_CANDIDATES:
        d, sw, ti = grid_refine(env, tt, (-2.0, 2.0), (-0.6, 0.6))
        swing_dir = 1.0 if sw > PREP_SWING else -1.0
        out[tt] = {
            "dist": d,
            "swing_target": sw,
            "tilt_target": ti,
            "reachable_geometrically": d <= CONTACT_THRESHOLD,
            "swing_dir": swing_dir,
            "same_direction_as_swing": swing_dir > 0,  # torso_dir is always +1 here by construction
        }
    return out


def run_episode(mode, torso_target, swing_target, torso_ct, swing_ct, record_timeline=False, record_jac=False):
    env = BaseballKC01aEnv(prep_torso=PREP_TORSO, prep_swing=PREP_SWING, prep_tilt=PREP_TILT)
    try:
        controller = TorsoBatController(
            mode, PREP_TORSO, PREP_SWING, PREP_TILT, torso_target, swing_target, torso_ct, swing_ct
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        overlay = FrontLegGripOverlay(env.model) if record_jac else None
        timeline = []
        reach_errors = []
        contact_jac: dict | None = None
        info = {}

        def substep_hook(env_, bat_hit, bat_vel, ball_vel):
            nonlocal contact_jac
            if record_jac and bat_hit and contact_jac is None:
                # Per-joint contribution to the bat contact point's world
                # velocity: mujoco.mj_jac gives jacp (3 x nv), the Jacobian
                # of that world point's velocity w.r.t. every qvel DOF --
                # v_point = jacp @ qvel is linear in qvel, so
                # jacp[:, i] * qvel[i] is EXACTLY joint i's own additive
                # contribution to v_point at this instant (not an
                # approximation -- the standard rigid-body Jacobian
                # decomposition).
                nv = env_.model.nv
                jacp = np.zeros((3, nv))
                jacr = np.zeros((3, nv))
                point = env_.data.geom_xpos[env_.bat_geom_id].copy()
                mujoco.mj_jac(env_.model, env_.data, jacp, jacr, point, env_.bat_body_id)
                qvel = env_.data.qvel.copy()
                v_point = jacp @ qvel
                contrib = {
                    "torso": (jacp[:, 0] * qvel[0]).tolist(),
                    "swing": (jacp[:, 1] * qvel[1]).tolist(),
                    "tilt": (jacp[:, 2] * qvel[2]).tolist(),
                }
                contact_jac = {
                    "point_world": point.tolist(),
                    "v_point_from_jac": v_point.tolist(),
                    "v_point_actual_ball_vel_at_contact": ball_vel.tolist() if ball_vel is not None else None,
                    "per_joint_contribution": contrib,
                    "torso_qvel": float(qvel[0]),
                    "swing_qvel": float(qvel[1]),
                    "tilt_qvel": float(qvel[2]),
                }

        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action, substep_callback=substep_hook if record_jac else None)
            if record_timeline:
                world_bat_angle = float(env.data.qpos[env.torso_qpos_adr] + env.data.qpos[env.swing_qpos_adr])
                world_bat_vel = float(env.data.qvel[env.torso_qvel_adr] + env.data.qvel[env.swing_qvel_adr])
                timeline.append(
                    {
                        "t": float(env.data.time),
                        "torso_angle": float(env.data.qpos[env.torso_qpos_adr]),
                        "torso_vel": float(env.data.qvel[env.torso_qvel_adr]),
                        "swing_angle": float(env.data.qpos[env.swing_qpos_adr]),
                        "swing_vel": float(env.data.qvel[env.swing_qvel_adr]),
                        "world_bat_angle": world_bat_angle,
                        "world_bat_vel": world_bat_vel,
                        "torso_ctrl": float(action[0]),
                        "swing_ctrl": float(action[1]),
                        "phase": info["phase"],
                    }
                )
            if overlay is not None:
                errs = overlay.update(env.model, env.data)
                reach_errors.append({"t": float(env.data.time), **errs})
            if terminated or truncated:
                break
        return info, timeline, reach_errors, contact_jac
    finally:
        env.close()


def trigger_search(torso_target, swing_target) -> dict:
    """torso-leads-swing timing search (docs/design/
    KC-01a-DIRECTION-CONTRACT.md section 4 item 5): torso_ct > swing_ct,
    mode='staggered' (functionally identical to 'simultaneous' in
    controllers/baseball_kc01a.py -- both move both axes; only the
    crossing-time VALUES passed in differ, which is exactly what this
    search is over)."""
    best = None
    for swing_ct in np.arange(0.06, 0.22, 0.004):
        for lead in np.arange(0.0, 0.20, 0.01):
            torso_ct = swing_ct + lead
            info, _, _, _ = run_episode("staggered", torso_target, swing_target, torso_ct, swing_ct)
            if info["scoring_valid"] and (best is None or info["batting_score"] > best[1]):
                best = (swing_ct, lead, info["batting_score"], info["bat_contact_vx"], torso_ct)
    if best is None:
        return {"found": False}
    swing_ct, lead, score, vx, torso_ct = best
    return {
        "found": True,
        "swing_crossing_time_s": swing_ct,
        "torso_lead_s": lead,
        "torso_crossing_time_s": torso_ct,
        "batting_score": score,
        "bat_contact_vx": vx,
    }


def main() -> None:
    env = BaseballKC01aEnv()
    print("=== same-direction geometry search (torso > 0 only) ===")
    geometry = step_geometry(env)
    env.close()
    for tt, r in geometry.items():
        print(f"  torso={tt}: dist={r['dist']:.4f} swing={r['swing_target']:.4f} tilt={r['tilt_target']:.4f} reachable={r['reachable_geometrically']}")

    feasible = {tt: r for tt, r in geometry.items() if r["reachable_geometrically"]}
    if not feasible:
        raise RuntimeError("no same-direction (torso>0) target reaches the ball geometrically -- cannot proceed")

    # Pick a mid-range feasible torso target (not the extreme ends) so both
    # axes contribute meaningfully -- a genuine coordination test, not a
    # near-single-axis degenerate case.
    chosen_torso = sorted(feasible.keys())[len(feasible) // 2]
    chosen = feasible[chosen_torso]
    print(f"\nchosen torso_target={chosen_torso} (swing={chosen['swing_target']:.4f} tilt={chosen['tilt_target']:.4f})")

    print("\n=== trigger-time search (torso leads swing) ===")
    trigger = trigger_search(chosen_torso, chosen["swing_target"])
    print(json.dumps(trigger, indent=2, default=str))

    result = {
        "geometry_search": geometry,
        "chosen_torso_target": chosen_torso,
        "chosen_swing_target": chosen["swing_target"],
        "chosen_tilt_target": chosen["tilt_target"],
        "trigger_search": trigger,
    }

    if trigger.get("found"):
        print("\n=== final run: reachability + timeline + contact-point Jacobian ===")
        info, timeline, reach_errors, contact_jac = run_episode(
            "staggered",
            chosen_torso,
            chosen["swing_target"],
            trigger["torso_crossing_time_s"],
            trigger["swing_crossing_time_s"],
            record_timeline=True,
            record_jac=True,
        )
        max_reach_error = max((max(e["L"], e["R"]) for e in reach_errors), default=0.0)
        result["final_run"] = {
            "end_reason": info["end_reason"],
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
            "exit_speed": info["exit_speed"],
            "bat_contact_vx": info["bat_contact_vx"],
            "max_grip_reach_error_m": max_reach_error,
            "grip_always_reachable": max_reach_error <= 1e-9,
            "contact_point_jacobian": contact_jac,
        }
        timeline_path = OUT_DIR / "KC-01a-timelines" / "same_direction_staggered.json"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        timeline_path.write_text(json.dumps(timeline))
        print(f"  end_reason={info['end_reason']} valid={info['scoring_valid']} score={info['batting_score']} max_reach_error={max_reach_error:.4f}m")
        print(f"  wrote {timeline_path}")
    else:
        print("\nNo valid same-direction trigger timing found in the swept range -- reporting search as a negative result.")

    out_path = OUT_DIR / "KC-01a-same-direction-search.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

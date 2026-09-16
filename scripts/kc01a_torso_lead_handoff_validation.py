"""Full acceptance battery for the best torso_lead_handoff candidate found
by a refinement of scripts/kc01a_torso_lead_handoff_search.py's grid
(torso_target=0.5, torso_ct=0.33, handoff_fraction=0.5, swing_target from
scripts/kc01a_same_direction_search.py's own geometry table for torso=0.5).
This candidate has a genuine ~225ms CONTROL-trigger lead (torso's own
accelerate state starts 225ms before swing's, not a ~10ms fixed offset)
and produced a much larger production-dt score (6.78m) than any prior
KC-01a condition -- exactly the kind of surprising result that MUST be
re-verified with the same skepticism that overturned `staggered`'s earlier
"best score" (docs/records/KC-01a-VALIDATION.md A2), not reported as a
coordination win before that verification.

Runs, on this ONE frozen candidate: dt convergence (A2 methodology,
imported from scripts/kc01a_dt_convergence.py), contact penetration/force/
impulse per dt, settle diagnostics (A3 methodology), and grip reachability
(FrontLegGripOverlay). gear/mass/material/reward are never touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import kc01a_dt_convergence as dtc
import mujoco
import numpy as np
from kc01a_same_direction_acceptance import DetailedContactLog
from kc01a_settle_diagnostics import MIN_CONTINUATION_S, _axis_history_to_settle

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv
from envs.fly_visual import FrontLegGripOverlay

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

CANDIDATE = {
    "controller_mode": "torso_lead_handoff",
    "torso_target": 0.5,
    "swing_target": -1.9640000000000004,
    "torso_ct": 0.33,
    "swing_ct": 999.0,
    "handoff_fraction": 0.5,
}


def _make_controller(cfg: dict) -> TorsoBatController:
    return TorsoBatController(
        cfg["controller_mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"],
        handoff_fraction=cfg["handoff_fraction"],
    )


def run_recording(cfg: dict, dt: float, frame_skip: int):
    env = dtc._make_env_at_dt(dt, frame_skip)
    try:
        controller = _make_controller(cfg)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        log = dtc.ContactLog()
        actions = []
        info = {}
        while True:
            action = controller.act(obs)
            actions.append(action.tolist())
            obs, _, terminated, truncated, info = env.step(action, substep_callback=log)
            if terminated or truncated:
                break
        return info, actions, log
    finally:
        env.close()


def run_replay(actions: list, dt: float, frame_skip: int):
    env = dtc._make_env_at_dt(dt, frame_skip)
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        log = dtc.ContactLog()
        info = {}
        max_steps = max(len(actions) * 4, 200)
        for i in range(max_steps):
            action = actions[i] if i < len(actions) else actions[-1]
            _obs, _, terminated, truncated, info = env.step(np.array(action, dtype=np.float32), substep_callback=log)
            if terminated or truncated:
                break
        return info, log
    finally:
        env.close()


def dt_convergence(cfg: dict) -> dict:
    result = {"independent": {}, "replay": {}}
    base_info, base_actions, base_log = run_recording(cfg, dtc.BASE_DT, dtc.FRAME_SKIP_AT_BASE)
    result["independent"][str(dtc.BASE_DT)] = dtc.summarize(base_info, base_log)
    for dt in dtc.DT_CANDIDATES[1:]:
        scale = round(dtc.BASE_DT / dt)
        frame_skip = dtc.FRAME_SKIP_AT_BASE * scale
        info_i, _, log_i = run_recording(cfg, dt, frame_skip)
        result["independent"][str(dt)] = dtc.summarize(info_i, log_i)
        info_r, log_r = run_replay(base_actions, dt, frame_skip)
        result["replay"][str(dt)] = dtc.summarize(info_r, log_r)
    result["replay"][str(dtc.BASE_DT)] = dtc.summarize(base_info, base_log)
    finest, fine = str(dtc.DT_CANDIDATES[2]), str(dtc.DT_CANDIDATES[1])
    result["acceptance"] = {
        "independent": dtc.check_pair(result["independent"][fine], result["independent"][finest]),
        "replay": dtc.check_pair(result["replay"][fine], result["replay"][finest]),
    }
    result["converged"] = result["acceptance"]["independent"]["all_ok"] and result["acceptance"]["replay"]["all_ok"]
    return result


def contact_detail(cfg: dict, dt: float, frame_skip: int) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    control_dt = env.model.opt.timestep * env.frame_skip
    env.model.opt.timestep = dt
    env.frame_skip = frame_skip
    assert abs(dt * frame_skip - control_dt) < 1e-12
    try:
        controller = _make_controller(cfg)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        log = DetailedContactLog()
        info = {}
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action, substep_callback=log)
            if terminated or truncated:
                break
        return {
            "dt": dt,
            "scoring_valid": info["scoring_valid"],
            "min_dist_m": log.min_dist,
            "min_dist_geoms": log.min_dist_geoms,
            "max_normal_force_n": log.max_normal_force_n,
            "impulse_magnitude_ns": float(np.linalg.norm(log.impulse_ns)),
            "contact_duration_s": (None if log.first_active_t is None else log.last_active_t - log.first_active_t),
        }
    finally:
        env.close()


def settle(cfg: dict) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = _make_controller(cfg)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        history: dict[str, list] = {"torso": [], "swing": []}

        def record():
            history["torso"].append((float(env.data.time), float(env.data.qpos[env.torso_qpos_adr]), float(env.data.qvel[env.torso_qvel_adr]), controller._torso_axis.state))
            history["swing"].append((float(env.data.time), float(env.data.qpos[env.swing_qpos_adr]), float(env.data.qvel[env.swing_qvel_adr]), controller._swing_axis.state))

        info = {}
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            record()
            if terminated or truncated:
                break
        outcome = {"end_reason": info["end_reason"], "scoring_valid": info["scoring_valid"], "batting_score": info["batting_score"]}

        target_end_time = float(env.data.time) + MIN_CONTINUATION_S
        safety_cap_time = float(env.data.time) + 4.0
        control_steps = 0
        while float(env.data.time) < target_end_time and float(env.data.time) < safety_cap_time:
            obs = env._get_obs()
            action = controller.act(obs)
            env.data.ctrl[env.torso_actuator_id] = float(np.clip(action[0], -1.0, 1.0))
            env.data.ctrl[env.swing_actuator_id] = float(np.clip(action[1], -1.0, 1.0))
            env.data.ctrl[env.tilt_actuator_id] = float(np.clip(action[2], -1.0, 1.0))
            for _ in range(env.frame_skip):
                mujoco.mj_step(env.model, env.data)
            mujoco.mj_forward(env.model, env.data)
            record()
            control_steps += 1
            for axis_name in ("torso", "swing"):
                h = history[axis_name]
                for i in range(1, len(h)):
                    if h[i - 1][3] == "accelerate" and h[i][3] == "brake":
                        target_end_time = max(target_end_time, h[i][0] + MIN_CONTINUATION_S)
            if control_steps > 2000:
                break
        settle_result = {axis: _axis_history_to_settle(history[axis]) for axis in ("torso", "swing")}
        return {"outcome": outcome, "settle": settle_result}
    finally:
        env.close()


def grip_reachability(cfg: dict) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = _make_controller(cfg)
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
    print(f"Candidate: {CANDIDATE}")
    result: dict = {"config": CANDIDATE}

    print("\n=== dt convergence ===")
    dtres = dt_convergence(CANDIDATE)
    result["dt_convergence"] = dtres
    for dt in dtc.DT_CANDIDATES:
        s = dtres["independent"][str(dt)]
        print(f"  independent dt={dt}: valid={s['scoring_valid']} score={s['batting_score']}")
    print(f"  CONVERGED: {dtres['converged']}")

    print("\n=== contact detail per dt ===")
    cdet = {}
    for dt, fs in ((0.00025, 20), (0.000125, 40), (0.0000625, 80)):
        r = contact_detail(CANDIDATE, dt, fs)
        cdet[str(dt)] = r
        print(f"  dt={dt}: min_dist={r['min_dist_m']:.5f}m geoms={r['min_dist_geoms']} force={r['max_normal_force_n']:.1f}N impulse={r['impulse_magnitude_ns']:.4f}")
    result["contact_detail"] = cdet

    print("\n=== settle ===")
    s = settle(CANDIDATE)
    result["settle"] = s
    print(json.dumps(s["settle"], indent=2, default=str))

    print("\n=== grip reachability ===")
    g = grip_reachability(CANDIDATE)
    result["grip"] = g
    print(g)

    out_path = OUT_DIR / "KC-01a-torso-lead-handoff-validation.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

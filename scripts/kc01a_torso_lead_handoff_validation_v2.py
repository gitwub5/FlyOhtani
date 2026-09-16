"""Full acceptance battery for the CORRECTED torso_lead_handoff candidate
(docs/design/KC-01a-DIRECTION-CONTRACT.md section 8), found by
scripts/kc01a_torso_lead_handoff_search_v2.py's direction/displacement/
range pre-filter: torso_target=0.25, swing_target=-1.644 (swing
displacement +0.316rad, SAME direction as torso, both follow-through
targets inside their own joint ranges), torso_ct=0.16, handoff_fraction=0.1.

scripts/kc01a_torso_lead_handoff_validation.py's OLDER candidate
(torso_target=0.5) is preserved unchanged as a labeled reference/
diagnostic result -- it is invalid (opposite-signed torso/swing commands,
both follow-through targets out of range) and is NOT superseded in place,
per the instruction to keep it as a reference rather than delete it.

Adds, beyond the older script's battery:
- validate_same_direction_candidate() run explicitly and asserted True
  (this candidate must actually pass the pre-filter the old one failed).
- Contact penetration is reported but NEVER described as "passed" --
  the ~5cm penetration is the same order of magnitude as every other
  KC-01a condition and remains an unresolved, unvalidated-against-reality
  property of this contact model (docs/records/KC-01a-VALIDATION.md A9).
- Genuine-motion classification: distinguishes a brief reaction blip from
  sustained, actuator-driven motion using a DURATION+DISPLACEMENT
  criterion (does the SIGNED progress in the intended direction keep
  growing for a sustained window), not a single-instant velocity
  threshold -- reported alongside (not instead of) the raw threshold
  onset and the controller's own trigger-flag times.
- Full handoff-instant report: torso's own angular displacement/velocity
  at the moment of handoff, swing's own (torso-relative) angle/velocity at
  that instant, and the subsequent swing acceleration + world bat
  velocity (torso_vel+swing_vel) trajectory after handoff.
"""
from __future__ import annotations

import json
from pathlib import Path

import kc01a_dt_convergence as dtc
import mujoco
import numpy as np
from kc01a_same_direction_acceptance import DetailedContactLog
from kc01a_settle_diagnostics import MIN_CONTINUATION_S, _axis_history_to_settle

from controllers.baseball_kc01a import (
    SWING_RANGE,
    TORSO_RANGE,
    TorsoBatController,
    validate_same_direction_candidate,
)
from envs.baseball_kc01a_env import BaseballKC01aEnv
from envs.fly_visual import FrontLegGripOverlay

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

CANDIDATE = {
    "controller_mode": "torso_lead_handoff",
    "torso_target": 0.25,
    "swing_target": -1.644,
    "torso_ct": 0.16,
    "swing_ct": 999.0,
    "handoff_fraction": 0.1,
}

SUSTAINED_WINDOW_S = 0.02  # 4 control steps at 5ms
SUSTAINED_DISPLACEMENT_RAD = 0.03


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
        max_abs_torso = max(abs(h[1]) for h in history["torso"])
        max_abs_swing = max(abs(h[1]) for h in history["swing"])
        return {
            "outcome": outcome,
            "settle": settle_result,
            "max_abs_torso_angle_rad": max_abs_torso,
            "torso_distance_from_own_limit_rad": TORSO_RANGE[1] - max_abs_torso,
            "max_abs_swing_angle_rad": max_abs_swing,
            "swing_distance_from_own_limit_rad": SWING_RANGE[1] - max_abs_swing,
        }
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


def _sustained_onset(times, angles, prep, direction, window_s, min_disp) -> float | None:
    """First index i such that the SIGNED progress (angle(t)-prep)*direction
    keeps growing (never drops more than a tiny numerical tolerance below
    its running max) for the next `window_s` and exceeds `min_disp` by the
    end of that window -- a sustained-displacement definition of "genuine
    motion" that a brief reaction blip (which reverses within a step or
    two) does not satisfy."""
    n = len(times)
    for i in range(n):
        t0 = times[i]
        j = i
        running_max = (angles[i] - prep) * direction
        ok = True
        while j + 1 < n and times[j + 1] <= t0 + window_s:
            j += 1
            prog = (angles[j] - prep) * direction
            if prog < running_max - 1e-6:
                ok = False
                break
            running_max = max(running_max, prog)
        if ok and times[j] >= t0 + window_s * 0.8 and running_max >= min_disp:
            return t0
    return None


def handoff_detail_and_world_bat_velocity(cfg: dict) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = _make_controller(cfg)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        torso_dir = 1.0 if cfg["torso_target"] > 0.0 else -1.0
        swing_dir = 1.0 if cfg["swing_target"] > -1.96 else -1.0

        rows = []
        torso_trig_t = swing_trig_t = None
        torso_raw_onset_t = swing_raw_onset_t = None
        info = {}
        while True:
            t = float(env.data.time)
            torso_a = float(env.data.qpos[env.torso_qpos_adr])
            torso_v = float(env.data.qvel[env.torso_qvel_adr])
            swing_a = float(env.data.qpos[env.swing_qpos_adr])
            swing_v = float(env.data.qvel[env.swing_qvel_adr])
            if torso_trig_t is None and controller._torso_triggered:
                torso_trig_t = t
            if swing_trig_t is None and controller._swing_triggered:
                swing_trig_t = t
            if torso_raw_onset_t is None and abs(torso_v) > 0.05:
                torso_raw_onset_t = t
            if swing_raw_onset_t is None and abs(swing_v) > 0.05:
                swing_raw_onset_t = t
            rows.append({"t": t, "torso_angle": torso_a, "torso_vel": torso_v, "swing_angle": swing_a, "swing_vel": swing_v, "world_bat_vel": torso_v + swing_v})
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break

        times = [r["t"] for r in rows]
        torso_angles = [r["torso_angle"] for r in rows]
        swing_angles = [r["swing_angle"] for r in rows]
        torso_sustained_t = _sustained_onset(times, torso_angles, 0.0, torso_dir, SUSTAINED_WINDOW_S, SUSTAINED_DISPLACEMENT_RAD)
        swing_sustained_t = _sustained_onset(times, swing_angles, -1.96, swing_dir, SUSTAINED_WINDOW_S, SUSTAINED_DISPLACEMENT_RAD)

        handoff_row = min(rows, key=lambda r: abs(r["t"] - swing_trig_t)) if swing_trig_t is not None else None
        post_handoff = [r for r in rows if swing_trig_t is not None and r["t"] >= swing_trig_t]
        # World bat velocity trajectory for 100ms after handoff (or to contact, whichever first).
        contact_t = info["first_contact_time_s"]
        post_handoff_to_contact = [r for r in post_handoff if contact_t is None or r["t"] <= contact_t]

        return {
            "torso_control_trigger_t": torso_trig_t,
            "swing_control_trigger_t": swing_trig_t,
            "control_lead_s": (None if (torso_trig_t is None or swing_trig_t is None) else swing_trig_t - torso_trig_t),
            "torso_raw_qvel_onset_t (contamination-prone, reported for reference only)": torso_raw_onset_t,
            "swing_raw_qvel_onset_t (contamination-prone, reported for reference only)": swing_raw_onset_t,
            "torso_sustained_motion_onset_t": torso_sustained_t,
            "swing_sustained_motion_onset_t": swing_sustained_t,
            "sustained_criterion": f"signed progress non-decreasing for {SUSTAINED_WINDOW_S}s and >= {SUSTAINED_DISPLACEMENT_RAD}rad by the end of that window",
            "at_handoff_instant": handoff_row,
            "first_contact_time_s": contact_t,
            "world_bat_velocity_trajectory_post_handoff_to_contact": post_handoff_to_contact,
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
            "epistemic_caveat": (
                "world_bat_vel = torso_vel + swing_vel is a kinematic identity (both hinges share the "
                "same world Z axis, docs/design/KC-01a-DIRECTION-CONTRACT.md section 1) -- it shows how "
                "each axis's angular velocity adds to the bat's own world angular velocity at each instant, "
                "NOT that energy or momentum flowed from one axis to the other."
            ),
        }
    finally:
        env.close()


def main() -> None:
    print(f"Candidate: {CANDIDATE}")
    valid, reasons = validate_same_direction_candidate(0.0, -1.96, CANDIDATE["torso_target"], CANDIDATE["swing_target"])
    print(f"pre-filter valid: {valid} reasons={reasons}")
    assert valid, "this candidate is supposed to pass the pre-filter -- if not, do not proceed"

    result: dict = {"config": CANDIDATE, "pre_filter": {"valid": valid, "reasons": reasons}}

    print("\n=== dt convergence ===")
    dtres = dt_convergence(CANDIDATE)
    result["dt_convergence"] = dtres
    for dt in dtc.DT_CANDIDATES:
        s = dtres["independent"][str(dt)]
        print(f"  independent dt={dt}: valid={s['scoring_valid']} score={s['batting_score']}")
    print(f"  CONVERGED: {dtres['converged']}")

    print("\n=== contact detail per dt (NOT a pass/fail -- penetration remains unresolved, see docs) ===")
    cdet = {}
    for dt, fs in ((0.00025, 20), (0.000125, 40), (0.0000625, 80)):
        r = contact_detail(CANDIDATE, dt, fs)
        cdet[str(dt)] = r
        print(f"  dt={dt}: min_dist={r['min_dist_m']:.5f}m geoms={r['min_dist_geoms']} force={r['max_normal_force_n']:.1f}N impulse={r['impulse_magnitude_ns']:.4f}")
    result["contact_detail"] = cdet
    result["contact_penetration_status"] = "UNRESOLVED -- numerically dt-stable but not validated as physically realistic (docs/records/KC-01a-VALIDATION.md A9); not reported as a passed check"

    print("\n=== settle (with distance-from-own-joint-limit, to check active-braking vs hard-stop) ===")
    s = settle(CANDIDATE)
    result["settle"] = s
    print(json.dumps({k: v for k, v in s.items() if k != "outcome"}, indent=2, default=str))

    print("\n=== grip reachability ===")
    g = grip_reachability(CANDIDATE)
    result["grip"] = g
    print(g)

    print("\n=== handoff detail + genuine-motion classification + world bat velocity ===")
    h = handoff_detail_and_world_bat_velocity(CANDIDATE)
    result["handoff_detail"] = h
    print(f"  control_lead_s={h['control_lead_s']}")
    print(f"  torso_sustained_motion_onset_t={h['torso_sustained_motion_onset_t']}  swing_sustained_motion_onset_t={h['swing_sustained_motion_onset_t']}")
    print(f"  at handoff instant: {h['at_handoff_instant']}")

    out_path = OUT_DIR / "KC-01a-torso-lead-handoff-validation-v2.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

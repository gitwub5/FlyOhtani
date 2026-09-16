"""KC-01a torso-lead mechanism verification (user follow-up): does
`same_direction_staggered` actually show torso leading the arm in a
physically meaningful way, or only in COMMAND onset (torso_ct=0.122s vs
swing_ct=0.112s, a fixed 10ms offset)? The user watched the video and it
looks like the bat moves first with torso trailing -- this script checks
that against the actual simulation data rather than trusting the command
offset or the earlier single-instant (at-contact) Jacobian decomposition.

Four things, all from ONE recorded run (same trajectory, no re-simulation
needed for consistency):

1. ACTUAL motion onset time per axis (first control step |qvel| exceeds a
   threshold), separately from the COMMAND trigger time (when the
   controller's own _torso_triggered/_swing_triggered flip True) -- these
   can differ a lot when one axis's max angular acceleration (torso:
   11.41 rad/s^2) is ~12x smaller than the other's (swing: 134.4 rad/s^2,
   controllers/baseball_kc01a.py's own _SWING_A_MAX/_TORSO_A_MAX).
2. Contact-point velocity contribution from torso vs swing vs tilt, via
   mujoco.mj_jac, computed at EVERY control step during the
   accelerate+brake window (not just the single contact instant like the
   earlier scripts/kc01a_same_direction_search.py check) -- the bat_geom's
   own moving xpos is used as "the point" at each instant (a fixed
   reference point on the bat itself, not a fixed world point).
3. Comparison against the arm_swing_with_torso_hold baseline: the torso
   actuator's own work/peak-power there is NOT zero even though torso is
   "held" at a fixed target (docs/records/KC-01a-VALIDATION.md A1 already
   noted this) -- this script measures that hold-work explicitly and
   compares it to same_direction_staggered's torso work, to see whether
   actively swinging the torso costs meaningfully more than merely
   resisting reaction forces while holding still.
4. An explicit written caveat (not just a code comment): velocity-Jacobian
   decomposition at an instant tells you each joint's INSTANTANEOUS
   contribution to a point's velocity -- it is NOT proof of how kinetic
   energy or momentum was transferred between the axes over time (that
   would require an angular-momentum/energy-flow analysis this script does
   not attempt). The report explicitly says so rather than implying more
   than the number supports.
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
SEARCH_RESULT_PATH = OUT_DIR / "KC-01a-same-direction-search.json"

ONSET_QVEL_THRESHOLD = 0.05  # rad/s -- pre-registered before reading results


def _load_config() -> dict:
    search = json.loads(SEARCH_RESULT_PATH.read_text())
    trig = search["trigger_search"]
    return {
        "controller_mode": "staggered",
        "torso_target": search["chosen_torso_target"],
        "swing_target": search["chosen_swing_target"],
        "torso_ct": trig["torso_crossing_time_s"],
        "swing_ct": trig["swing_crossing_time_s"],
    }


def run_full_trace(cfg: dict, prep_torso: float = 0.0, prep_swing: float = -1.96) -> dict:
    env = BaseballKC01aEnv(prep_torso=prep_torso, prep_swing=prep_swing, prep_tilt=0.0)
    try:
        controller = TorsoBatController(
            cfg["controller_mode"], prep_torso, prep_swing, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        rows = []
        torso_command_trigger_t = None
        swing_command_trigger_t = None
        torso_motion_onset_t = None
        swing_motion_onset_t = None
        info = {}
        while True:
            t = float(env.data.time)
            if torso_command_trigger_t is None and controller._torso_triggered:
                torso_command_trigger_t = t
            if swing_command_trigger_t is None and controller._swing_triggered:
                swing_command_trigger_t = t
            torso_v = float(env.data.qvel[env.torso_qvel_adr])
            swing_v = float(env.data.qvel[env.swing_qvel_adr])
            if torso_motion_onset_t is None and abs(torso_v) > ONSET_QVEL_THRESHOLD:
                torso_motion_onset_t = t
            if swing_motion_onset_t is None and abs(swing_v) > ONSET_QVEL_THRESHOLD:
                swing_motion_onset_t = t

            nv = env.model.nv
            jacp = np.zeros((3, nv))
            jacr = np.zeros((3, nv))
            point = env.data.geom_xpos[env.bat_geom_id].copy()
            mujoco.mj_jac(env.model, env.data, jacp, jacr, point, env.bat_body_id)
            qvel_full = env.data.qvel.copy()
            contrib_torso = jacp[:, 0] * qvel_full[0]
            contrib_swing = jacp[:, 1] * qvel_full[1]
            contrib_tilt = jacp[:, 2] * qvel_full[2]

            rows.append(
                {
                    "t": t,
                    "torso_angle": float(env.data.qpos[env.torso_qpos_adr]),
                    "torso_vel": torso_v,
                    "swing_angle": float(env.data.qpos[env.swing_qpos_adr]),
                    "swing_vel": swing_v,
                    "torso_state": controller._torso_axis.state,
                    "swing_state": controller._swing_axis.state,
                    "bat_point_world": point.tolist(),
                    "contrib_torso_x": float(contrib_torso[0]),
                    "contrib_swing_x": float(contrib_swing[0]),
                    "contrib_tilt_x": float(contrib_tilt[0]),
                    "contrib_torso_mag": float(np.linalg.norm(contrib_torso)),
                    "contrib_swing_mag": float(np.linalg.norm(contrib_swing)),
                    "torso_qfrc_actuator": float(env.data.qfrc_actuator[0]),
                }
            )
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break

        return {
            "rows": rows,
            "torso_command_trigger_t": torso_command_trigger_t,
            "swing_command_trigger_t": swing_command_trigger_t,
            "torso_motion_onset_t": torso_motion_onset_t,
            "swing_motion_onset_t": swing_motion_onset_t,
            "first_contact_time_s": info["first_contact_time_s"],
            "onset_qvel_threshold": ONSET_QVEL_THRESHOLD,
        }
    finally:
        env.close()


def torso_angle_and_qvel_before_swing_onset(trace: dict) -> dict:
    swing_onset = trace["swing_motion_onset_t"]
    if swing_onset is None:
        return {"applicable": False}
    before = [r for r in trace["rows"] if r["t"] < swing_onset]
    if not before:
        return {"applicable": True, "torso_angle_at_swing_onset": 0.0, "torso_vel_at_swing_onset": 0.0}
    last = before[-1]
    return {
        "applicable": True,
        "torso_angle_at_swing_onset": last["torso_angle"],
        "torso_vel_at_swing_onset": last["torso_vel"],
        "torso_lead_time_s": swing_onset - trace["torso_motion_onset_t"] if trace["torso_motion_onset_t"] is not None else None,
    }


def run_holdmotor_baseline() -> dict:
    """arm_swing_with_torso_hold: torso target=0 (held via the
    controller's own P-hold, gain=50 -- NOT env.set_held_pose()'s hard
    lock, docs/records/KC-01a-VALIDATION.md A1), swing does all the work.
    Measures the torso actuator's own work/peak power over the whole
    episode -- this is the "cost of merely holding" baseline."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = TorsoBatController("arm_only", 0.0, -1.96, 0.0, 0.0, -1.298, 999.0, 0.09425316355759385)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        w_torso_hold = 0.0
        peak_abs_torso_power = 0.0
        info = {}
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            p = float(env.data.qfrc_actuator[0] * env.data.qvel[env.torso_qvel_adr])
            w_torso_hold += p * env.model.opt.timestep * env.frame_skip
            peak_abs_torso_power = max(peak_abs_torso_power, abs(p))
            if terminated or truncated:
                break
        return {
            "w_torso_hold_net_j": w_torso_hold,
            "peak_abs_torso_power_w": peak_abs_torso_power,
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
            "note": "torso target=0 the whole episode (arm_only baseline); this is the actuator work spent RESISTING reaction forces while nominally 'not moving', not zero as a naive reading of 'held' would suggest.",
        }
    finally:
        env.close()


def main() -> None:
    cfg = _load_config()
    print(f"config: {cfg}")

    print("\n=== full trace: command trigger vs actual motion onset ===")
    trace = run_full_trace(cfg)
    print(f"  torso command trigger t={trace['torso_command_trigger_t']}")
    print(f"  swing command trigger t={trace['swing_command_trigger_t']}")
    print(f"  torso motion onset (|qvel|>{ONSET_QVEL_THRESHOLD}) t={trace['torso_motion_onset_t']}")
    print(f"  swing motion onset (|qvel|>{ONSET_QVEL_THRESHOLD}) t={trace['swing_motion_onset_t']}")
    print(f"  command lead (torso ahead of swing): {trace['swing_command_trigger_t'] - trace['torso_command_trigger_t']:.4f}s")
    if trace["torso_motion_onset_t"] is not None and trace["swing_motion_onset_t"] is not None:
        print(f"  ACTUAL motion lead (torso ahead of swing): {trace['swing_motion_onset_t'] - trace['torso_motion_onset_t']:.4f}s")

    pre = torso_angle_and_qvel_before_swing_onset(trace)
    print(f"  torso state at swing's own motion onset: {pre}")

    print("\n=== torso vs swing contribution to bat-point x-velocity, whole accel window ===")
    accel_rows = [r for r in trace["rows"] if r["torso_state"] in ("accelerate", "brake") or r["swing_state"] in ("accelerate", "brake")]
    if accel_rows:
        torso_share = [abs(r["contrib_torso_x"]) / (abs(r["contrib_torso_x"]) + abs(r["contrib_swing_x"]) + 1e-9) for r in accel_rows]
        print(f"  n={len(accel_rows)} control steps in accel/brake window")
        print(f"  torso's share of |contrib_x| -- min={min(torso_share):.3f} max={max(torso_share):.3f} mean={float(np.mean(torso_share)):.3f}")

    print("\n=== torso-hold baseline (arm_swing_with_torso_hold) ===")
    hold = run_holdmotor_baseline()
    print(json.dumps(hold, indent=2, default=str))

    result = {
        "config": cfg,
        "trigger_vs_onset": {
            "torso_command_trigger_t": trace["torso_command_trigger_t"],
            "swing_command_trigger_t": trace["swing_command_trigger_t"],
            "torso_motion_onset_t": trace["torso_motion_onset_t"],
            "swing_motion_onset_t": trace["swing_motion_onset_t"],
            "onset_qvel_threshold": ONSET_QVEL_THRESHOLD,
            "torso_state_at_swing_onset": pre,
        },
        "contribution_accel_window": {
            "n_rows": len(accel_rows),
            "torso_share_min": float(min(torso_share)) if accel_rows else None,
            "torso_share_max": float(max(torso_share)) if accel_rows else None,
            "torso_share_mean": float(np.mean(torso_share)) if accel_rows else None,
        },
        "holdmotor_baseline": hold,
        "epistemic_caveat": (
            "contrib_torso_x/contrib_swing_x is an INSTANTANEOUS velocity-Jacobian "
            "decomposition (v_point = sum_i jacp[:,i]*qvel[i]) at each control step -- "
            "it shows which joint's angular velocity is contributing how much to the "
            "bat point's CURRENT velocity at that instant. It is NOT a measurement of "
            "energy or momentum transferred FROM one axis TO the other over time; no "
            "such flow analysis was performed, and this ratio should not be read as one."
        ),
    }
    (OUT_DIR / "KC-01a-torso-lead-timeline.json").write_text(json.dumps(trace["rows"]))
    out_path = OUT_DIR / "KC-01a-torso-lead-analysis.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

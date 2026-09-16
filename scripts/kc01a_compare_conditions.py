"""KC-01a step 2-4 (docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 6,
mid_mid only): runs the 4 coordination conditions on identical hardware,
records full outcome/energy/timing metrics and per-step timelines, then
re-runs each condition's central pitch with a +/-5ms trigger offset and
(for one representative condition) a halved physics timestep, to check
timing/dt sensitivity honestly rather than assuming robustness.

Writes:
- docs/records/evidence/KC-01a-comparison.json (full data)
- docs/records/evidence/KC-01a-timelines/<condition>.json (per-step angle/
  velocity/ctrl timelines, for plotting)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
TIMELINE_DIR = OUT_DIR / "KC-01a-timelines"

CONDITIONS = {
    "arm_only": {"torso_target": 0.0, "swing_target": -1.298, "torso_ct": 999.0, "swing_ct": 0.09425316355759385},
    "torso_only": {"torso_target": 0.496, "swing_target": -1.96, "torso_ct": 0.360, "swing_ct": 999.0},
    "simultaneous": {"torso_target": -0.4, "swing_target": -0.726, "torso_ct": 0.096, "swing_ct": 0.096},
    "staggered": {"torso_target": -0.4, "swing_target": -0.726, "torso_ct": 0.242, "swing_ct": 0.122},
}


def run(mode: str, cfg: dict, torso_ct_override=None, swing_ct_override=None, half_dt=False, record_timeline=False):
    """The non-participating axis in arm_only/torso_only is held by the
    CONTROLLER's own hold-gain P-control (never triggered, crossing_time=
    999.0), not env.set_held_pose()'s hard qpos/qvel override. This is a
    deliberate finding, not an oversight (docs/design/
    KC-01a-TORSO-BAT-COORDINATION.md section 5): the hard lock resets
    qvel=0 every substep, which changes the ball-bat collision's effective
    dynamics enough to flip arm_only from a valid hit to no valid hit
    anywhere in a wide trigger-time search -- given this contact model's
    already-documented extreme timing sensitivity (B1's own ±5ms finding),
    that is plausible, not a KC-01a-specific bug, but it means "locked"
    here means "actively held at zero commanded motion", not "welded"."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    if half_dt:
        env.model.opt.timestep = env.model.opt.timestep / 2.0
        env.frame_skip = env.frame_skip * 2  # control_dt unchanged
    try:
        torso_ct = torso_ct_override if torso_ct_override is not None else cfg["torso_ct"]
        swing_ct = swing_ct_override if swing_ct_override is not None else cfg["swing_ct"]
        controller = TorsoBatController(
            mode, 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], torso_ct, swing_ct
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        timeline = []
        info = {}
        while True:
            action = controller.act(obs)
            obs, _reward, terminated, truncated, info = env.step(action)
            if record_timeline:
                timeline.append(
                    {
                        "t": float(env.data.time),
                        "torso_angle": float(env.data.qpos[env.torso_qpos_adr]),
                        "torso_vel": float(env.data.qvel[env.torso_qvel_adr]),
                        "swing_angle": float(env.data.qpos[env.swing_qpos_adr]),
                        "swing_vel": float(env.data.qvel[env.swing_qvel_adr]),
                        "tilt_angle": float(env.data.qpos[env.tilt_qpos_adr]),
                        "tilt_vel": float(env.data.qvel[env.tilt_qvel_adr]),
                        "torso_ctrl": float(action[0]),
                        "swing_ctrl": float(action[1]),
                        "tilt_ctrl": float(action[2]),
                        "phase": info["phase"],
                        "contact_occurred": bool(info["contact_occurred"]),
                    }
                )
            if terminated or truncated:
                break
        return info, timeline
    finally:
        env.close()


def summarize(info: dict) -> dict:
    total_pos_work = sum(info["joint_positive_work_j"].values())
    total_neg_work = sum(info["joint_negative_work_j"].values())
    return {
        "end_reason": info["end_reason"],
        "status": info["status"],
        "contact_occurred": info["contact_occurred"],
        "bat_contact_vx": info["bat_contact_vx"],
        "bat_contact_velocity": info["bat_contact_velocity"],
        "recontact_count": info["recontact_count"],
        "prolonged_contact": info["prolonged_contact"],
        "exit_speed": info["exit_speed"],
        "launch_angle_deg": None if info["launch_angle_rad"] is None else float(np.degrees(info["launch_angle_rad"])),
        "forward_flight_success": info["forward_flight_success"],
        "scoring_valid": info["scoring_valid"],
        "carry_distance_m": info["carry_distance_m"],
        "batting_score": info["batting_score"],
        "joint_positive_work_j": info["joint_positive_work_j"],
        "joint_negative_work_j": info["joint_negative_work_j"],
        "total_positive_work_j": total_pos_work,
        "total_negative_work_j": total_neg_work,
        "net_actuator_work_j": total_pos_work + total_neg_work,
        "joint_peak_abs_power_w": info["joint_peak_abs_power_w"],
        "joint_peak_abs_torque_nm": info["joint_peak_abs_torque_nm"],
        "real_duration_s": info["step"],
    }


def main() -> None:
    TIMELINE_DIR.mkdir(parents=True, exist_ok=True)
    result = {"conditions": {}, "timing_sensitivity": {}, "dt_sensitivity": {}}

    print("=== main comparison ===")
    for mode, cfg in CONDITIONS.items():
        info, timeline = run(mode, cfg, record_timeline=True)
        summary = summarize(info)
        result["conditions"][mode] = summary
        (TIMELINE_DIR / f"{mode}.json").write_text(json.dumps(timeline))
        print(mode, "->", {k: summary[k] for k in ("scoring_valid", "batting_score", "exit_speed", "launch_angle_deg", "net_actuator_work_j")})

    print("\n=== timing sensitivity (+/-5ms on the trigger(s) that move) ===")
    for mode, cfg in CONDITIONS.items():
        entries = {}
        for label, dt_off in (("minus_5ms", -0.005), ("baseline", 0.0), ("plus_5ms", 0.005)):
            # Offsetting the non-participating axis's own 999.0s crossing
            # time by +-5ms is harmless (it still never triggers within a
            # <1s pitch), so the offset is applied uniformly rather than
            # branching on which axis moves.
            torso_ov = cfg["torso_ct"] + dt_off
            swing_ov = cfg["swing_ct"] + dt_off
            info, _ = run(mode, cfg, torso_ct_override=torso_ov, swing_ct_override=swing_ov)
            entries[label] = summarize(info)
        result["timing_sensitivity"][mode] = entries
        print(mode, {k: (entries[k]["scoring_valid"], entries[k]["batting_score"]) for k in entries})

    print("\n=== dt sensitivity (staggered and simultaneous, physics_dt halved) ===")
    for mode in ("simultaneous", "staggered"):
        cfg = CONDITIONS[mode]
        info_full, _ = run(mode, cfg)
        info_half, _ = run(mode, cfg, half_dt=True)
        result["dt_sensitivity"][mode] = {
            "physics_dt_0.00025s": summarize(info_full),
            "physics_dt_0.000125s": summarize(info_half),
        }
        print(mode, "full_dt score=", info_full.get("batting_score"), "half_dt score=", info_half.get("batting_score"))

    out_path = OUT_DIR / "KC-01a-comparison.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

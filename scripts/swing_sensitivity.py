"""I-07c-swing sensitivity check (docs/design/BATTING-QUALITY-AND-SWING.md
section 2 item 5): for the chosen mid_mid candidate (prep_swing=-1.96,
swing_crossing_time=0.09425316355759385), replay at

  (a) trigger +/- 1 control step (control_dt=0.005s), and
  (b) physics_dt halved with the SAME recorded control schedule (same
      per-control-step ctrl sequence, just resolved at twice the substep
      count so each 0.005s control interval is unchanged),

and report contact/landing/score sensitivity, hiding no boundary flips.
"""

from __future__ import annotations

import json

import numpy as np

from controllers.baseball_b1 import CROSSING_TIME_S, OracleAimController
from envs.baseball_b1_env import BaseballB1Env

CHOSEN_PREP_SWING = -1.96
CHOSEN_CROSSING_TIME = 0.09425316355759385
CONTROL_DT = 0.005


def run(prep_swing: float, crossing_time: float, half_dt: bool = False, replay_ctrl: list | None = None) -> dict:
    env = BaseballB1Env(prep_swing=prep_swing, prep_tilt=0.0)
    if half_dt:
        env.model.opt.timestep = 0.000125
        env.frame_skip = 40  # control_dt stays 0.005s: 0.000125*40 == 0.00025*20
    original = CROSSING_TIME_S["mid_mid"]
    CROSSING_TIME_S["mid_mid"] = (crossing_time, original[1])
    try:
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        recorded_ctrl = []
        if replay_ctrl is None:
            controller = OracleAimController("mid_mid", prep_swing=env.prep_swing, prep_tilt=env.prep_tilt)
            controller.reset()
            info = {}
            i = 0
            while True:
                action = controller.act(obs)
                recorded_ctrl.append(action.tolist())
                obs, _, terminated, truncated, info = env.step(action)
                i += 1
                if terminated or truncated:
                    break
        else:
            info = {}
            for action in replay_ctrl:
                obs, _, terminated, truncated, info = env.step(np.array(action, dtype=np.float32))
                if terminated or truncated:
                    break
        return {
            "prep_swing": prep_swing,
            "crossing_time": crossing_time,
            "half_dt": half_dt,
            "end_reason": info["end_reason"],
            "forward_flight_success": info["forward_flight_success"],
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
            "carry_distance_m": info["carry_distance_m"],
            "exit_velocity_xyz": info["exit_velocity_xyz"],
            "bat_contact_vx": info["bat_contact_vx"],
            "recontact_count": info["recontact_count"],
            "prolonged_contact": info["prolonged_contact"],
            "first_landing_xyz": info["first_landing_xyz"],
        }, recorded_ctrl
    finally:
        CROSSING_TIME_S["mid_mid"] = original
        env.close()


def main() -> None:
    results = {}

    baseline, baseline_ctrl = run(CHOSEN_PREP_SWING, CHOSEN_CROSSING_TIME)
    results["chosen"] = baseline

    for label, dt_offset in (("trigger_minus_1_step", -CONTROL_DT), ("trigger_plus_1_step", CONTROL_DT)):
        res, _ = run(CHOSEN_PREP_SWING, CHOSEN_CROSSING_TIME + dt_offset)
        results[label] = res

    half_dt_res, _ = run(CHOSEN_PREP_SWING, CHOSEN_CROSSING_TIME, half_dt=True, replay_ctrl=baseline_ctrl)
    results["half_physics_dt_same_schedule"] = half_dt_res

    print(json.dumps(results, indent=2))
    from pathlib import Path

    out = Path("runs/env002-b1-swing-experiment/sensitivity.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()

"""I-07c-swing (docs/design/BATTING-QUALITY-AND-SWING.md section 2):
measure the current mid_mid swing, then search prep angle / trigger timing
candidates within the FIXED bat_hinge joint range [-2.0, 2.0] (gear/mass/
inertia/material/dt/pitch all held fixed -- no restitution/torque increase,
no force added to the ball, no teleporting).

Physics basis for why prep angle (windup distance) is the only free lever
that can raise contact-point speed without touching gear/dt: the swing
axis's "accelerate" phase (controllers/baseball_b1.py::_SwingAxis) applies
constant max torque the ENTIRE distance from the trigger to accel_target
crossing/contact -- there is no premature target-arrival braking during
this phase (braking only starts once the target is crossed or contact
happens). Under that already-optimal constant-acceleration profile, contact
speed is analytically v = sqrt(2*a_max*delta_theta) where delta_theta is
the prep-to-contact angular distance. a_max is measured/fixed at
134.4 rad/s^2 (gear=30). ALIGNMENT["mid_mid"] (the contact angle) is a
direction-independent geometric fact (envs/baseball_b1_env.py's own
comment) and is NOT changed here -- only how far back of it the bat starts.

The trigger crossing_time is a DEPENDENT quantity, not an independent knob:
for a given delta_theta, the analytic no-braking time-to-cross is
t = sqrt(2*delta_theta/a_max); CROSSING_TIME_S must be retuned to that
figure (then finely searched, matching the exact methodology I-07b-fix used
for its own gear/trigger calibration) so the bat still arrives near the
ball's actual arrival time.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from controllers.baseball_b1 import ALIGNMENT, CROSSING_TIME_S, OracleAimController
from envs.baseball_b1_env import BaseballB1Env

A_MAX_SWING = 134.4  # rad/s^2 at ctrl=1, gear=30 (controllers/baseball_b1.py, measured)
ACCEL_TARGET = ALIGNMENT["mid_mid"][0]  # -1.298, direction-independent geometric fact, unchanged
BASELINE_PREP_SWING = -1.9
BASELINE_CROSSING_TIME = CROSSING_TIME_S["mid_mid"][0]
SETTLE_QVEL = 0.2
SETTLE_STEPS = 40
PP_WINDOW_STEPS = 40  # 0.2s @ control_dt=0.005s
PP_TOL = 0.02


def run_episode(prep_swing: float, swing_crossing_time: float, course: str = "mid_mid") -> dict:
    """Runs one full mid_mid episode with the given prep_swing/crossing_time
    (tilt untouched -- mid_mid's tilt never needs to aim), returns the
    measurement table + timeline this section needs. CROSSING_TIME_S is a
    read-only mappingproxy (2026-09-17 cleanup) -- this builds its own local
    calibration dict for the controller instead of mutating the shared
    module default."""
    env = BaseballB1Env(prep_swing=prep_swing, prep_tilt=0.0)
    calibration = dict(CROSSING_TIME_S)
    calibration[course] = (swing_crossing_time, CROSSING_TIME_S[course][1])
    try:
        controller = OracleAimController(
            course, prep_swing=env.prep_swing, prep_tilt=env.prep_tilt, crossing_time_s=calibration
        )
        obs, _ = env.reset(seed=0, options={"course": course})
        controller.reset()

        timeline: list[dict] = []
        first_accel_t = None
        contact_t = None
        contact_angle = None
        brake_entry_t = None
        settled_t = None
        info: dict = {}
        bat_tip_local = np.array([0.35, 0.0, 0.0])  # bat_geom's own long axis tip, local to bat_tilt_body
        prev_state = controller._swing_axis.state  # read BEFORE act() mutates it

        while True:
            action = controller.act(obs)
            # controller.act() mutates _swing_axis.state as a side effect
            # (the transition happens INSIDE act(), not between calls) --
            # so `state` here is already the post-transition state for this
            # very step, and prev_state (captured at the end of the
            # PREVIOUS iteration, before this act() call) is the state the
            # action was actually computed under.
            state = controller._swing_axis.state
            obs, _reward, terminated, truncated, info = env.step(action)
            angle = float(env.data.qpos[env.swing_qpos_adr])
            vel = float(env.data.qvel[env.swing_qvel_adr])
            t = float(env.data.time)

            if prev_state == "prepare" and state != "prepare" and first_accel_t is None:
                first_accel_t = t
            if info["contact_occurred"] and contact_t is None:
                contact_t = info["first_contact_time_s"]
                contact_angle = angle
            if prev_state == "accelerate" and state == "brake" and brake_entry_t is None:
                brake_entry_t = t
            # "settled" per the design doc's own definition (docs/design/
            # BATTING-QUALITY-AND-SWING.md section 2 item 5) is measured
            # from the post-contact brake/latch, not from episode start --
            # the bat sits motionless (near-zero qvel) throughout the whole
            # "prepare" hold, which would trivially satisfy any |qvel|
            # threshold from t=0 if counted naively. Use _SwingAxis's own
            # internal brake->hold transition (the exact settle criterion
            # controllers/baseball_b1.py already implements) instead of
            # recomputing a second, differently-scoped streak here.
            if prev_state == "brake" and state == "hold" and settled_t is None:
                settled_t = t

            bat_tip_world = env.data.xpos[env.bat_body_id] + env.data.xmat[env.bat_body_id].reshape(3, 3) @ bat_tip_local
            bat_tip_vel = env._point_velocity(env.bat_body_id, bat_tip_world)

            timeline.append(
                {
                    "t": t,
                    "swing_state": state,
                    "swing_angle": angle,
                    "swing_vel": vel,
                    "swing_ctrl": float(action[0]),
                    "contact_occurred": bool(info["contact_occurred"]),
                    "phase": info["phase"],
                    "bat_tip_world": bat_tip_world.tolist(),
                    "bat_tip_speed": float(np.linalg.norm(bat_tip_vel)),
                }
            )
            prev_state = state
            if terminated or truncated:
                break

        final_angle = float(env.data.qpos[env.swing_qpos_adr])
        prep_to_contact_deg = (
            None if contact_angle is None else float(np.degrees(contact_angle - prep_swing))
        )
        contact_to_settle_deg = (
            None
            if (contact_angle is None or settled_t is None)
            else float(np.degrees(final_angle - contact_angle))
        )

        # peak-to-peak angle over the 0.2s window after the settle_t sample
        pp = None
        if settled_t is not None:
            window = [row["swing_angle"] for row in timeline if row["t"] >= settled_t][:PP_WINDOW_STEPS]
            if len(window) == PP_WINDOW_STEPS:
                pp = float(max(window) - min(window))

        result = {
            "prep_swing": prep_swing,
            "swing_crossing_time": swing_crossing_time,
            "prep_angle_rad": prep_swing,
            "first_accel_time_s": first_accel_t,
            "contact_time_s": contact_t,
            "contact_angle_rad": contact_angle,
            "brake_entry_time_s": brake_entry_t,
            "final_angle_rad": final_angle,
            "settled_time_s": settled_t,
            "settle_duration_after_contact_s": (
                None if (settled_t is None or contact_t is None) else settled_t - contact_t
            ),
            "angle_peak_to_peak_after_settle_rad": pp,
            "settle_meets_0_5s_target": (
                settled_t is not None and contact_t is not None and (settled_t - contact_t) <= 0.5
            ),
            "settle_meets_0_02rad_pp_target": (pp is not None and pp <= PP_TOL),
            "prep_to_contact_deg": prep_to_contact_deg,
            "contact_to_settle_deg": contact_to_settle_deg,
            "bat_contact_vx": info["bat_contact_vx"],
            "bat_contact_speed": (
                None
                if info["bat_contact_velocity"] is None
                else float(np.linalg.norm(info["bat_contact_velocity"]))
            ),
            "exit_velocity_xyz": info["exit_velocity_xyz"],
            "exit_speed": info["exit_speed"],
            "launch_angle_deg": (
                None if info["launch_angle_rad"] is None else float(np.degrees(info["launch_angle_rad"]))
            ),
            "forward_flight_success": info["forward_flight_success"],
            "status": info["status"],
            "scoring_valid": info["scoring_valid"],
            "carry_distance_m": info["carry_distance_m"],
            "landing_range_from_home_m": info["landing_range_from_home_m"],
            "batting_score": info["batting_score"],
            "reward_terms_batted_ball_v1": info["reward_terms"],
            "reward_terms_forward_carry_v1": info["forward_carry_v1"]["reward_terms"],
            "recontact_count": info["recontact_count"],
            "prolonged_contact": info["prolonged_contact"],
            "end_reason": info["end_reason"],
            "first_landing_xyz": info["first_landing_xyz"],
        }
        return result, timeline
    finally:
        env.close()


def analytic_crossing_time(delta_theta: float, a_max: float = A_MAX_SWING) -> float:
    return float(np.sqrt(2.0 * delta_theta / a_max))


def main() -> None:
    out_dir = Path("runs/env002-b1-swing-experiment")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== baseline (current mid_mid) ===")
    baseline, baseline_timeline = run_episode(BASELINE_PREP_SWING, BASELINE_CROSSING_TIME)
    print(json.dumps({k: v for k, v in baseline.items() if k not in ("reward_terms_batted_ball_v1", "reward_terms_forward_carry_v1")}, indent=2))

    # Candidate prep angles: as far back as the joint's [-2.0, 2.0] range
    # allows while keeping a small safety margin (joint is "limited=true",
    # so exactly -2.0 is legal, but a tiny margin avoids sitting exactly on
    # a hard constraint at reset).
    candidates_prep = [-1.9, -1.93, -1.95, -1.96, -1.98, -1.99]
    results = {}
    for prep in candidates_prep:
        delta_theta = ACCEL_TARGET - prep
        t_analytic = analytic_crossing_time(delta_theta)
        # local search around the analytic estimate: real contact/damping
        # dynamics deviate slightly, same methodology as I-07b-fix's own
        # gear/trigger sweep (docs/records/VALIDATION_LOG.md).
        best = None
        for dt_off in np.arange(-0.01, 0.0101, 0.001):
            t_try = float(t_analytic + dt_off)
            if t_try <= 0:
                continue
            res, _ = run_episode(prep, t_try)
            score = (res["exit_speed"] or 0.0) if res["scoring_valid"] else -1.0
            if best is None or score > best[0]:
                best = (score, t_try, res)
        results[prep] = best
        print(f"\n=== prep_swing={prep} best trigger={best[1]:.4f}s (analytic {t_analytic:.4f}s) ===")
        print(json.dumps({k: v for k, v in best[2].items() if k not in ("reward_terms_batted_ball_v1", "reward_terms_forward_carry_v1")}, indent=2))

    summary = {
        "baseline": baseline,
        "candidates": {str(p): r[2] for p, r in results.items()},
    }
    (out_dir / "swing_experiment_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (out_dir / "baseline_timeline.json").write_text(json.dumps(baseline_timeline, indent=2))
    print(f"\nWrote {out_dir}/swing_experiment_summary.json")


if __name__ == "__main__":
    main()

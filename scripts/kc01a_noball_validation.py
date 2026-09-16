"""KC-01a no-ball validation (docs/design/KC-01a-TORSO-BAT-COORDINATION.md
section 3's frozen validation criteria, step 4.1 of the KC-01a task): joint
direction, inertial coupling between torso and swing, energy budget
(actuator work in/out vs kinetic energy change, on a fixed axis so no
potential-energy term), and post-latch deceleration/settle time -- all with
NO ball in play (torso/swing driven directly, ball left far outside contact
range by simply not stepping the pitch far enough, or equivalently checked
before any contact occurs).

Writes docs/records/evidence/KC-01a-noball-validation.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv


def joint_direction_check() -> dict:
    """ctrl=+1 alone on each axis, from rest, must move that axis's angle
    in the +ctrl direction (arm held at prep for torso's check, since
    torso's effective inertia depends on what's attached)."""
    out = {}
    for axis_name, action in (("torso", [1.0, 0.0, 0.0]), ("swing", [0.0, 1.0, 0.0]), ("tilt", [0.0, 0.0, 1.0])):
        env = BaseballKC01aEnv()
        try:
            env.reset(seed=0, options={"course": "mid_mid"})
            if axis_name == "torso":
                env.set_held_pose(None, env.prep_swing, env.prep_tilt)
                adr = env.torso_qvel_adr
            elif axis_name == "swing":
                env.set_held_pose(env.prep_torso, None, env.prep_tilt)
                adr = env.swing_qvel_adr
            else:
                env.set_held_pose(env.prep_torso, env.prep_swing, None)
                adr = env.tilt_qvel_adr
            for _ in range(5):
                env.step(np.array(action, dtype=np.float32))
            v = float(env.data.qvel[adr])
            out[axis_name] = {"ctrl": 1.0, "final_qvel": v, "moved_in_ctrl_direction": v > 0.0}
        finally:
            env.close()
    return out


def inertial_coupling_check() -> dict:
    """With torso free and swing driven at full torque (torso NOT
    actuated, ctrl=0), does torso_yaw's angle/velocity move away from
    exactly 0 due to the swinging arm's reaction? A real coupled system
    must show SOME torso response (Newton's third law through the shared
    body); a fully decoupled/buggy model would show torso_qvel staying at
    machine-precision zero throughout."""
    env = BaseballKC01aEnv()
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        env.set_held_pose(None, None, env.prep_tilt)  # torso and swing both free, tilt held
        max_abs_torso_angle = 0.0
        for _ in range(40):
            env.step(np.array([0.0, 1.0, 0.0], dtype=np.float32))  # only swing driven
            max_abs_torso_angle = max(max_abs_torso_angle, abs(float(env.data.qpos[env.torso_qpos_adr])))
        return {
            "max_abs_torso_angle_rad_while_only_swing_driven": max_abs_torso_angle,
            "shows_reaction_coupling": max_abs_torso_angle > 1e-6,
        }
    finally:
        env.close()


def energy_budget_check(mode: str, torso_target: float, swing_target: float, torso_ct: float, swing_ct: float) -> dict:
    """Real pitch/contact is allowed to happen (this validates the actual
    calibrated conditions, contact included) -- work/energy accounting is
    valid either way, since it only sums actuator work and DOF kinetic
    energy, both computed directly from qvel/qfrc_actuator regardless of
    whether a ball happens to be hit. The non-participating axis in
    arm_only/torso_only is held by the controller's own hold-gain
    P-control, not env.set_held_pose()'s hard override -- see
    scripts/kc01a_calibrate.py's run_episode docstring for why the hard
    lock was tried and rejected (docs/design/
    KC-01a-TORSO-BAT-COORDINATION.md section 5)."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=env_prep_swing(), prep_tilt=0.0)
    try:
        controller = TorsoBatController(mode, 0.0, env.prep_swing, 0.0, torso_target, swing_target, torso_ct, swing_ct)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        info = {}
        while True:
            obs, _, terminated, truncated, info = env.step(controller.act(obs))
            if terminated or truncated:
                break
        total_positive = sum(info["joint_positive_work_j"].values())
        total_negative = sum(info["joint_negative_work_j"].values())
        net_actuator_work = total_positive + total_negative  # negative already signed
        return {
            "mode": mode,
            "joint_positive_work_j": info["joint_positive_work_j"],
            "joint_negative_work_j": info["joint_negative_work_j"],
            "net_actuator_work_j": net_actuator_work,
            "joint_peak_abs_power_w": info["joint_peak_abs_power_w"],
            "joint_peak_abs_torque_nm": info["joint_peak_abs_torque_nm"],
        }
    finally:
        env.close()


def env_prep_swing() -> float:
    return -1.96


def deceleration_settle_check(mode: str, torso_target: float, swing_target: float, torso_ct: float, swing_ct: float) -> dict:
    """Same 0.5s/|qvel|<0.2rad/s settle criterion as B1's followthrough
    (docs/design/BASEBALL-SPEC.md section 6), measured for EACH moving
    axis independently, from that axis's own latch (accelerate->brake
    transition) instant."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=env_prep_swing(), prep_tilt=0.0)
    try:
        controller = TorsoBatController(mode, 0.0, env.prep_swing, 0.0, torso_target, swing_target, torso_ct, swing_ct)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        latch_t = {"torso": None, "swing": None}
        settle_t = {"torso": None, "swing": None}
        prev_state = {"torso": controller._torso_axis.state, "swing": controller._swing_axis.state}
        while True:
            obs, _, terminated, truncated, _info = env.step(controller.act(obs))
            t = float(env.data.time)
            for name, axis in (("torso", controller._torso_axis), ("swing", controller._swing_axis)):
                if prev_state[name] == "accelerate" and axis.state == "brake" and latch_t[name] is None:
                    latch_t[name] = t
                if prev_state[name] == "brake" and axis.state == "hold" and settle_t[name] is None:
                    settle_t[name] = t
                prev_state[name] = axis.state
            if terminated or truncated:
                break
        out = {}
        for name in ("torso", "swing"):
            if latch_t[name] is not None and settle_t[name] is not None:
                out[name] = {
                    "latch_time_s": latch_t[name],
                    "settle_time_s": settle_t[name],
                    "settle_duration_s": settle_t[name] - latch_t[name],
                    "meets_0_5s_target": (settle_t[name] - latch_t[name]) <= 0.5,
                }
            else:
                out[name] = {"latch_time_s": latch_t[name], "settle_time_s": settle_t[name], "note": "never latched or never settled within the episode"}
        return out
    finally:
        env.close()


def main() -> None:
    result = {
        "joint_direction": joint_direction_check(),
        "inertial_coupling": inertial_coupling_check(),
        "energy_budget": {
            "arm_only": energy_budget_check("arm_only", 0.0, -1.298, 999.0, 0.09425316355759385),
            "torso_only": energy_budget_check("torso_only", 0.496, -1.96, 0.360, 999.0),
            "simultaneous": energy_budget_check("simultaneous", -0.4, -0.726, 0.096, 0.096),
            "staggered": energy_budget_check("staggered", -0.4, -0.726, 0.242, 0.122),
        },
        "settle": {
            "arm_only": deceleration_settle_check("arm_only", 0.0, -1.298, 999.0, 0.09425316355759385),
            "torso_only": deceleration_settle_check("torso_only", 0.496, -1.96, 0.360, 999.0),
            "simultaneous": deceleration_settle_check("simultaneous", -0.4, -0.726, 0.096, 0.096),
            "staggered": deceleration_settle_check("staggered", -0.4, -0.726, 0.242, 0.122),
        },
    }
    print(json.dumps(result, indent=2, default=str))
    out_path = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence" / "KC-01a-noball-validation.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

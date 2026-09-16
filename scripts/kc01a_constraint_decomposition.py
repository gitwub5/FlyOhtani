"""KC-01a divergence/energy decomposition, step 3 (user follow-up to
docs/records/KC-01a-VALIDATION.md A4): two separate questions the original
A4 script (scripts/kc01a_energy_validation.py) did not answer --

(1) WHEN does the torso joint limit actually activate during a real
    (with-ball) swing, relative to bat-ball contact and to the
    accelerate->brake latch, and how much of the deceleration-phase energy
    change does it account for vs actuator braking? A4 only reported the
    TOTAL work done by qfrc_constraint over the whole run, not its timing
    or its share of the braking-window energy change specifically.

(2) Is the leftover residual (after including qfrc_constraint) explained by
    an unmodeled CONSTRAINT TYPE (e.g. the with-ball run's qfrc_constraint
    mixes joint-limit AND ball-bat contact reaction on the same 3 DOF,
    which A4's no-ball-only scope never had to separate), or is it ordinary
    INTEGRATION (truncation) error that should shrink roughly linearly with
    dt? This script decomposes qfrc_constraint by MuJoCo's own per-row
    efc_type (LIMIT_JOINT vs CONTACT_* vs other) via the constraint
    Jacobian (qfrc_type = efc_J[rows of that type].T @ efc_force[those
    rows]) rather than assuming qfrc_constraint is one thing, and reruns
    the no-ball residual at a 3rd, finer dt to estimate the residual's
    convergence order.
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
GRAVITY = 9.81

CONDITIONS = {
    "arm_swing_with_torso_hold": {
        "controller_mode": "arm_only",
        "torso_target": 0.0,
        "swing_target": -1.298,
        "torso_ct": 999.0,
        "swing_ct": 0.09425316355759385,
    },
    "torso_swing_with_arm_hold": {
        "controller_mode": "torso_only",
        "torso_target": 0.496,
        "swing_target": -1.96,
        "torso_ct": 0.360,
        "swing_ct": 999.0,
    },
    "simultaneous_swing_and_torso": {
        "controller_mode": "simultaneous",
        "torso_target": -0.4,
        "swing_target": -0.726,
        "torso_ct": 0.096,
        "swing_ct": 0.096,
    },
    "staggered_swing_and_torso": {
        "controller_mode": "staggered",
        "torso_target": -0.4,
        "swing_target": -0.726,
        "torso_ct": 0.242,
        "swing_ct": 0.122,
    },
}

LIMIT_JOINT = int(mujoco.mjtConstraint.mjCNSTR_LIMIT_JOINT)
CONTACT_TYPES = {
    int(mujoco.mjtConstraint.mjCNSTR_CONTACT_FRICTIONLESS),
    int(mujoco.mjtConstraint.mjCNSTR_CONTACT_PYRAMIDAL),
    int(mujoco.mjtConstraint.mjCNSTR_CONTACT_ELLIPTIC),
}


def _qfrc_by_type(env, dof_slice=slice(0, 3)) -> dict:
    """Decomposes this instant's qfrc_constraint (restricted to dof_slice)
    into the sum contributed by LIMIT_JOINT rows vs CONTACT_* rows vs
    anything else, via the constraint Jacobian -- qfrc_constraint itself is
    J^T @ efc_force summed over ALL rows; this recomputes the same sum
    restricted to rows of one efc_type, which is a well-defined linear
    decomposition (not an approximation)."""
    d = env.data
    nefc = d.nefc
    nv = env.model.nv
    if nefc == 0:
        return {"limit_joint": np.zeros(3), "contact": np.zeros(3), "other": np.zeros(3)}
    efc_J = d.efc_J[: nefc * nv].reshape(nefc, nv)
    efc_force = d.efc_force[:nefc]
    efc_type = d.efc_type[:nefc]
    out = {"limit_joint": np.zeros(nv), "contact": np.zeros(nv), "other": np.zeros(nv)}
    for row in range(nefc):
        t = int(efc_type[row])
        contrib = efc_J[row] * efc_force[row]
        if t == LIMIT_JOINT:
            out["limit_joint"] += contrib
        elif t in CONTACT_TYPES:
            out["contact"] += contrib
        else:
            out["other"] += contrib
    return {k: v[dof_slice].copy() for k, v in out.items()}


def run_withball_constraint_timing(cfg: dict) -> dict:
    """Real (with-ball) episode at production dt, logging per-substep
    torso-limit activation and its work contribution, keyed to
    first_contact_time_s and the brake-latch instant (from the controller's
    own _torso_axis.state transition, same convention as
    scripts/kc01a_settle_diagnostics.py)."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = TorsoBatController(
            cfg["controller_mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        torso_range = list(env.model.jnt_range[env.torso_joint_id])
        first_limit_active_time: float | None = None
        latch_time: float | None = None
        prev_axis_state = None
        w_limit_torso_total = 0.0
        w_limit_torso_post_latch = 0.0
        w_actuator_torso_post_latch = 0.0
        w_damping_torso_post_latch = 0.0
        limit_active_substeps = 0
        dt = env.model.opt.timestep

        def substep_hook(env_, bat_hit, bat_vel, ball_vel):
            nonlocal first_limit_active_time, w_limit_torso_total, w_limit_torso_post_latch
            nonlocal w_actuator_torso_post_latch, w_damping_torso_post_latch, limit_active_substeps
            by_type = _qfrc_by_type(env_, dof_slice=slice(0, 1))
            limit_force_torso = float(by_type["limit_joint"][0])
            torso_vel = float(env_.data.qvel[env_.torso_qvel_adr])
            if abs(limit_force_torso) > 1e-9:
                limit_active_substeps += 1
                if first_limit_active_time is None:
                    first_limit_active_time = float(env_.data.time)
            w_step = limit_force_torso * torso_vel * dt
            w_limit_torso_total += w_step
            if latch_time is not None:
                w_limit_torso_post_latch += w_step
                w_actuator_torso_post_latch += float(env_.data.qfrc_actuator[0]) * torso_vel * dt
                w_damping_torso_post_latch += float(env_.data.qfrc_passive[0]) * torso_vel * dt

        info = {}
        while True:
            axis_state = controller._torso_axis.state
            if prev_axis_state == "accelerate" and axis_state == "brake" and latch_time is None:
                latch_time = float(env.data.time)
            prev_axis_state = axis_state
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action, substep_callback=substep_hook)
            if terminated or truncated:
                break

        return {
            "first_contact_time_s": info["first_contact_time_s"],
            "brake_latch_time_s": latch_time,
            "first_torso_limit_active_time_s": first_limit_active_time,
            "limit_active_substeps": limit_active_substeps,
            "time_from_latch_to_limit_active_s": (
                None if latch_time is None or first_limit_active_time is None else first_limit_active_time - latch_time
            ),
            "time_from_contact_to_limit_active_s": (
                None
                if info["first_contact_time_s"] is None or first_limit_active_time is None
                else first_limit_active_time - info["first_contact_time_s"]
            ),
            "w_limit_torso_total_j": w_limit_torso_total,
            "w_limit_torso_post_latch_j": w_limit_torso_post_latch,
            "w_actuator_torso_post_latch_j": w_actuator_torso_post_latch,
            "w_damping_torso_post_latch_j": w_damping_torso_post_latch,
            "torso_range_rad": torso_range,
            "end_reason": info["end_reason"],
            "scoring_valid": info["scoring_valid"],
        }
    finally:
        env.close()


SUBSYSTEM_BODIES = ["torso_body", "bat_body", "bat_tilt_body"]


def _subsystem_ke(env) -> float:
    nv = env.model.nv
    m_full = np.zeros((nv, nv))
    mujoco.mj_fullM(env.model, env.data, m_full)
    qvel3 = env.data.qvel[:3]
    return float(0.5 * qvel3 @ m_full[:3, :3] @ qvel3)


def _subsystem_pe(env, body_ids: list[int]) -> float:
    return float(sum(env.model.body_mass[bid] * GRAVITY * env.data.xipos[bid][2] for bid in body_ids))


def run_noball_energy_3dt(cfg: dict, dt: float, frame_skip: int) -> dict:
    """Same computation as scripts/kc01a_energy_validation.py's
    run_noball_energy, PLUS a decomposition of qfrc_constraint into
    limit_joint/contact/other via _qfrc_by_type (no-ball, so 'contact'
    should be ~0 -- verified rather than assumed) so the constraint-type
    question and the dt-scaling question can both be read off one run."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    control_dt = env.model.opt.timestep * env.frame_skip
    env.model.opt.timestep = dt
    env.frame_skip = frame_skip
    assert abs(dt * frame_skip - control_dt) < 1e-12
    try:
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0
        body_ids = [mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_BODY, n) for n in SUBSYSTEM_BODIES]

        controller = TorsoBatController(
            cfg["controller_mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
        )
        env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        ke0 = _subsystem_ke(env)
        pe0 = _subsystem_pe(env, body_ids)
        w_actuator = w_damping = w_limit = w_contact = w_other = 0.0
        n_control_steps = round(2.5 / control_dt)
        for _ in range(n_control_steps):
            obs = env._get_obs()
            action = controller.act(obs)
            env.data.ctrl[env.torso_actuator_id] = float(np.clip(action[0], -1.0, 1.0))
            env.data.ctrl[env.swing_actuator_id] = float(np.clip(action[1], -1.0, 1.0))
            env.data.ctrl[env.tilt_actuator_id] = float(np.clip(action[2], -1.0, 1.0))
            for _ in range(env.frame_skip):
                mujoco.mj_step(env.model, env.data)
                mujoco.mj_forward(env.model, env.data)
                qvel3 = env.data.qvel[:3]
                by_type = _qfrc_by_type(env, dof_slice=slice(0, 3))
                for i in range(3):
                    w_actuator += float(env.data.qfrc_actuator[i] * qvel3[i]) * dt
                    w_damping += float(env.data.qfrc_passive[i] * qvel3[i]) * dt
                    w_limit += float(by_type["limit_joint"][i] * qvel3[i]) * dt
                    w_contact += float(by_type["contact"][i] * qvel3[i]) * dt
                    w_other += float(by_type["other"][i] * qvel3[i]) * dt

        ke1 = _subsystem_ke(env)
        pe1 = _subsystem_pe(env, body_ids)
        delta_e = (ke1 + pe1) - (ke0 + pe0)
        w_constraint_total = w_limit + w_contact + w_other
        predicted = w_actuator + w_damping + w_constraint_total
        residual = delta_e - predicted
        return {
            "dt": dt,
            "delta_ke_plus_pe": delta_e,
            "w_actuator_net": w_actuator,
            "w_damping": w_damping,
            "w_limit_joint": w_limit,
            "w_contact_noball_should_be_zero": w_contact,
            "w_other_constraint": w_other,
            "w_constraint_total": w_constraint_total,
            "predicted_delta_e": predicted,
            "residual": residual,
            "residual_fraction_of_w_actuator": (residual / w_actuator) if abs(w_actuator) > 1e-9 else None,
        }
    finally:
        env.close()


def main() -> None:
    result = {"withball_constraint_timing": {}, "noball_energy_3dt": {}}

    print("=== with-ball: torso joint-limit activation timing ===")
    for mode, cfg in CONDITIONS.items():
        r = run_withball_constraint_timing(cfg)
        result["withball_constraint_timing"][mode] = r
        print(f"{mode}: first_limit_active={r['first_torso_limit_active_time_s']} "
              f"(latch={r['brake_latch_time_s']}, contact={r['first_contact_time_s']}) "
              f"w_limit_post_latch={r['w_limit_torso_post_latch_j']:.4f}J "
              f"w_actuator_post_latch={r['w_actuator_torso_post_latch_j']:.4f}J")

    print("\n=== no-ball energy at 3 dt levels, constraint-type decomposition ===")
    dt_frame_skip = [(0.00025, 20), (0.000125, 40), (0.0000625, 80)]
    for mode, cfg in CONDITIONS.items():
        per_dt = {}
        for dt, fs in dt_frame_skip:
            r = run_noball_energy_3dt(cfg, dt, fs)
            per_dt[str(dt)] = r
            print(f"{mode} dt={dt}: residual={r['residual']:.4f}J ({r['residual_fraction_of_w_actuator']}) "
                  f"w_limit={r['w_limit_joint']:.4f}J w_contact(should~0)={r['w_contact_noball_should_be_zero']:.6f}J w_other={r['w_other_constraint']:.6f}J")
        residuals = [per_dt[str(dt)]["residual"] for dt, _ in dt_frame_skip]
        # Convergence order estimate: halving dt should roughly halve
        # (order~1, semi-implicit Euler truncation) a pure integration
        # error; a residual that does NOT shrink with dt indicates a
        # still-missing physical term rather than truncation error.
        order_estimates = []
        for i in range(len(residuals) - 1):
            a, b = abs(residuals[i]), abs(residuals[i + 1])
            if a > 1e-9 and b > 1e-9:
                order_estimates.append(float(np.log2(a / b)))
        per_dt["residual_convergence_order_estimates"] = order_estimates
        per_dt["interpretation"] = (
            "order~1 (or higher) => consistent with ordinary integration truncation error, shrinking with dt"
            if order_estimates and min(order_estimates) > 0.5
            else "order~0/flat or not computable => NOT consistent with pure truncation error; may indicate a still-unmodeled term"
        )
        result["noball_energy_3dt"][mode] = per_dt
        print(f"  {mode} residual convergence order estimates: {order_estimates} -> {per_dt['interpretation']}")

    out_path = OUT_DIR / "KC-01a-constraint-decomposition.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

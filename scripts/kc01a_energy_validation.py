"""KC-01a-validation A4, part 1 (docs/tasks/KC-01a-VALIDATION-AND-VISION.md):
no-ball energy-residual validation. Scoped to no-ball swings only, as the
task explicitly specifies ("먼저 무공에서") -- a real pitch adds ball-bat
collision energy exchange and ball-ground contact dissipation, a separate,
harder accounting problem this script does not attempt.

For the torso+bat subsystem (torso_yaw, bat_hinge, bat_tilt_hinge -- the
first 3 generalized DOF; the ball's free joint is mechanically decoupled
from these while no contact occurs, so the mass matrix is block-diagonal
and a 3x3 submatrix gives this subsystem's own kinetic energy exactly, no
cross terms to account for):

  delta(KE + PE) = W_actuator_net + W_damping + residual

  KE = 0.5 * qvel[:3]^T @ M[:3,:3] @ qvel[:3]           (mj_fullM)
  PE = sum(body_mass_i * 9.81 * body_com_height_i)       (torso/bat bodies only)
  W_actuator_net = integral of qfrc_actuator[i] * qvel[i] dt, summed over
                   the 3 DOF (same quantity envs/baseball_kc01a_env.py's
                   own _accumulate_joint_work tracks, recomputed here
                   independently rather than importing it, so a bug in one
                   does not silently validate the other)
  W_damping = integral of qfrc_passive[i] * qvel[i] dt (MuJoCo's own
              damping/passive-force accounting, negative = energy removed)
  residual = whatever is left over -- reported explicitly, not hidden.
             A large residual is a real finding (e.g. an unsupported term,
             or joint-limit constraint forces doing work when a range is
             hit), not swept under a "numerical error" label without
             evidence.

Also reports how the residual changes as physics_dt is halved (A2's own
diagnostic, applied to this narrower energy question).
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

SUBSYSTEM_BODIES = ["torso_body", "bat_body", "bat_tilt_body"]


def _subsystem_ke(env) -> float:
    nv = env.model.nv
    m_full = np.zeros((nv, nv))
    mujoco.mj_fullM(env.model, env.data, m_full)
    qvel3 = env.data.qvel[:3]
    m3 = m_full[:3, :3]
    return float(0.5 * qvel3 @ m3 @ qvel3)


def _subsystem_pe(env, body_ids: list[int]) -> float:
    return float(sum(env.model.body_mass[bid] * GRAVITY * env.data.xipos[bid][2] for bid in body_ids))


def run_noball_energy(cfg: dict, dt: float, frame_skip: int) -> dict:
    """Drives physics directly (mj_step, never env.step()) for the whole
    run -- the env's own phase/outcome bookkeeping is irrelevant here
    (bat collision is disabled, so there is no contact/score to track) and
    mixing env.step() with manual mj_step calls would double-step physics.
    The controller's own remaining-time trigger still reads real
    (unmodified) ball position/velocity via env._get_obs(), so it fires at
    its normal time even though the ball cannot actually be hit."""
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

        w_actuator = 0.0
        w_damping = 0.0
        w_constraint = 0.0
        torso_range = list(env.model.jnt_range[env.torso_joint_id])
        max_abs_torso_angle = 0.0
        # Run for a fixed, generous wall-clock duration (2.5s: comfortably
        # covers the ~0.46s pitch arrival plus >=1.2s of post-latch
        # continuation, matching A3's own settle-observation window) so
        # the subsystem has actually settled before the energy snapshot,
        # not cut off mid-swing.
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
                for i in range(3):
                    w_actuator += float(env.data.qfrc_actuator[i] * env.data.qvel[i]) * dt
                    w_damping += float(env.data.qfrc_passive[i] * env.data.qvel[i]) * dt
                    w_constraint += float(env.data.qfrc_constraint[i] * env.data.qvel[i]) * dt
                max_abs_torso_angle = max(max_abs_torso_angle, abs(float(env.data.qpos[env.torso_qpos_adr])))

        ke1 = _subsystem_ke(env)
        pe1 = _subsystem_pe(env, body_ids)
        delta_e = (ke1 + pe1) - (ke0 + pe0)
        # w_constraint is included as a SUPPORTED term here (not folded
        # silently into "residual"): qfrc_constraint captures joint-limit
        # reaction forces, which do real work (absorb kinetic energy) any
        # time a joint's own range is reached -- a real physical energy
        # sink this subsystem can hit, not a numerical artifact.
        predicted = w_actuator + w_damping + w_constraint
        residual = delta_e - predicted
        hit_torso_limit = max_abs_torso_angle >= abs(torso_range[1]) - 1e-4
        return {
            "dt": dt,
            "ke0": ke0,
            "pe0": pe0,
            "ke1": ke1,
            "pe1": pe1,
            "delta_ke_plus_pe": delta_e,
            "w_actuator_net": w_actuator,
            "w_damping": w_damping,
            "w_constraint": w_constraint,
            "predicted_delta_e": predicted,
            "residual": residual,
            "residual_fraction_of_w_actuator": (residual / w_actuator) if abs(w_actuator) > 1e-9 else None,
            "torso_range_rad": torso_range,
            "max_abs_torso_angle_observed_rad": max_abs_torso_angle,
            "hit_torso_joint_limit": hit_torso_limit,
        }
    finally:
        env.close()


def main() -> None:
    # NOTE on the "common budget comparison" half of A4 (docs/tasks/
    # KC-01a-VALIDATION-AND-VISION.md): "A2 통과 후에만 공통... 한도 아래
    # 비교한다" gates that comparison on A2 passing. A2 (docs/records/
    # evidence/KC-01a-dt-convergence.json) did not converge for 3 of 4
    # conditions, so no budget-constrained re-comparison is run here --
    # doing so would need its own A2 convergence pass per the task's own
    # rule, which is deferred to a follow-up task. What IS produced below
    # is the per-condition no-ball W+/peak-power/peak-torque data a future
    # budget would be drawn from (see docs/records/KC-01a-VALIDATION.md).
    result = {"noball_energy": {}}
    for mode, cfg in CONDITIONS.items():
        print(f"=== {mode} ===")
        per_dt = {}
        for dt, frame_skip in ((0.00025, 20), (0.000125, 40)):
            r = run_noball_energy(cfg, dt, frame_skip)
            per_dt[str(dt)] = r
            print(
                f"  dt={dt}: delta(KE+PE)={r['delta_ke_plus_pe']:.4f}J  "
                f"W_actuator={r['w_actuator_net']:.4f}J  W_damping={r['w_damping']:.4f}J  "
                f"residual={r['residual']:.4f}J ({r['residual_fraction_of_w_actuator']})"
            )
        result["noball_energy"][mode] = per_dt

    out_path = OUT_DIR / "KC-01a-energy-validation.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

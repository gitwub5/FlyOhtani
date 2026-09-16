"""KC-01a divergence decomposition, step 1 (user follow-up to
docs/records/KC-01a-VALIDATION.md A2): isolate whether the DRIVEN
torso/swing trajectory itself (actuator + passive dynamics + integration,
NO ball-bat collision at all) is already dt-sensitive, before asking
whether the CONTACT resolution adds further sensitivity on top (that
question is scripts/kc01a_contact_only_dt_isolation.py). If this script
finds negligible divergence, A2's "접촉의 이산화 민감도로 추정" hypothesis
(docs/records/KC-01a-VALIDATION.md section A2, now downgraded to a
hypothesis pending this decomposition) gains support; if this script ALSO
diverges by itself, the drive/integration side is a real contributor too
and that hypothesis must be revised.

Method: same technique as scripts/kc01a_energy_validation.py's
run_noball_energy -- bat collision disabled (contype/conaffinity=0 on
bat_geom), physics driven directly via mj_step for a FIXED number of
control steps (not until env-detected termination, so the three dt
candidates are compared at identical control-step indices, with no
termination-timing confound), same controller/timing as the real
(preserved, diagnostic) 4 conditions. Compares the two finest dt candidates
(0.000125s, 0.0000625s) at every matching control step.

Runs the SAME 4 conditions as docs/records/KC-01a-VALIDATION.md A2 --
condition definitions/targets are copied verbatim, not modified (docs/
design/KC-01a-DIRECTION-CONTRACT.md section 3: preserve as diagnostic
record).
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

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

DT_FINE = 0.000125
DT_FINEST = 0.0000625
FRAME_SKIP_FINE = 40
FRAME_SKIP_FINEST = 80
RUN_DURATION_S = 2.5  # matches kc01a_energy_validation.py's own window

# Pre-registered BEFORE running (same spirit as A2's own thresholds,
# extended to a per-control-step angle-trajectory comparison rather than a
# single terminal outcome).
ANGLE_ABS_TOL_RAD = 0.01
ANGLE_REL_TOL = 0.02


def run_noball_trajectory(cfg: dict, dt: float, frame_skip: int) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    control_dt = env.model.opt.timestep * env.frame_skip
    env.model.opt.timestep = dt
    env.frame_skip = frame_skip
    assert abs(dt * frame_skip - control_dt) < 1e-12
    try:
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0
        controller = TorsoBatController(
            cfg["controller_mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
        )
        env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        n_steps = round(RUN_DURATION_S / control_dt)
        torso_traj = np.zeros(n_steps)
        swing_traj = np.zeros(n_steps)
        for i in range(n_steps):
            obs = env._get_obs()
            action = controller.act(obs)
            env.data.ctrl[env.torso_actuator_id] = float(np.clip(action[0], -1.0, 1.0))
            env.data.ctrl[env.swing_actuator_id] = float(np.clip(action[1], -1.0, 1.0))
            env.data.ctrl[env.tilt_actuator_id] = float(np.clip(action[2], -1.0, 1.0))
            for _ in range(env.frame_skip):
                mujoco.mj_step(env.model, env.data)
            mujoco.mj_forward(env.model, env.data)
            torso_traj[i] = env.data.qpos[env.torso_qpos_adr]
            swing_traj[i] = env.data.qpos[env.swing_qpos_adr]
        return {"torso": torso_traj, "swing": swing_traj, "control_dt": control_dt}
    finally:
        env.close()


def compare(mode: str, cfg: dict) -> dict:
    fine = run_noball_trajectory(cfg, DT_FINE, FRAME_SKIP_FINE)
    finest = run_noball_trajectory(cfg, DT_FINEST, FRAME_SKIP_FINEST)
    assert len(fine["torso"]) == len(finest["torso"]), "control-step count must match (control_dt fixed by construction)"

    out = {}
    for axis in ("torso", "swing"):
        diff = np.abs(fine[axis] - finest[axis])
        amplitude = abs(cfg[f"{axis}_target"] - (0.0 if axis == "torso" else -1.96))
        tol = max(ANGLE_ABS_TOL_RAD, ANGLE_REL_TOL * amplitude)
        max_diff = float(diff.max())
        out[axis] = {
            "max_abs_diff_rad": max_diff,
            "final_abs_diff_rad": float(diff[-1]),
            "argmax_control_step": int(diff.argmax()),
            "argmax_time_s": float(diff.argmax() * fine["control_dt"]),
            "amplitude_rad": amplitude,
            "tol_rad": tol,
            "converged": max_diff <= tol,
        }
    out["condition_converged_driveonly"] = out["torso"]["converged"] and out["swing"]["converged"]
    return out


def main() -> None:
    result = {"thresholds": {"angle_abs_tol_rad": ANGLE_ABS_TOL_RAD, "angle_rel_tol": ANGLE_REL_TOL}, "per_condition": {}}
    for mode, cfg in CONDITIONS.items():
        print(f"=== {mode} (drive-only, no ball-bat collision) ===")
        r = compare(mode, cfg)
        result["per_condition"][mode] = r
        print(f"  torso: max_diff={r['torso']['max_abs_diff_rad']:.6f} tol={r['torso']['tol_rad']:.6f} converged={r['torso']['converged']}")
        print(f"  swing: max_diff={r['swing']['max_abs_diff_rad']:.6f} tol={r['swing']['tol_rad']:.6f} converged={r['swing']['converged']}")
        print(f"  DRIVE-ONLY CONVERGED: {r['condition_converged_driveonly']}")

    out_path = OUT_DIR / "KC-01a-noball-dt-isolation.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

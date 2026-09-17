"""VM-01 P1 (docs/tasks/VISUOMOTOR-PIVOT.md, docs/design/
CONTACT-VALIDATION-P1-SPEC.md): isolated ball-vs-fixed-plate and
ball-vs-free-bat collision experiments, NO torso/swing/bat controller at
all -- envs/assets/contact_validation_p1.xml is a standalone asset, not
BaseballKC01aEnv. gear/material/joint ranges of the actual B1/KC-01a bodies
are never touched by this script; it only reproduces ball_geom/bat_geom's
OWN production values in an isolated model to study the collision alone.

Every acceptance threshold here is imported from this file's own constants,
matching CONTACT-VALIDATION-P1-SPEC.md's table EXACTLY (copy-pasted, not
re-derived) -- fixed BEFORE any run below.
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

ASSET_PATH = Path(__file__).resolve().parent.parent / "envs" / "assets" / "contact_validation_p1.xml"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

# --- Pre-registered acceptance thresholds (CONTACT-VALIDATION-P1-SPEC.md section 3, copied verbatim) ---
BALL_RADIUS_M = 0.0366
BAT_RADIUS_M = 0.025
MAX_ALLOWED_PENETRATION_M = 0.30 * min(BALL_RADIUS_M, BAT_RADIUS_M)  # 0.0075m -- an engineering margin, NOT a literature COR
COR_ACCEPTABLE_RANGE = (0.3, 0.7)
DT_CONVERGENCE_REL_TOL = 0.02
DT_CONVERGENCE_ABS_TOL = 0.01
ENERGY_RESIDUAL_TOL_FRACTION = 0.05
MOMENTUM_CONSERVATION_TOL_FRACTION = 0.01

APPROACH_SPEED_M_S = 35.0  # matches envs/assets/baseball_park_kc01a.xml's own HORIZONTAL_SPEED order of magnitude
DT_CANDIDATES = [0.00025, 0.000125, 0.0000625]
BASE_FRAME_SKIP = 1  # we step substep-by-substep here (no control_dt abstraction needed, no actuators exist)
SIM_WINDOW_S = 0.06  # generous: ~13ms approach + contact + >=40ms clear separation margin (a first, too-short 20ms window was caught cutting off mid-contact -- see comment at call sites)


def _fmt(x, spec=".4f"):
    return format(x, spec) if x is not None else "None"


class ContactRecorder:
    def __init__(self, ball_geom_id: int, target_geom_id: int) -> None:
        self.ball_geom_id = ball_geom_id
        self.target_geom_id = target_geom_id
        self.min_dist: float | None = None
        self.max_normal_force_n = 0.0
        self.impulse_n_s = np.zeros(3)
        self.first_t: float | None = None
        self.last_t: float | None = None
        self.n_active_substeps = 0

    def record(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        active_this_step = False
        for idx in range(data.ncon):
            c = data.contact[idx]
            pair = {c.geom1, c.geom2}
            if self.ball_geom_id in pair and self.target_geom_id in pair:
                active_this_step = True
                if self.min_dist is None or float(c.dist) < self.min_dist:
                    self.min_dist = float(c.dist)
                force6 = np.zeros(6)
                mujoco.mj_contactForce(model, data, idx, force6)
                normal_force = float(force6[0])
                self.max_normal_force_n = max(self.max_normal_force_n, abs(normal_force))
                normal_world = np.array(c.frame[:3])
                self.impulse_n_s += normal_world * normal_force * model.opt.timestep
        if active_this_step:
            self.n_active_substeps += 1
            if self.first_t is None:
                self.first_t = float(data.time)
            self.last_t = float(data.time)

    @property
    def contact_duration_s(self) -> float | None:
        if self.first_t is None or self.last_t is None:
            return None
        return self.last_t - self.first_t


def _make_model_data(dt: float):
    model = mujoco.MjModel.from_xml_path(str(ASSET_PATH))
    model.opt.timestep = dt
    data = mujoco.MjData(model)
    return model, data


def run_fixed_plate(dt: float, n_substeps: int) -> dict:
    model, data = _make_model_data(dt)
    ball_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
    plate_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "fixed_plate")
    bat_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "free_bat")
    model.geom_contype[bat_geom_id] = 0
    model.geom_conaffinity[bat_geom_id] = 0

    ball_qpos_adr = model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]
    ball_qvel_adr = model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]

    data.qpos[ball_qpos_adr : ball_qpos_adr + 3] = [3.8, 0, 1]
    data.qpos[ball_qpos_adr + 3 : ball_qpos_adr + 7] = [1, 0, 0, 0]
    data.qvel[ball_qvel_adr : ball_qvel_adr + 3] = [APPROACH_SPEED_M_S, 0, 0]
    mujoco.mj_forward(model, data)

    recorder = ContactRecorder(ball_geom_id, plate_geom_id)
    v_in = data.qvel[ball_qvel_adr]
    ke0 = 0.5 * 0.145 * float(np.dot(data.qvel[ball_qvel_adr : ball_qvel_adr + 3], data.qvel[ball_qvel_adr : ball_qvel_adr + 3]))
    for _ in range(n_substeps):
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        recorder.record(model, data)
    v_out = float(data.qvel[ball_qvel_adr])
    ke1 = 0.5 * 0.145 * float(np.dot(data.qvel[ball_qvel_adr : ball_qvel_adr + 3], data.qvel[ball_qvel_adr : ball_qvel_adr + 3]))
    cor = -v_out / v_in if v_in != 0 else None

    return {
        "dt": dt,
        "v_in_m_s": float(v_in),
        "v_out_m_s": v_out,
        "cor": cor,
        "min_dist_m": recorder.min_dist,
        "max_normal_force_n": recorder.max_normal_force_n,
        "impulse_magnitude_n_s": float(np.linalg.norm(recorder.impulse_n_s)),
        "contact_duration_s": recorder.contact_duration_s,
        "ke0_j": ke0,
        "ke1_j": ke1,
        "ke_dissipated_j": ke0 - ke1,
    }


def run_free_bat(dt: float, n_substeps: int) -> dict:
    model, data = _make_model_data(dt)
    ball_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
    plate_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "fixed_plate")
    bat_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "free_bat")
    model.geom_contype[plate_geom_id] = 0
    model.geom_conaffinity[plate_geom_id] = 0

    ball_qpos_adr = model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]
    ball_qvel_adr = model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]
    bat_qpos_adr = model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "free_bat_joint")]
    bat_qvel_adr = model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "free_bat_joint")]

    data.qpos[ball_qpos_adr : ball_qpos_adr + 3] = [-5, 1.2, 1]
    data.qpos[ball_qpos_adr + 3 : ball_qpos_adr + 7] = [1, 0, 0, 0]
    data.qvel[ball_qvel_adr : ball_qvel_adr + 3] = [0, -APPROACH_SPEED_M_S, 0]
    data.qpos[bat_qpos_adr + 3 : bat_qpos_adr + 7] = [1, 0, 0, 0]
    mujoco.mj_forward(model, data)

    recorder = ContactRecorder(ball_geom_id, bat_geom_id)
    ball_mass, bat_mass = 0.145, 0.9

    def momentum(d) -> np.ndarray:
        return ball_mass * d.qvel[ball_qvel_adr : ball_qvel_adr + 3] + bat_mass * d.qvel[bat_qvel_adr : bat_qvel_adr + 3]

    p0 = momentum(data).copy()
    t0 = float(data.time)
    ke0 = 0.5 * ball_mass * float(np.dot(data.qvel[ball_qvel_adr : ball_qvel_adr + 3], data.qvel[ball_qvel_adr : ball_qvel_adr + 3]))
    v_in = APPROACH_SPEED_M_S

    for _ in range(n_substeps):
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        recorder.record(model, data)

    p1 = momentum(data)
    elapsed = float(data.time) - t0
    # Gravity is a REAL external force in this model (matches production);
    # over the ~60ms observation window (mostly free flight before/after
    # the actual ~ms-scale contact) it accumulates a z-momentum change that
    # has nothing to do with the collision itself. "Momentum conservation"
    # here means no external force BESIDES gravity acted -- so gravity's
    # own (exactly known) contribution is subtracted before checking, not
    # ignored or hidden (an earlier version of this check did not do this
    # and flagged a spurious ~12% "violation" that was entirely gravity's
    # z-impulse over the full window, verified by hand: (0.145+0.9 kg) *
    # 9.81 m/s^2 * ~0.06s / |p0| = the exact reported discrepancy).
    gravity_impulse = np.array([0.0, 0.0, -9.81]) * (ball_mass + bat_mass) * elapsed
    p1_gravity_adjusted = p1 - gravity_impulse
    momentum_change = float(np.linalg.norm(p1_gravity_adjusted - p0))
    p0_mag = float(np.linalg.norm(p0))

    ball_v_out = data.qvel[ball_qvel_adr : ball_qvel_adr + 3].copy()
    bat_v_out = data.qvel[bat_qvel_adr : bat_qvel_adr + 3].copy()
    ke1 = 0.5 * ball_mass * float(np.dot(ball_v_out, ball_v_out)) + 0.5 * bat_mass * float(np.dot(bat_v_out, bat_v_out))
    # Approximate 1D COR along the approach axis (-Y): relative separation
    # speed / relative approach speed, both projected onto that axis.
    rel_approach = v_in  # bat starts at rest
    rel_separation = float(bat_v_out[1] - ball_v_out[1])
    cor = abs(rel_separation) / rel_approach if rel_approach != 0 else None

    return {
        "dt": dt,
        "v_in_m_s": v_in,
        "cor_approx_1d": cor,
        "min_dist_m": recorder.min_dist,
        "max_normal_force_n": recorder.max_normal_force_n,
        "impulse_magnitude_n_s": float(np.linalg.norm(recorder.impulse_n_s)),
        "contact_duration_s": recorder.contact_duration_s,
        "ke0_j": ke0,
        "ke1_j": ke1,
        "momentum_before": p0.tolist(),
        "momentum_after_raw": p1.tolist(),
        "gravity_impulse_n_s": gravity_impulse.tolist(),
        "momentum_after_gravity_adjusted": p1_gravity_adjusted.tolist(),
        "momentum_change_n_s": momentum_change,
        "momentum_change_fraction": (momentum_change / p0_mag) if p0_mag > 1e-9 else None,
        "ball_exit_v": ball_v_out.tolist(),
        "bat_exit_v": bat_v_out.tolist(),
    }


def check_dt_convergence(results_by_dt: dict, keys: list[str]) -> dict:
    finest, fine = str(DT_CANDIDATES[2]), str(DT_CANDIDATES[1])
    out = {}
    for key in keys:
        a, b = results_by_dt[fine].get(key), results_by_dt[finest].get(key)
        if a is None or b is None:
            out[key] = {"ok": None, "reason": "missing value"}
            continue
        diff = abs(a - b)
        tol = max(DT_CONVERGENCE_ABS_TOL, DT_CONVERGENCE_REL_TOL * abs(b))
        out[key] = {"diff": diff, "tol": tol, "ok": diff <= tol}
    return out


def main() -> None:
    result: dict = {"thresholds": {
        "max_allowed_penetration_m": MAX_ALLOWED_PENETRATION_M,
        "cor_acceptable_range": COR_ACCEPTABLE_RANGE,
        "dt_convergence_rel_tol": DT_CONVERGENCE_REL_TOL,
        "dt_convergence_abs_tol": DT_CONVERGENCE_ABS_TOL,
        "energy_residual_tol_fraction": ENERGY_RESIDUAL_TOL_FRACTION,
        "momentum_conservation_tol_fraction": MOMENTUM_CONSERVATION_TOL_FRACTION,
    }}

    print("=== P1a: ball vs FIXED plate (no bat/torso control) ===")
    fixed_by_dt = {}
    for dt in DT_CANDIDATES:
        n_substeps = round(SIM_WINDOW_S / dt)
        r = run_fixed_plate(dt, n_substeps)
        fixed_by_dt[str(dt)] = r
        print(f"  dt={dt}: cor={r['cor']:.4f} min_dist={r['min_dist_m']:.5f}m force={r['max_normal_force_n']:.1f}N duration={r['contact_duration_s']}")
    fixed_convergence = check_dt_convergence(fixed_by_dt, ["cor", "min_dist_m", "impulse_magnitude_n_s"])
    fixed_prod = fixed_by_dt[str(DT_CANDIDATES[0])]
    fixed_penetration_ok = abs(fixed_prod["min_dist_m"]) <= MAX_ALLOWED_PENETRATION_M if fixed_prod["min_dist_m"] is not None else None
    fixed_cor_ok = fixed_prod["cor"] is not None and COR_ACCEPTABLE_RANGE[0] <= fixed_prod["cor"] <= COR_ACCEPTABLE_RANGE[1]
    predicted_ke1 = fixed_prod["ke0_j"] * (fixed_prod["cor"] ** 2) if fixed_prod["cor"] is not None else None
    fixed_energy_residual = (fixed_prod["ke1_j"] - predicted_ke1) if predicted_ke1 is not None else None
    fixed_energy_ok = (abs(fixed_energy_residual) <= ENERGY_RESIDUAL_TOL_FRACTION * fixed_prod["ke0_j"]) if fixed_energy_residual is not None else None

    result["fixed_plate"] = {
        "by_dt": fixed_by_dt,
        "dt_convergence": fixed_convergence,
        "production_dt_checks": {
            "penetration_ok": fixed_penetration_ok,
            "cor_ok": fixed_cor_ok,
            "energy_residual_j": fixed_energy_residual,
            "energy_residual_ok": fixed_energy_ok,
        },
    }
    print(f"  PRODUCTION-DT CHECKS: penetration_ok={fixed_penetration_ok} cor_ok={fixed_cor_ok} energy_ok={fixed_energy_ok}")
    print(f"  DT CONVERGENCE: {fixed_convergence}")

    print("\n=== P1b: ball vs FREE bat (no bat/torso control, momentum must be conserved) ===")
    free_by_dt = {}
    for dt in DT_CANDIDATES:
        n_substeps = round(SIM_WINDOW_S / dt)
        r = run_free_bat(dt, n_substeps)
        free_by_dt[str(dt)] = r
        print(f"  dt={dt}: cor_1d={_fmt(r['cor_approx_1d'])} min_dist={_fmt(r['min_dist_m'], '.5f')}m momentum_change_frac={r['momentum_change_fraction']}")
    free_convergence = check_dt_convergence(free_by_dt, ["cor_approx_1d", "min_dist_m", "impulse_magnitude_n_s"])
    free_prod = free_by_dt[str(DT_CANDIDATES[0])]
    free_penetration_ok = abs(free_prod["min_dist_m"]) <= MAX_ALLOWED_PENETRATION_M if free_prod["min_dist_m"] is not None else None
    free_cor_ok = free_prod["cor_approx_1d"] is not None and COR_ACCEPTABLE_RANGE[0] <= free_prod["cor_approx_1d"] <= COR_ACCEPTABLE_RANGE[1]
    free_momentum_ok = free_prod["momentum_change_fraction"] is not None and free_prod["momentum_change_fraction"] <= MOMENTUM_CONSERVATION_TOL_FRACTION
    free_energy_residual_frac = (free_prod["ke1_j"] - free_prod["ke0_j"]) / free_prod["ke0_j"]

    result["free_bat"] = {
        "by_dt": free_by_dt,
        "dt_convergence": free_convergence,
        "production_dt_checks": {
            "penetration_ok": free_penetration_ok,
            "cor_ok": free_cor_ok,
            "momentum_conservation_ok": free_momentum_ok,
            "ke_change_fraction": free_energy_residual_frac,
        },
    }
    print(f"  PRODUCTION-DT CHECKS: penetration_ok={free_penetration_ok} cor_ok={free_cor_ok} momentum_ok={free_momentum_ok}")
    print(f"  DT CONVERGENCE: {free_convergence}")

    out_path = OUT_DIR / "VM01-P1-contact-isolated.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

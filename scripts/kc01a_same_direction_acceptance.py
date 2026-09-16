"""KC-01a same-direction acceptance validation (user follow-up to
docs/records/KC-01a-VALIDATION.md A8): applies the SAME A3(settle)/
A4(energy)/A5(timing-window) methodology already used on the original 4
conditions to the frozen `same_direction_staggered` condition found by
scripts/kc01a_same_direction_search.py, PLUS three new checks the user
asked for this round:

- Contact penetration/force/impulse per dt, separating whether the number
  itself is dt-CONVERGED from whether it is PHYSICALLY reasonable (it is
  neither modified nor excused here -- both questions are answered
  independently and both are reported even if the answer is "still
  unvalidated", matching how envs/assets/baseball_park_kc01a.xml's own
  ball_geom comment already describes this contact model).
- A corrected energy-integration framing: envs/assets/baseball_park_kc01a.xml
  sets integrator="RK4" (mujoco.mjtIntegrator.mjINT_RK4), NOT the
  semi-implicit Euler previously assumed when writing up the A4/A7 residual
  convergence order. This script separates STATE integration error (how
  accurately MuJoCo's own RK4 step advances qpos/qvel -- measured directly
  by comparing the state trajectory itself across dt, already close to
  machine precision per scripts/kc01a_noball_dt_isolation.py) from WORK
  quadrature error (this analysis script's own after-the-fact numerical
  approximation of integral(F . v dt) via a per-substep Riemann sum, which
  is a SEPARATE discretization this script introduces and is only
  first-order accurate regardless of what order the underlying state
  integrator is) -- and empirically tests the hypothesis that the
  previously observed order~1 residual convergence comes from the WORK
  quadrature, not from RK4's own state-integration order, by recomputing
  the same residual with a trapezoidal (2nd-order) work quadrature instead
  of the original right-Riemann-sum one and checking whether the
  convergence order goes up.
- Whether torso/swing actually co-rotate (same sign) during acceleration,
  when the deceleration phase starts, and whether torso comes to rest
  because of the controller's own brake or because it hits its own joint
  limit (docs/design/KC-01a-DIRECTION-CONTRACT.md's own +-0.6rad range).

gear/material/reward are NOT touched anywhere in this file.
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np
from kc01a_constraint_decomposition import _qfrc_by_type
from kc01a_settle_diagnostics import MIN_CONTINUATION_S, _axis_history_to_settle

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
SEARCH_RESULT_PATH = OUT_DIR / "KC-01a-same-direction-search.json"

GRAVITY = 9.81
SUBSYSTEM_BODIES = ["torso_body", "bat_body", "bat_tilt_body"]


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


def _make_controller(cfg: dict) -> TorsoBatController:
    return TorsoBatController(
        cfg["controller_mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
    )


# ---------------------------------------------------------------------------
# 1. Settle (A3-equivalent)
# ---------------------------------------------------------------------------
def run_settle(cfg: dict) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = _make_controller(cfg)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        history: dict[str, list] = {"torso": [], "swing": []}

        def record():
            history["torso"].append(
                (float(env.data.time), float(env.data.qpos[env.torso_qpos_adr]), float(env.data.qvel[env.torso_qvel_adr]), controller._torso_axis.state)
            )
            history["swing"].append(
                (float(env.data.time), float(env.data.qpos[env.swing_qpos_adr]), float(env.data.qvel[env.swing_qvel_adr]), controller._swing_axis.state)
            )

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

        settle = {axis: _axis_history_to_settle(history[axis]) for axis in ("torso", "swing")}
        return {"outcome": outcome, "settle": settle, "continuation_final_time_s": float(env.data.time)}
    finally:
        env.close()


# ---------------------------------------------------------------------------
# 2. Energy (A4/A7-equivalent), with RK4-correct framing + quadrature-order test
# ---------------------------------------------------------------------------
def _subsystem_ke(env) -> float:
    nv = env.model.nv
    m_full = np.zeros((nv, nv))
    mujoco.mj_fullM(env.model, env.data, m_full)
    qvel3 = env.data.qvel[:3]
    return float(0.5 * qvel3 @ m_full[:3, :3] @ qvel3)


def _subsystem_pe(env, body_ids: list[int]) -> float:
    return float(sum(env.model.body_mass[bid] * GRAVITY * env.data.xipos[bid][2] for bid in body_ids))


def run_noball_energy(cfg: dict, dt: float, frame_skip: int) -> dict:
    """Right-Riemann-sum work quadrature (same as scripts/
    kc01a_energy_validation.py / kc01a_constraint_decomposition.py) PLUS a
    trapezoidal quadrature computed in the SAME run (both read off the same
    trajectory, so this is a direct apples-to-apples order comparison, not
    two separate stochastic runs)."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    control_dt = env.model.opt.timestep * env.frame_skip
    env.model.opt.timestep = dt
    env.frame_skip = frame_skip
    assert abs(dt * frame_skip - control_dt) < 1e-12
    try:
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0
        body_ids = [mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_BODY, n) for n in SUBSYSTEM_BODIES]
        controller = _make_controller(cfg)
        env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        ke0 = _subsystem_ke(env)
        pe0 = _subsystem_pe(env, body_ids)
        w_actuator_rect = w_damping_rect = w_limit_rect = w_contact_rect = 0.0
        w_actuator_trap = w_damping_trap = 0.0

        # "Start" values for the trapezoidal rule = the END-of-previous-
        # substep values (already consistent post mj_forward), seeded here
        # from the state right after reset.
        prev_qfrc_act = env.data.qfrc_actuator[:3].copy()
        prev_qfrc_pass = env.data.qfrc_passive[:3].copy()
        prev_qvel = env.data.qvel[:3].copy()

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
                qvel3 = env.data.qvel[:3].copy()
                qfrc_act = env.data.qfrc_actuator[:3].copy()
                qfrc_pass = env.data.qfrc_passive[:3].copy()
                by_type = _qfrc_by_type(env, dof_slice=slice(0, 3))
                for i in range(3):
                    w_actuator_rect += float(qfrc_act[i] * qvel3[i]) * dt
                    w_damping_rect += float(qfrc_pass[i] * qvel3[i]) * dt
                    w_limit_rect += float(by_type["limit_joint"][i] * qvel3[i]) * dt
                    w_contact_rect += float(by_type["contact"][i] * qvel3[i]) * dt
                    # Trapezoidal: average the (force, vel) PRODUCT at the
                    # substep's start and end -- a standard 2nd-order
                    # quadrature of a product of two time-varying signals
                    # (not exact, since force and velocity both vary within
                    # the substep, but strictly higher-order than the
                    # right-Riemann sum above for the same data).
                    w_actuator_trap += 0.5 * float(prev_qfrc_act[i] * prev_qvel[i] + qfrc_act[i] * qvel3[i]) * dt
                    w_damping_trap += 0.5 * float(prev_qfrc_pass[i] * prev_qvel[i] + qfrc_pass[i] * qvel3[i]) * dt
                prev_qfrc_act, prev_qfrc_pass, prev_qvel = qfrc_act, qfrc_pass, qvel3

        ke1 = _subsystem_ke(env)
        pe1 = _subsystem_pe(env, body_ids)
        delta_e = (ke1 + pe1) - (ke0 + pe0)
        predicted_rect = w_actuator_rect + w_damping_rect + w_limit_rect + w_contact_rect
        predicted_trap = w_actuator_trap + w_damping_trap + w_limit_rect + w_contact_rect  # constraint terms reuse rect (small, not the focus)
        return {
            "dt": dt,
            "delta_ke_plus_pe": delta_e,
            "rect": {"w_actuator": w_actuator_rect, "w_damping": w_damping_rect, "w_limit": w_limit_rect, "w_contact": w_contact_rect, "residual": delta_e - predicted_rect},
            "trap": {"w_actuator": w_actuator_trap, "w_damping": w_damping_trap, "residual": delta_e - predicted_trap},
        }
    finally:
        env.close()


def _order(residuals: list[float]) -> list[float]:
    out = []
    for i in range(len(residuals) - 1):
        a, b = abs(residuals[i]), abs(residuals[i + 1])
        if a > 1e-9 and b > 1e-9:
            out.append(float(np.log2(a / b)))
    return out


# ---------------------------------------------------------------------------
# 3. Timing window (A5-equivalent)
# ---------------------------------------------------------------------------
def run_timing_offset(cfg: dict, offset_s: float) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        c2 = dict(cfg)
        c2["torso_ct"] = cfg["torso_ct"] + offset_s
        c2["swing_ct"] = cfg["swing_ct"] + offset_s
        controller = _make_controller(c2)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        trigger_step = None
        step_i = 0
        info = {}
        while True:
            action = controller.act(obs)
            if trigger_step is None and (controller._torso_triggered or controller._swing_triggered):
                trigger_step = step_i
            obs, _, terminated, truncated, info = env.step(action)
            step_i += 1
            if terminated or truncated:
                break
        return {"offset_ms": offset_s * 1000, "scoring_valid": info["scoring_valid"], "batting_score": info["batting_score"], "trigger_control_step": trigger_step}
    finally:
        env.close()


# ---------------------------------------------------------------------------
# 4. Contact penetration/force/impulse per dt + geom-pair identification
# ---------------------------------------------------------------------------
class DetailedContactLog:
    def __init__(self) -> None:
        self.min_dist = None
        self.min_dist_geoms: tuple[str, str] | None = None
        self.max_normal_force_n = 0.0
        self.impulse_ns = np.zeros(3)
        self.n_active_substeps = 0
        self.first_active_t: float | None = None
        self.last_active_t: float | None = None

    def __call__(self, env, bat_hit, bat_vel, ball_vel):
        if not bat_hit:
            return
        self.n_active_substeps += 1
        now = float(env.data.time)
        if self.first_active_t is None:
            self.first_active_t = now
        self.last_active_t = now
        dt = env.model.opt.timestep
        for idx in range(env.data.ncon):
            c = env.data.contact[idx]
            pair = {c.geom1, c.geom2}
            if env.ball_geom_id in pair and env.bat_geom_id in pair:
                if self.min_dist is None or float(c.dist) < self.min_dist:
                    self.min_dist = float(c.dist)
                    g1 = mujoco.mj_id2name(env.model, mujoco.mjtObj.mjOBJ_GEOM, c.geom1)
                    g2 = mujoco.mj_id2name(env.model, mujoco.mjtObj.mjOBJ_GEOM, c.geom2)
                    self.min_dist_geoms = (g1, g2)
                force6 = np.zeros(6)
                mujoco.mj_contactForce(env.model, env.data, idx, force6)
                normal_force = float(force6[0])  # contact-frame force: index 0 is the normal component
                self.max_normal_force_n = max(self.max_normal_force_n, abs(normal_force))
                normal_world = np.array(c.frame[:3])
                self.impulse_ns += normal_world * normal_force * dt


def run_contact_detail(cfg: dict, dt: float, frame_skip: int) -> dict:
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
            "impulse_ns": log.impulse_ns.tolist(),
            "impulse_magnitude_ns": float(np.linalg.norm(log.impulse_ns)),
            "contact_duration_s": (None if log.first_active_t is None else log.last_active_t - log.first_active_t),
            "n_active_substeps": log.n_active_substeps,
        }
    finally:
        env.close()


# ---------------------------------------------------------------------------
# 5. Co-rotation window + joint-limit-stop check
# ---------------------------------------------------------------------------
def analyze_corotation_and_limit(cfg: dict) -> dict:
    timeline_path = OUT_DIR / "KC-01a-timelines" / "same_direction_staggered.json"
    tl = json.loads(timeline_path.read_text())
    corotate_steps = sum(1 for r in tl if r["torso_vel"] * r["swing_vel"] > 0 and abs(r["torso_vel"]) > 0.05 and abs(r["swing_vel"]) > 0.05)
    total_moving_steps = sum(1 for r in tl if abs(r["torso_vel"]) > 0.05 or abs(r["swing_vel"]) > 0.05)
    torso_range = None
    env = BaseballKC01aEnv()
    torso_range = list(env.model.jnt_range[env.torso_joint_id])
    env.close()
    max_abs_torso_angle = max(abs(r["torso_angle"]) for r in tl)
    hit_torso_limit = max_abs_torso_angle >= abs(torso_range[1]) - 1e-3
    return {
        "corotating_control_steps": corotate_steps,
        "either_moving_control_steps": total_moving_steps,
        "corotation_fraction_of_moving_time": (corotate_steps / total_moving_steps) if total_moving_steps else None,
        "max_abs_torso_angle_rad": max_abs_torso_angle,
        "torso_range_rad": torso_range,
        "torso_hit_own_joint_limit": hit_torso_limit,
    }


def main() -> None:
    cfg = _load_config()
    print(f"Frozen config: {cfg}")
    result: dict = {"config": cfg}

    print("\n=== 1. settle ===")
    settle = run_settle(cfg)
    result["settle"] = settle
    print(json.dumps(settle["settle"], default=str, indent=2))

    print("\n=== 2. energy (RK4-correct framing, rect vs trapezoidal quadrature) ===")
    per_dt = {}
    for dt, fs in ((0.00025, 20), (0.000125, 40), (0.0000625, 80)):
        r = run_noball_energy(cfg, dt, fs)
        per_dt[str(dt)] = r
        print(f"  dt={dt}: rect_residual={r['rect']['residual']:.4f}J trap_residual={r['trap']['residual']:.4f}J")
    rect_residuals = [per_dt[str(dt)]["rect"]["residual"] for dt, _ in ((0.00025, 20), (0.000125, 40), (0.0000625, 80))]
    trap_residuals = [per_dt[str(dt)]["trap"]["residual"] for dt, _ in ((0.00025, 20), (0.000125, 40), (0.0000625, 80))]
    rect_order = _order(rect_residuals)
    trap_order = _order(trap_residuals)
    print(f"  rect-quadrature residual convergence order: {rect_order}")
    print(f"  trapezoidal-quadrature residual convergence order: {trap_order}")
    result["energy"] = {"per_dt": per_dt, "rect_order_estimates": rect_order, "trap_order_estimates": trap_order}

    print("\n=== 3. timing window (+-20ms, 1ms steps) ===")
    timing = [run_timing_offset(cfg, off_ms / 1000.0) for off_ms in range(-20, 21, 1)]
    n_valid = sum(1 for t in timing if t["scoring_valid"])
    print(f"  {n_valid}/{len(timing)} valid")
    result["timing_window"] = {"offsets": timing, "n_valid": n_valid, "n_total": len(timing)}

    print("\n=== 4. contact penetration/force/impulse per dt ===")
    contact_detail = {}
    for dt, fs in ((0.00025, 20), (0.000125, 40), (0.0000625, 80)):
        r = run_contact_detail(cfg, dt, fs)
        contact_detail[str(dt)] = r
        print(f"  dt={dt}: min_dist={r['min_dist_m']:.5f}m geoms={r['min_dist_geoms']} max_normal_force={r['max_normal_force_n']:.1f}N impulse={r['impulse_magnitude_ns']:.4f}N.s duration={r['contact_duration_s']}")
    result["contact_detail"] = contact_detail

    print("\n=== 5. co-rotation window + joint-limit-stop ===")
    corotation = analyze_corotation_and_limit(cfg)
    result["corotation_and_limit"] = corotation
    print(json.dumps(corotation, indent=2, default=str))

    out_path = OUT_DIR / "KC-01a-same-direction-acceptance.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

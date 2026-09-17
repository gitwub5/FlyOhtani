"""VM-01 P2 (user follow-up to docs/records/VM01-P1-CONTACT.md): separates
the cause of P1's negative fixed-plate restitution, using
envs/assets/contact_validation_p2.xml (thin_plate = P1's original geometry
reproduced for direct comparison, thick_block, flat_plane, free_bat). P1's
own asset/script/results are left untouched.

Hypothesis under test: the ball (radius 0.0366m) is FATTER than P1's plate
is thick (0.02m total). A box-vs-sphere contact's normal comes from the
nearest point on the box surface; once the ball's center passes closer to
the box's FAR face than its near face, that nearest point -- and the
contact normal -- can flip direction, partially cancelling the
deceleration built up on approach. A target the ball cannot geometrically
transit (thick_block) or that has no far face at all (flat_plane, a true
half-space) should not show this, if the hypothesis is right.

Per the user's explicit instruction, a good OBLIQUE result does not excuse
a bad FRONTAL result -- both are run and reported, and neither is used to
wave away the other.
"""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np

ASSET_PATH = Path(__file__).resolve().parent.parent / "envs" / "assets" / "contact_validation_p2.xml"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

BALL_RADIUS_M = 0.0366
APPROACH_SPEED_M_S = 35.0
SIM_WINDOW_S = 0.10
DT_CANDIDATES = [0.00025, 0.0000625, 0.0000078125]

# Same acceptance band as docs/design/CONTACT-VALIDATION-P1-SPEC.md (reused,
# not re-derived) -- ANY target failing this is reported as failing, oblique
# success does not retroactively pass the frontal case.
MAX_ALLOWED_PENETRATION_M = 0.30 * min(BALL_RADIUS_M, 0.025)
COR_ACCEPTABLE_RANGE = (0.3, 0.7)

TARGET_START_X = {"thin_plate": 3.8, "thick_block": 6.5, "flat_plane": 9.7}
TARGET_ALL_GEOMS = ["thin_plate", "thick_block", "flat_plane", "free_bat"]


class SegmentedContactRecorder:
    """Unlike scripts/p1_contact_isolated.py's ContactRecorder (first/last
    contact time only), this tracks every SEPARATE contiguous contact
    segment -- more than one segment within a single approach is itself
    direct evidence of a "push back, then push forward again" event (the
    normal-flip hypothesis), not something inferred indirectly from the
    net restitution number alone."""

    def __init__(self, ball_geom_id: int, target_geom_id: int) -> None:
        self.ball_geom_id = ball_geom_id
        self.target_geom_id = target_geom_id
        self.segments: list[list[float]] = []  # [[start_t, end_t], ...]
        self._active_prev = False
        self.min_dist: float | None = None
        self.normal_history: list[tuple[float, float]] = []  # (t, normal_x_world) while active

    def record(self, model: mujoco.MjModel, data: mujoco.MjData) -> bool:
        active = False
        for idx in range(data.ncon):
            c = data.contact[idx]
            pair = {c.geom1, c.geom2}
            if self.ball_geom_id in pair and self.target_geom_id in pair:
                active = True
                if self.min_dist is None or float(c.dist) < self.min_dist:
                    self.min_dist = float(c.dist)
                normal_x = float(c.frame[0])
                self.normal_history.append((float(data.time), normal_x))
        t = float(data.time)
        if active and not self._active_prev:
            self.segments.append([t, t])
        elif active:
            self.segments[-1][1] = t
        self._active_prev = active
        return active


def _make_model_data(dt: float):
    model = mujoco.MjModel.from_xml_path(str(ASSET_PATH))
    model.opt.timestep = dt
    data = mujoco.MjData(model)
    return model, data


def _disable_all_except(model: mujoco.MjModel, keep: str) -> None:
    for name in TARGET_ALL_GEOMS:
        if name == keep:
            continue
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        model.geom_contype[gid] = 0
        model.geom_conaffinity[gid] = 0


def run_frontal(target_name: str, dt: float, log_trajectory: bool = False) -> dict:
    model, data = _make_model_data(dt)
    _disable_all_except(model, target_name)
    ball_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
    target_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, target_name)
    ball_qpos_adr = model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]
    ball_qvel_adr = model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]

    start_x = TARGET_START_X[target_name]
    data.qpos[ball_qpos_adr : ball_qpos_adr + 3] = [start_x, 0, 1]
    data.qpos[ball_qpos_adr + 3 : ball_qpos_adr + 7] = [1, 0, 0, 0]
    data.qvel[ball_qvel_adr : ball_qvel_adr + 3] = [APPROACH_SPEED_M_S, 0, 0]
    mujoco.mj_forward(model, data)

    recorder = SegmentedContactRecorder(ball_geom_id, target_geom_id)
    v_in = float(data.qvel[ball_qvel_adr])
    n_substeps = round(SIM_WINDOW_S / dt)
    trajectory = [] if log_trajectory else None
    v_out = v_in
    max_x = data.qpos[ball_qpos_adr]
    for _ in range(n_substeps):
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        active = recorder.record(model, data)
        ball_x = float(data.qpos[ball_qpos_adr])
        max_x = max(max_x, ball_x)
        v_out = float(data.qvel[ball_qvel_adr])
        if trajectory is not None:
            trajectory.append({"t": float(data.time), "ball_x": ball_x, "contact_active": active})

    cor = -v_out / v_in if v_in != 0 else None
    normal_signs = sorted({np.sign(round(nx, 6)) for _t, nx in recorder.normal_history if abs(nx) > 1e-6})

    result = {
        "target": target_name,
        "dt": dt,
        "v_in_m_s": v_in,
        "v_out_m_s": v_out,
        "cor": cor,
        "min_dist_m": recorder.min_dist,
        "n_contact_segments": len(recorder.segments),
        "segments_s": recorder.segments,
        "contact_normal_x_signs_seen": normal_signs,
        "normal_sign_flip_observed": len(normal_signs) > 1,
        "penetration_ok": (abs(recorder.min_dist) <= MAX_ALLOWED_PENETRATION_M) if recorder.min_dist is not None else None,
        "cor_ok": (cor is not None and COR_ACCEPTABLE_RANGE[0] <= cor <= COR_ACCEPTABLE_RANGE[1]),
    }
    if trajectory is not None:
        result["trajectory"] = trajectory
    return result


def run_oblique_free_bat(dt: float, angle_deg: float) -> dict:
    """Ball approaches the free bat's SIDE with a velocity component along
    the bat's own long axis (tangential) in addition to the radial
    (normal) component -- a glancing hit, unlike P1's purely radial
    approach. COR is computed along the actual contact NORMAL direction at
    peak penetration (not assumed to be a fixed world axis), the
    physically correct treatment for an oblique impact."""
    model, data = _make_model_data(dt)
    _disable_all_except(model, "free_bat")
    ball_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "ball_geom")
    bat_geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "free_bat")
    ball_qpos_adr = model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]
    ball_qvel_adr = model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")]
    bat_qpos_adr = model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "free_bat_joint")]
    bat_qvel_adr = model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "free_bat_joint")]

    angle = np.radians(angle_deg)
    v_normal = APPROACH_SPEED_M_S * np.cos(angle)
    v_tangent = APPROACH_SPEED_M_S * np.sin(angle)
    # Bat body at (-5,0,1), long axis world X. Ball approaches along -Y
    # (normal, toward the bat's side) with a +X (tangential, along the
    # bat's own length) component, starting near the bat's center.
    data.qpos[ball_qpos_adr : ball_qpos_adr + 3] = [-5 - v_tangent / v_normal * 1.2, 1.2, 1]
    data.qpos[ball_qpos_adr + 3 : ball_qpos_adr + 7] = [1, 0, 0, 0]
    data.qvel[ball_qvel_adr : ball_qvel_adr + 3] = [v_tangent, -v_normal, 0]
    data.qpos[bat_qpos_adr + 3 : bat_qpos_adr + 7] = [1, 0, 0, 0]
    mujoco.mj_forward(model, data)

    recorder = SegmentedContactRecorder(ball_geom_id, bat_geom_id)
    n_substeps = round(SIM_WINDOW_S / dt)
    peak_penetration_normal: np.ndarray | None = None
    for _ in range(n_substeps):
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        recorder.record(model, data)
        for idx in range(data.ncon):
            c = data.contact[idx]
            if {c.geom1, c.geom2} == {ball_geom_id, bat_geom_id} and (recorder.min_dist is None or float(c.dist) <= recorder.min_dist):
                peak_penetration_normal = np.array(c.frame[:3])

    ball_v_out = data.qvel[ball_qvel_adr : ball_qvel_adr + 3].copy()
    bat_v_out = data.qvel[bat_qvel_adr : bat_qvel_adr + 3].copy()
    rel_v_out = ball_v_out - bat_v_out
    rel_v_in = np.array([v_tangent, -v_normal, 0.0])

    if peak_penetration_normal is not None:
        n = peak_penetration_normal / (np.linalg.norm(peak_penetration_normal) + 1e-12)
        v_in_normal = float(np.dot(rel_v_in, n))
        v_out_normal = float(np.dot(rel_v_out, n))
        cor_normal = abs(v_out_normal) / abs(v_in_normal) if v_in_normal != 0 else None
    else:
        cor_normal = None
        n = None

    return {
        "angle_deg": angle_deg,
        "dt": dt,
        "min_dist_m": recorder.min_dist,
        "n_contact_segments": len(recorder.segments),
        "contact_normal_at_peak": n.tolist() if n is not None else None,
        "cor_along_normal": cor_normal,
        "cor_ok": (cor_normal is not None and COR_ACCEPTABLE_RANGE[0] <= cor_normal <= COR_ACCEPTABLE_RANGE[1]),
        "penetration_ok": (abs(recorder.min_dist) <= MAX_ALLOWED_PENETRATION_M) if recorder.min_dist is not None else None,
        "ball_v_out": ball_v_out.tolist(),
        "bat_v_out": bat_v_out.tolist(),
    }


def main() -> None:
    result: dict = {}

    print("=== A. tunneling check (thin_plate, trajectory logged) ===")
    traj_run = run_frontal("thin_plate", DT_CANDIDATES[0], log_trajectory=True)
    ball_end_x = traj_run["trajectory"][-1]["ball_x"]
    plate_front_x, plate_back_x = 4.99, 5.01
    passed_through = ball_end_x > plate_back_x
    print(f"  ball ends at x={ball_end_x:.4f} (plate spans [{plate_front_x},{plate_back_x}]) -> passed through far face: {passed_through}")
    print(f"  contact segments: {traj_run['n_contact_segments']} {traj_run['segments_s']}")
    print(f"  contact normal x-signs observed during contact: {traj_run['contact_normal_x_signs_seen']} (more than one sign = normal flip)")
    result["tunneling_check"] = {
        "ball_end_x": ball_end_x,
        "plate_bounds_x": [plate_front_x, plate_back_x],
        "passed_through_far_face": bool(passed_through),
        "n_contact_segments": traj_run["n_contact_segments"],
        "segments_s": traj_run["segments_s"],
        "normal_sign_flip_observed": traj_run["normal_sign_flip_observed"],
        "contact_normal_x_signs_seen": traj_run["contact_normal_x_signs_seen"],
    }

    print("\n=== B. thin_plate vs thick_block vs flat_plane (frontal, same material) ===")
    geometry_comparison = {}
    for target in ["thin_plate", "thick_block", "flat_plane"]:
        by_dt = {}
        for dt in DT_CANDIDATES:
            r = run_frontal(target, dt)
            by_dt[str(dt)] = r
            print(f"  {target} dt={dt}: cor={r['cor']:.4f} min_dist={r['min_dist_m']:.5f}m segments={r['n_contact_segments']} normal_flip={r['normal_sign_flip_observed']} cor_ok={r['cor_ok']} penetration_ok={r['penetration_ok']}")
        geometry_comparison[target] = by_dt
    result["geometry_comparison"] = geometry_comparison

    print("\n=== C. oblique free-bat impact (does NOT excuse the frontal failures above) ===")
    oblique_results = {}
    for angle_deg in [0, 20, 35]:
        r = run_oblique_free_bat(DT_CANDIDATES[0], angle_deg)
        oblique_results[str(angle_deg)] = r
        print(f"  angle={angle_deg}deg: cor_along_normal={r['cor_along_normal']} min_dist={r['min_dist_m']:.5f}m cor_ok={r['cor_ok']} penetration_ok={r['penetration_ok']}")
    result["oblique_free_bat"] = oblique_results
    result["oblique_does_not_excuse_frontal"] = (
        "A passing oblique result here does not change the frontal thin_plate/thick_block/flat_plane "
        "verdicts in section B -- both are reported, neither is dropped in favor of the other."
    )

    out_path = OUT_DIR / "VM01-P2-contact-diagnosis.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

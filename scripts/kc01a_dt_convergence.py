"""KC-01a-validation A2 (docs/tasks/KC-01a-VALIDATION-AND-VISION.md, TOP
PRIORITY): timestep convergence for all 4 conditions, at
physics_dt in {0.00025, 0.000125, 0.0000625}s with control_dt=0.005s fixed
(frame_skip scaled 20/40/80 to match).

Two independent checks per condition per dt:
  1. REPLAY: the exact per-control-step action sequence recorded from a
     baseline (dt=0.00025s) run of the real controller, replayed via
     zero-order hold -- isolates pure contact-physics/integration
     sensitivity to dt from any control-feedback effect.
  2. INDEPENDENT: the real controller re-run fresh at each dt -- includes
     state-feedback/branching sensitivity (the controller sees slightly
     different angle/velocity readings at finer dt and could in principle
     make different accelerate/brake transitions).

Acceptance thresholds are fixed here, BEFORE running anything below, and
are not loosened after seeing results (docs/tasks/
KC-01a-VALIDATION-AND-VISION.md A2):
  - at the two finest dt (0.000125s, 0.0000625s): identical end_reason and
    scoring_valid for a given condition/check
  - |common contact/separation time diff| <= 0.5ms
  - |exit velocity vector diff| <= max(0.1 m/s, 2% of the finer dt's speed)
  - |landing XY diff| <= max(0.05m, 2% of the finer dt's carry distance)

Renamed conditions (docs/tasks/KC-01a-VALIDATION-AND-VISION.md A1 --
old name -> new name, both recorded so old evidence stays traceable):
  arm_only      -> arm_swing_with_torso_hold
  torso_only    -> torso_swing_with_arm_hold
  simultaneous  -> simultaneous_swing_and_torso
  staggered     -> staggered_swing_and_torso
tilt is actively P-held (never driven to a new target) in ALL FOUR
conditions; not called out per-name since it is uniform.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

CONDITIONS = {
    "arm_swing_with_torso_hold": {
        "old_name": "arm_only",
        "controller_mode": "arm_only",  # controllers/baseball_kc01a.py's internal mode string, unchanged
        "torso_target": 0.0,
        "swing_target": -1.298,
        "torso_ct": 999.0,
        "swing_ct": 0.09425316355759385,
    },
    "torso_swing_with_arm_hold": {
        "old_name": "torso_only",
        "controller_mode": "torso_only",
        "torso_target": 0.496,
        "swing_target": -1.96,
        "torso_ct": 0.360,
        "swing_ct": 999.0,
    },
    "simultaneous_swing_and_torso": {
        "old_name": "simultaneous",
        "controller_mode": "simultaneous",
        "torso_target": -0.4,
        "swing_target": -0.726,
        "torso_ct": 0.096,
        "swing_ct": 0.096,
    },
    "staggered_swing_and_torso": {
        "old_name": "staggered",
        "controller_mode": "staggered",
        "torso_target": -0.4,
        "swing_target": -0.726,
        "torso_ct": 0.242,
        "swing_ct": 0.122,
    },
}

BASE_DT = 0.00025
DT_CANDIDATES = [0.00025, 0.000125, 0.0000625]
FRAME_SKIP_AT_BASE = 20  # BaseballKC01aEnv's default; control_dt = 0.005s

# --- Pre-registered acceptance thresholds (fixed before any run below) ---
SEPARATION_TIME_TOL_S = 0.0005
LANDING_XY_ABS_TOL_M = 0.05
LANDING_XY_REL_TOL = 0.02
EXIT_VEL_ABS_TOL_M_S = 0.1
EXIT_VEL_REL_TOL = 0.02


class ContactLog:
    """Per-substep_callback accumulator: min contact `dist` (most negative
    = deepest penetration) and the contact normal/relative speed observed
    at that instant, over the FIRST bat-ball contact window only (matches
    what info's own first_contact_time_s/exit_time_s already bracket)."""

    def __init__(self) -> None:
        self.first_window_active = False
        self.first_window_done = False
        self.min_dist = None
        self.normal_at_min_dist = None
        self.contact_substep_count = 0

    def __call__(self, env, bat_hit, bat_vel, ball_vel):
        if self.first_window_done:
            return
        if bat_hit:
            self.first_window_active = True
            self.contact_substep_count += 1
            for idx in range(env.data.ncon):
                c = env.data.contact[idx]
                pair = {c.geom1, c.geom2}
                is_ball_bat = env.ball_geom_id in pair and env.bat_geom_id in pair
                if is_ball_bat and (self.min_dist is None or float(c.dist) < self.min_dist):
                    self.min_dist = float(c.dist)
                    self.normal_at_min_dist = np.array(c.frame[:3], dtype=float).tolist()
        elif self.first_window_active:
            self.first_window_done = True


def _make_env_at_dt(dt: float, frame_skip: int) -> BaseballKC01aEnv:
    """Constructs with the DEFAULT (base) frame_skip/timestep so __init__'s
    own max_pitch_steps = pitch_timeout_s / (timestep * frame_skip) is
    computed correctly at construction time, THEN overrides both timestep
    and frame_skip to the target dt (control_dt = timestep * frame_skip is
    unchanged by construction, only how finely it's resolved) -- avoids a
    mismatched-pair bug from passing a scaled frame_skip to the constructor
    before timestep is overridden."""
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    control_dt = env.model.opt.timestep * env.frame_skip
    env.model.opt.timestep = dt
    env.frame_skip = frame_skip
    assert abs(dt * frame_skip - control_dt) < 1e-12, "control_dt must stay fixed across dt candidates"
    return env


def run_recording(cfg: dict, dt: float, frame_skip: int) -> tuple[dict, list, ContactLog]:
    """INDEPENDENT check: real controller, fresh at this dt. Returns
    (info, recorded_actions, contact_log)."""
    env = _make_env_at_dt(dt, frame_skip)
    try:
        controller = TorsoBatController(
            cfg["controller_mode"],
            0.0,
            -1.96,
            0.0,
            cfg["torso_target"],
            cfg["swing_target"],
            cfg["torso_ct"],
            cfg["swing_ct"],
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        log = ContactLog()
        actions = []
        info = {}
        while True:
            action = controller.act(obs)
            actions.append(action.tolist())
            obs, _, terminated, truncated, info = env.step(action, substep_callback=log)
            if terminated or truncated:
                break
        return info, actions, log
    finally:
        env.close()


def run_replay(actions: list, dt: float, frame_skip: int) -> tuple[dict, ContactLog]:
    """REPLAY check: zero-order hold of a FIXED action sequence, ignoring
    the controller/observations entirely. True zero-order hold means the
    LAST recorded action is held constant for as long as the episode keeps
    running past the recorded sequence's length -- at a finer dt the same
    real-world event (contact, separation, landing) can legitimately take
    a few more/fewer 5ms control steps to reach, so simply stopping once
    the recorded list is exhausted would truncate the episode before its
    own natural termination (observed: end_reason=None, i.e. "ran out of
    actions", not a real outcome) rather than actually replaying the
    command history. A safety cap (4x the recorded length) guards against
    a genuine non-termination bug elsewhere hanging this forever."""
    env = _make_env_at_dt(dt, frame_skip)
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        log = ContactLog()
        info = {}
        max_steps = max(len(actions) * 4, 200)
        for i in range(max_steps):
            action = actions[i] if i < len(actions) else actions[-1]
            _obs, _, terminated, truncated, info = env.step(
                np.array(action, dtype=np.float32), substep_callback=log
            )
            if terminated or truncated:
                break
        return info, log
    finally:
        env.close()


def summarize(info: dict, log: ContactLog) -> dict:
    return {
        "end_reason": info["end_reason"],
        "scoring_valid": info["scoring_valid"],
        "status": info["status"],
        "first_contact_time_s": info["first_contact_time_s"],
        "exit_time_s": info["exit_time_s"],
        "recontact_count": info["recontact_count"],
        "prolonged_contact": info["prolonged_contact"],
        "bat_contact_vx": info["bat_contact_vx"],
        "bat_contact_velocity": info["bat_contact_velocity"],
        "exit_velocity_xyz": info["exit_velocity_xyz"],
        "exit_speed": info["exit_speed"],
        "first_landing_xyz": info["first_landing_xyz"],
        "carry_distance_m": info["carry_distance_m"],
        "batting_score": info["batting_score"],
        "contact_min_dist_m": log.min_dist,
        "contact_normal_at_min_dist": log.normal_at_min_dist,
        "contact_substep_count": log.contact_substep_count,
        "contact_duration_from_substeps_s": (
            None
            if info["exit_time_s"] is None or info["first_contact_time_s"] is None
            else info["exit_time_s"] - info["first_contact_time_s"]
        ),
    }


def _vec_diff(a, b) -> float | None:
    if a is None or b is None:
        return None
    return float(np.linalg.norm(np.array(a) - np.array(b)))


def check_pair(fine: dict, finest: dict) -> dict:
    """Compares the two finest-dt summaries for one condition/check
    against the pre-registered thresholds."""
    out = {}
    out["same_end_reason"] = fine["end_reason"] == finest["end_reason"]
    out["same_scoring_valid"] = fine["scoring_valid"] == finest["scoring_valid"]

    if fine["first_contact_time_s"] is not None and finest["first_contact_time_s"] is not None:
        d = abs(fine["first_contact_time_s"] - finest["first_contact_time_s"])
        out["first_contact_time_diff_s"] = d
        out["first_contact_time_ok"] = d <= SEPARATION_TIME_TOL_S
    else:
        out["first_contact_time_diff_s"] = None
        out["first_contact_time_ok"] = fine["first_contact_time_s"] == finest["first_contact_time_s"]

    if fine["exit_time_s"] is not None and finest["exit_time_s"] is not None:
        d = abs(fine["exit_time_s"] - finest["exit_time_s"])
        out["separation_time_diff_s"] = d
        out["separation_time_ok"] = d <= SEPARATION_TIME_TOL_S
    else:
        out["separation_time_diff_s"] = None
        out["separation_time_ok"] = fine["exit_time_s"] == finest["exit_time_s"]

    ev_diff = _vec_diff(fine["exit_velocity_xyz"], finest["exit_velocity_xyz"])
    out["exit_velocity_diff_m_s"] = ev_diff
    if ev_diff is not None:
        ref_speed = finest["exit_speed"] or 0.0
        tol = max(EXIT_VEL_ABS_TOL_M_S, EXIT_VEL_REL_TOL * ref_speed)
        out["exit_velocity_ok"] = ev_diff <= tol
    else:
        out["exit_velocity_ok"] = fine["exit_velocity_xyz"] == finest["exit_velocity_xyz"]

    if fine["first_landing_xyz"] is not None and finest["first_landing_xyz"] is not None:
        xy_diff = float(
            np.linalg.norm(np.array(fine["first_landing_xyz"][:2]) - np.array(finest["first_landing_xyz"][:2]))
        )
        out["landing_xy_diff_m"] = xy_diff
        ref_dist = finest["carry_distance_m"] or 0.0
        tol = max(LANDING_XY_ABS_TOL_M, LANDING_XY_REL_TOL * ref_dist)
        out["landing_xy_ok"] = xy_diff <= tol
    else:
        out["landing_xy_diff_m"] = None
        out["landing_xy_ok"] = fine["first_landing_xyz"] == finest["first_landing_xyz"]

    out["all_ok"] = all(
        out[k]
        for k in (
            "same_end_reason",
            "same_scoring_valid",
            "first_contact_time_ok",
            "separation_time_ok",
            "exit_velocity_ok",
            "landing_xy_ok",
        )
    )
    return out


def main() -> None:
    result = {"per_condition": {}}
    overall_pass = True

    for mode, cfg in CONDITIONS.items():
        print(f"\n=== {mode} (was {cfg['old_name']}) ===")
        cond_result = {"old_name": cfg["old_name"], "independent": {}, "replay": {}}

        # Baseline recording at BASE_DT for the replay action sequence.
        base_info, base_actions, base_log = run_recording(cfg, BASE_DT, FRAME_SKIP_AT_BASE)
        cond_result["independent"][str(BASE_DT)] = summarize(base_info, base_log)
        print(f"  independent dt={BASE_DT}: end_reason={base_info['end_reason']} valid={base_info['scoring_valid']} score={base_info['batting_score']}")

        for dt in DT_CANDIDATES[1:]:
            scale = round(BASE_DT / dt)
            frame_skip = FRAME_SKIP_AT_BASE * scale
            info_i, _, log_i = run_recording(cfg, dt, frame_skip)
            cond_result["independent"][str(dt)] = summarize(info_i, log_i)
            print(f"  independent dt={dt}: end_reason={info_i['end_reason']} valid={info_i['scoring_valid']} score={info_i['batting_score']}")

            info_r, log_r = run_replay(base_actions, dt, frame_skip)
            cond_result["replay"][str(dt)] = summarize(info_r, log_r)
            print(f"  replay      dt={dt}: end_reason={info_r['end_reason']} valid={info_r['scoring_valid']} score={info_r['batting_score']}")

        # Replay at BASE_DT is trivially the recording itself (same
        # actions, same dt) -- include for table completeness.
        cond_result["replay"][str(BASE_DT)] = summarize(base_info, base_log)

        finest, fine = str(DT_CANDIDATES[2]), str(DT_CANDIDATES[1])
        cond_result["acceptance"] = {
            "independent": check_pair(cond_result["independent"][fine], cond_result["independent"][finest]),
            "replay": check_pair(cond_result["replay"][fine], cond_result["replay"][finest]),
        }
        cond_pass = cond_result["acceptance"]["independent"]["all_ok"] and cond_result["acceptance"]["replay"]["all_ok"]
        cond_result["converged"] = cond_pass
        overall_pass = overall_pass and cond_pass
        print(f"  ACCEPTANCE: independent_ok={cond_result['acceptance']['independent']['all_ok']} replay_ok={cond_result['acceptance']['replay']['all_ok']}")

        result["per_condition"][mode] = cond_result

    result["overall_converged"] = overall_pass
    result["thresholds"] = {
        "separation_time_tol_s": SEPARATION_TIME_TOL_S,
        "landing_xy_abs_tol_m": LANDING_XY_ABS_TOL_M,
        "landing_xy_rel_tol": LANDING_XY_REL_TOL,
        "exit_vel_abs_tol_m_s": EXIT_VEL_ABS_TOL_M_S,
        "exit_vel_rel_tol": EXIT_VEL_REL_TOL,
        "dt_candidates": DT_CANDIDATES,
    }

    out_path = OUT_DIR / "KC-01a-dt-convergence.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nOVERALL CONVERGED: {overall_pass}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

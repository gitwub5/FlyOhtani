"""KC-01a same-direction condition (docs/design/KC-01a-DIRECTION-CONTRACT.md
section 4 item 6): applies the EXACT SAME pre-registered dt-convergence
methodology as docs/records/KC-01a-VALIDATION.md A2 (scripts/
kc01a_dt_convergence.py, imported directly -- same ContactLog, same
_make_env_at_dt, same run_recording/run_replay/check_pair, same thresholds)
to the new same-direction condition found by
scripts/kc01a_same_direction_search.py, instead of reimplementing the
methodology (risking silent drift between the two). Per the user's explicit
instruction, "협응 개선"(coordination improvement) is NOT concluded from the
production-dt score alone -- this script's own PASS/FAIL against the
existing thresholds is the gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import kc01a_dt_convergence as dtc

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

SEARCH_RESULT_PATH = OUT_DIR / "KC-01a-same-direction-search.json"


def main() -> None:
    search = json.loads(SEARCH_RESULT_PATH.read_text())
    trig = search["trigger_search"]
    if not trig.get("found"):
        raise RuntimeError("same-direction search found no valid trigger -- nothing to convergence-check")

    cfg = {
        "old_name": None,
        "controller_mode": "staggered",
        "torso_target": search["chosen_torso_target"],
        "swing_target": search["chosen_swing_target"],
        "torso_ct": trig["torso_crossing_time_s"],
        "swing_ct": trig["swing_crossing_time_s"],
    }
    mode = "same_direction_staggered"
    print(f"=== {mode} (torso_target={cfg['torso_target']}, swing_target={cfg['swing_target']:.4f}) ===")

    cond_result = {"config": cfg, "independent": {}, "replay": {}}
    base_info, base_actions, base_log = dtc.run_recording(cfg, dtc.BASE_DT, dtc.FRAME_SKIP_AT_BASE)
    cond_result["independent"][str(dtc.BASE_DT)] = dtc.summarize(base_info, base_log)
    print(f"  independent dt={dtc.BASE_DT}: end_reason={base_info['end_reason']} valid={base_info['scoring_valid']} score={base_info['batting_score']}")

    for dt in dtc.DT_CANDIDATES[1:]:
        scale = round(dtc.BASE_DT / dt)
        frame_skip = dtc.FRAME_SKIP_AT_BASE * scale
        info_i, _, log_i = dtc.run_recording(cfg, dt, frame_skip)
        cond_result["independent"][str(dt)] = dtc.summarize(info_i, log_i)
        print(f"  independent dt={dt}: end_reason={info_i['end_reason']} valid={info_i['scoring_valid']} score={info_i['batting_score']}")

        info_r, log_r = dtc.run_replay(base_actions, dt, frame_skip)
        cond_result["replay"][str(dt)] = dtc.summarize(info_r, log_r)
        print(f"  replay      dt={dt}: end_reason={info_r['end_reason']} valid={info_r['scoring_valid']} score={info_r['batting_score']}")

    cond_result["replay"][str(dtc.BASE_DT)] = dtc.summarize(base_info, base_log)

    finest, fine = str(dtc.DT_CANDIDATES[2]), str(dtc.DT_CANDIDATES[1])
    cond_result["acceptance"] = {
        "independent": dtc.check_pair(cond_result["independent"][fine], cond_result["independent"][finest]),
        "replay": dtc.check_pair(cond_result["replay"][fine], cond_result["replay"][finest]),
    }
    converged = cond_result["acceptance"]["independent"]["all_ok"] and cond_result["acceptance"]["replay"]["all_ok"]
    cond_result["converged"] = converged
    print(f"  ACCEPTANCE: independent_ok={cond_result['acceptance']['independent']['all_ok']} replay_ok={cond_result['acceptance']['replay']['all_ok']}")
    print(f"\nSAME-DIRECTION CONDITION CONVERGED: {converged}")

    out = {"same_direction_staggered": cond_result, "thresholds": {
        "separation_time_tol_s": dtc.SEPARATION_TIME_TOL_S,
        "landing_xy_abs_tol_m": dtc.LANDING_XY_ABS_TOL_M,
        "landing_xy_rel_tol": dtc.LANDING_XY_REL_TOL,
        "exit_vel_abs_tol_m_s": dtc.EXIT_VEL_ABS_TOL_M_S,
        "exit_vel_rel_tol": dtc.EXIT_VEL_REL_TOL,
        "dt_candidates": dtc.DT_CANDIDATES,
    }}
    out_path = OUT_DIR / "KC-01a-same-direction-dt-convergence.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

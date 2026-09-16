"""KC-01a-validation A5 (docs/tasks/KC-01a-VALIDATION-AND-VISION.md):
success-timing-window sweep, -20..+20ms at 1ms, on a CONVERGED setup only.

Of the 4 conditions, only torso_swing_with_arm_hold passed A2's dt-
convergence check (docs/records/evidence/KC-01a-dt-convergence.json,
committed) -- consistently invalid at every dt tested, both the replay and
independent checks. The task explicitly says "물리 수렴 전 성공률
최적화로 넘어가지 않는다" (don't move to success-rate optimization before
physics convergence), so the other three conditions' timing-window sweep
is NOT run here -- it is deferred until each has its own convergent
baseline (which may need a different trigger time / target geometry, not
just a finer dt, given staggered's outcome genuinely flips and
simultaneous's score does not settle down with dt).

For torso_swing_with_arm_hold, note also (docs/tasks/
KC-01a-VALIDATION-AND-VISION.md A5's own caution): "5ms 제어 양자화로
동일하게 실행된 조건은 독립 표본이 아니다" -- offsets that fall inside
the same 5ms control-step window as another offset produce byte-identical
runs (the controller only re-evaluates its trigger once per 5ms control
tick), so this sweep also records, for each 1ms offset, which control-step
index the trigger actually lands in, so "not independent" duplicates are
visible rather than silently counted as separate samples.
"""
from __future__ import annotations

import json
from pathlib import Path

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

CONVERGED_CONDITION = "torso_swing_with_arm_hold"
CFG = {
    "controller_mode": "torso_only",
    "torso_target": 0.496,
    "swing_target": -1.96,
    "torso_ct": 0.360,
    "swing_ct": 999.0,
}
CONTROL_DT = 0.005
DEFERRED_CONDITIONS = [
    "arm_swing_with_torso_hold",
    "simultaneous_swing_and_torso",
    "staggered_swing_and_torso",
]


def run(offset_s: float) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        torso_ct = CFG["torso_ct"] + offset_s
        controller = TorsoBatController(
            CFG["controller_mode"], 0.0, -1.96, 0.0, CFG["torso_target"], CFG["swing_target"], torso_ct, CFG["swing_ct"]
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        trigger_control_step = None
        step_idx = 0
        info = {}
        while True:
            action = controller.act(obs)
            if trigger_control_step is None and controller._torso_axis.state != "prepare":
                trigger_control_step = step_idx
            obs, _, terminated, truncated, info = env.step(action)
            step_idx += 1
            if terminated or truncated:
                break
        return {
            "offset_ms": offset_s * 1000.0,
            "trigger_control_step": trigger_control_step,
            "scoring_valid": info["scoring_valid"],
            "status": info["status"],
            "batting_score": info["batting_score"],
            "end_reason": info["end_reason"],
        }
    finally:
        env.close()


def main() -> None:
    rows = []
    for offset_ms in range(-20, 21, 1):
        r = run(offset_ms / 1000.0)
        rows.append(r)
        print(f"{offset_ms:+3d}ms -> trigger_step={r['trigger_control_step']} valid={r['scoring_valid']} score={r['batting_score']}")

    # Group by trigger_control_step to make the quantization explicit.
    by_step: dict = {}
    for r in rows:
        by_step.setdefault(r["trigger_control_step"], []).append(r["offset_ms"])

    n_valid = sum(1 for r in rows if r["scoring_valid"])
    result = {
        "condition": CONVERGED_CONDITION,
        "note": "torso_swing_with_arm_hold is A2-convergent but was ALREADY invalid at every dt -- this sweep checks whether ANY nearby trigger time within +-20ms produces a valid hit, not just the one calibrated point.",
        "sweep": rows,
        "distinct_control_steps_hit": len(by_step),
        "offsets_per_control_step": {str(k): v for k, v in by_step.items()},
        "success_window_count_of_41": n_valid,
        "success_window_fraction": n_valid / len(rows),
        "deferred_conditions": DEFERRED_CONDITIONS,
        "deferred_reason": "did not pass A2 dt-convergence; sweeping timing before a convergent baseline exists would be optimizing success rate before physics convergence, which the task explicitly prohibits.",
    }
    out_path = OUT_DIR / "KC-01a-timing-window.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nvalid in {n_valid}/{len(rows)} offsets tested; {len(by_step)} distinct control-step landings")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

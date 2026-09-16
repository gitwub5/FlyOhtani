"""KC-01a torso_lead_handoff search (user follow-up): searches for a
condition where the arm GENUINELY waits for torso motion (not just a fixed
10ms command offset) before accelerating, using the new
mode="torso_lead_handoff" added to controllers/baseball_kc01a.py. Swing
stays fully held (its own actuator does only P-hold, not max-torque
accelerate) until torso's own angular displacement reaches
`handoff_fraction` of its own target displacement -- this directly answers
the user's "모든 축을 처음부터 최대 입력으로 움직이는 방식만 고집하지
말라"/"선행 시간을 늘리면 항상 좋아진다고 가정하지 말라" instructions: swing
is NOT driven at max torque from t=0, and lead amount is swept rather than
assumed monotonic.

Searches over (torso_target, torso_ct, handoff_fraction) -- reusing the
geometry table already computed by scripts/kc01a_same_direction_search.py
(same torso_target candidates, same swing/tilt targets) so this does not
re-derive geometry that already exists. gear/mass/contact material/reward
are never touched.

For every valid hit found, verifies with scripts/
kc01a_torso_lead_analysis.py's own onset-time definition whether a
MEANINGFUL actual motion lead exists (not just a command offset) before
calling it a genuine same-direction lead-then-follow candidate.
"""
from __future__ import annotations

import json
from pathlib import Path

from controllers.baseball_kc01a import TorsoBatController
from envs.baseball_kc01a_env import BaseballKC01aEnv

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"
SEARCH_RESULT_PATH = OUT_DIR / "KC-01a-same-direction-search.json"

ONSET_QVEL_THRESHOLD = 0.05
MEANINGFUL_LEAD_S = 0.02  # pre-registered: an actual-motion lead below 20ms is not "meaningful" given B1's own known 5ms control-step-level noise floor


def run_episode(torso_target, swing_target, tilt_target, torso_ct, handoff_fraction):
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = TorsoBatController(
            "torso_lead_handoff", 0.0, -1.96, 0.0, torso_target, swing_target, torso_ct, 999.0,
            handoff_fraction=handoff_fraction,
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        torso_onset = swing_onset = None
        info = {}
        while True:
            t = float(env.data.time)
            torso_v = float(env.data.qvel[env.torso_qvel_adr])
            swing_v = float(env.data.qvel[env.swing_qvel_adr])
            if torso_onset is None and abs(torso_v) > ONSET_QVEL_THRESHOLD:
                torso_onset = t
            if swing_onset is None and abs(swing_v) > ONSET_QVEL_THRESHOLD:
                swing_onset = t
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        actual_lead = None if (torso_onset is None or swing_onset is None) else swing_onset - torso_onset
        return {
            "torso_target": torso_target,
            "swing_target": swing_target,
            "torso_ct": torso_ct,
            "handoff_fraction": handoff_fraction,
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
            "torso_motion_onset_t": torso_onset,
            "swing_motion_onset_t": swing_onset,
            "actual_motion_lead_s": actual_lead,
            "meaningful_lead": actual_lead is not None and actual_lead >= MEANINGFUL_LEAD_S,
        }
    finally:
        env.close()


def main() -> None:
    search = json.loads(SEARCH_RESULT_PATH.read_text())
    geometry = search["geometry_search"]

    torso_targets = [0.2, 0.3, 0.4]
    torso_cts = [0.15, 0.20, 0.25, 0.30, 0.36]
    handoff_fractions = [0.15, 0.3, 0.5, 0.7]

    results = []
    for tt in torso_targets:
        g = geometry[str(tt)]
        for ct in torso_cts:
            for hf in handoff_fractions:
                r = run_episode(tt, g["swing_target"], g["tilt_target"], ct, hf)
                results.append(r)

    valid = [r for r in results if r["scoring_valid"]]
    valid_and_leading = [r for r in valid if r["meaningful_lead"]]
    print(f"total={len(results)} valid={len(valid)} valid_and_meaningful_lead={len(valid_and_leading)}")
    for r in sorted(valid, key=lambda x: -x["batting_score"])[:10]:
        print(f"  torso_target={r['torso_target']} torso_ct={r['torso_ct']} handoff_frac={r['handoff_fraction']} "
              f"score={r['batting_score']:.3f} actual_lead={r['actual_motion_lead_s']} meaningful={r['meaningful_lead']}")

    out = {
        "search_space": {"torso_targets": torso_targets, "torso_cts": torso_cts, "handoff_fractions": handoff_fractions},
        "onset_qvel_threshold": ONSET_QVEL_THRESHOLD,
        "meaningful_lead_threshold_s": MEANINGFUL_LEAD_S,
        "all_results": results,
        "n_valid": len(valid),
        "n_valid_and_meaningful_lead": len(valid_and_leading),
        "best_valid_and_leading": (
            max(valid_and_leading, key=lambda x: x["batting_score"]) if valid_and_leading else None
        ),
        "best_valid_overall": max(valid, key=lambda x: x["batting_score"]) if valid else None,
    }
    out_path = OUT_DIR / "KC-01a-torso-lead-handoff-search.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

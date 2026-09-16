"""KC-01a-validation A3 (docs/tasks/KC-01a-VALIDATION-AND-VISION.md): per-
axis settle diagnostics, separate from the normal episode/outcome contract.

Two diagnostic modes, both explicit and separate from BaseballKC01aEnv's
own step() (which still rejects any call after terminated/truncated --
unchanged, verified by the existing test suite):

1. POST-LANDING CONTINUATION: run mid_mid normally to its real outcome
   (score/status unchanged, exactly as scripts/kc01a_compare_conditions.py
   reports it), then keep integrating physics for at least 1.2s past the
   LATEST moving axis's own brake-start instant, using env.data/env.model
   directly (mujoco.mj_step + mj_forward), continuing to apply the same
   controller's ctrl each control step read via env._get_obs() (a pure
   read of qpos/qvel -- no outcome/reward is touched or backdated).
2. NO-BALL SWING: same controller/timing, but the bat geom's
   contype/conaffinity are zeroed so it cannot register contact with
   anything -- the ball still flies on its real trajectory (so the
   controller's own remaining-time trigger still fires naturally), but
   swings clean through empty air.

Settle criterion (per axis, from that axis's own accelerate->brake latch
instant): within 0.5s, |qvel| < 0.2 rad/s, THEN continuously for the next
0.2s, angle peak-to-peak < 0.02rad AND |qvel| < 0.2rad/s sampled every
control step (not a single sample -- the whole 0.2s window must hold).
Axes that never leave "prepare" (held the whole episode) are reported
separately, not scored against this criterion (already at a constant
target, latch never happens).
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

MIN_CONTINUATION_S = 1.2
SETTLE_QVEL = 0.2
SETTLE_TO_S = 0.5
SETTLE_HOLD_S = 0.2
CONTROL_DT = 0.005


def _make_controller(cfg: dict) -> TorsoBatController:
    return TorsoBatController(
        cfg["controller_mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
    )


def _axis_history_to_settle(history: list[tuple[float, float, float, str]]) -> dict:
    """history: list of (t, angle, qvel, axis_state) sampled once per
    control step. Finds the axis's own accelerate->brake latch instant,
    then checks the 0.5s/0.2s criterion from there. Returns a dict with
    latch_time_s, settle_time_s (first instant the 0.2s continuous window
    begins, or None), meets_target, and the reason if not met."""
    latch_t = None
    prev_state = None
    for t, _angle, _qvel, state in history:
        if prev_state == "accelerate" and state == "brake" and latch_t is None:
            latch_t = t
        prev_state = state
    if latch_t is None:
        return {"applicable": False, "reason": "axis never left prepare/accelerate (held or never triggered)"}

    # Restrict to samples from latch onward.
    post = [(t, a, v) for t, a, v, _s in history if t >= latch_t]
    if not post:
        return {"applicable": True, "latch_time_s": latch_t, "meets_target": False, "reason": "no samples after latch"}

    # Find first instant within 0.5s of latch where |qvel|<threshold AND
    # it stays true continuously (every sampled control step) for the next
    # 0.2s, with angle peak-to-peak < 0.02rad over that same window.
    for i, (t, _a, v) in enumerate(post):
        if t - latch_t > SETTLE_TO_S:
            break
        if abs(v) >= SETTLE_QVEL:
            continue
        window = [(tt, aa, vv) for tt, aa, vv in post[i:] if tt <= t + SETTLE_HOLD_S]
        if not window or window[-1][0] < t + SETTLE_HOLD_S - CONTROL_DT * 1.5:
            continue  # not enough data to confirm the full 0.2s window
        angles = [aa for _, aa, _ in window]
        vels = [vv for _, _, vv in window]
        if (max(angles) - min(angles)) < 0.02 and all(abs(vv) < SETTLE_QVEL for vv in vels):
            return {
                "applicable": True,
                "latch_time_s": latch_t,
                "settle_time_s": t,
                "settle_duration_s": t - latch_t,
                "meets_target": (t - latch_t) <= SETTLE_TO_S,
                "angle_pp_over_hold_window_rad": max(angles) - min(angles),
            }
    return {
        "applicable": True,
        "latch_time_s": latch_t,
        "settle_time_s": None,
        "meets_target": False,
        "reason": "no instant found meeting the 0.5s-to-threshold + continuous 0.2s window criterion",
        "final_qvel": post[-1][2],
        "observed_duration_s": post[-1][0] - latch_t,
    }


def run_post_landing_continuation(mode: str, cfg: dict) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        controller = _make_controller(cfg)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()

        history: dict[str, list] = {"torso": [], "swing": []}

        def record():
            history["torso"].append(
                (
                    float(env.data.time),
                    float(env.data.qpos[env.torso_qpos_adr]),
                    float(env.data.qvel[env.torso_qvel_adr]),
                    controller._torso_axis.state,
                )
            )
            history["swing"].append(
                (
                    float(env.data.time),
                    float(env.data.qpos[env.swing_qpos_adr]),
                    float(env.data.qvel[env.swing_qvel_adr]),
                    controller._swing_axis.state,
                )
            )

        # Phase 1: normal episode (outcome/score exactly as the regular
        # comparison reports it -- untouched by anything below).
        info = {}
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            record()
            if terminated or truncated:
                break
        outcome = {
            "end_reason": info["end_reason"],
            "scoring_valid": info["scoring_valid"],
            "batting_score": info["batting_score"],
        }

        # Phase 2: diagnostic continuation -- env.step() is never called
        # again (its terminal-rejection contract is untouched); physics is
        # driven directly. The controller keeps computing ctrl from a
        # manually-read observation so torso/swing keep braking/holding
        # exactly as they would if the episode were still "live", but no
        # reward/outcome is recomputed or backdated.
        last_latch_guess = max(
            (t for t, *_r in history["torso"]), default=0.0
        )  # will be refined once we know actual latch times below; use total elapsed as a safe over-estimate for now
        target_end_time = float(env.data.time) + max(MIN_CONTINUATION_S, 0.0)
        # Also make sure we run at least MIN_CONTINUATION_S past whichever
        # axis latches LAST -- but latch may not have happened yet if
        # contact was late; loop until both conditions are satisfied or a
        # generous safety cap.
        safety_cap_time = float(env.data.time) + 4.0
        control_steps = 0
        while float(env.data.time) < target_end_time and float(env.data.time) < safety_cap_time:
            obs = env._get_obs()
            action = controller.act(obs)
            torso_ctrl = float(np.clip(action[0], -1.0, 1.0))
            swing_ctrl = float(np.clip(action[1], -1.0, 1.0))
            tilt_ctrl = float(np.clip(action[2], -1.0, 1.0))
            env.data.ctrl[env.torso_actuator_id] = torso_ctrl
            env.data.ctrl[env.swing_actuator_id] = swing_ctrl
            env.data.ctrl[env.tilt_actuator_id] = tilt_ctrl
            for _ in range(env.frame_skip):
                mujoco.mj_step(env.model, env.data)
            mujoco.mj_forward(env.model, env.data)
            record()
            control_steps += 1
            # Extend target_end_time once we actually observe a late latch
            # so "1.2s past the LATEST latch" is genuinely satisfied, not
            # just "1.2s past episode end".
            for axis_name in ("torso", "swing"):
                h = history[axis_name]
                for i in range(1, len(h)):
                    if h[i - 1][3] == "accelerate" and h[i][3] == "brake":
                        target_end_time = max(target_end_time, h[i][0] + MIN_CONTINUATION_S)
            if control_steps > 2000:  # hard safety valve (~10s of continuation)
                break

        settle = {axis: _axis_history_to_settle(history[axis]) for axis in ("torso", "swing")}
        return {"outcome": outcome, "settle": settle, "continuation_final_time_s": float(env.data.time), "_last_latch_guess_unused": last_latch_guess}
    finally:
        env.close()


def run_noball_swing(mode: str, cfg: dict) -> dict:
    env = BaseballKC01aEnv(prep_torso=0.0, prep_swing=-1.96, prep_tilt=0.0)
    try:
        # Disable the bat's collision entirely (contype/conaffinity=0) so
        # it cannot register contact with the ball or anything else -- the
        # ball still flies its real trajectory, so the controller's own
        # remaining-time trigger fires naturally (unlike teleporting the
        # ball away, which would break the "ball approaching" trigger
        # condition entirely).
        env.model.geom_contype[env.bat_geom_id] = 0
        env.model.geom_conaffinity[env.bat_geom_id] = 0

        controller = _make_controller(cfg)
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        history: dict[str, list] = {"torso": [], "swing": []}

        def record():
            history["torso"].append(
                (
                    float(env.data.time),
                    float(env.data.qpos[env.torso_qpos_adr]),
                    float(env.data.qvel[env.torso_qvel_adr]),
                    controller._torso_axis.state,
                )
            )
            history["swing"].append(
                (
                    float(env.data.time),
                    float(env.data.qpos[env.swing_qpos_adr]),
                    float(env.data.qvel[env.swing_qvel_adr]),
                    controller._swing_axis.state,
                )
            )

        info = {}
        while True:
            action = controller.act(obs)
            obs, _, terminated, truncated, info = env.step(action)
            record()
            if terminated or truncated:
                break
        assert not info["contact_occurred"], "bat collision should have been fully disabled for this diagnostic"

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
        return {"contact_occurred_pre_disable_check": info["contact_occurred"], "settle": settle, "continuation_final_time_s": float(env.data.time)}
    finally:
        env.close()


def main() -> None:
    result = {"post_landing_continuation": {}, "noball_swing": {}}
    for mode, cfg in CONDITIONS.items():
        print(f"=== {mode} ===")
        r1 = run_post_landing_continuation(mode, cfg)
        del r1["_last_latch_guess_unused"]
        result["post_landing_continuation"][mode] = r1
        print("  post-landing:", json.dumps(r1["settle"], default=str))
        r2 = run_noball_swing(mode, cfg)
        result["noball_swing"][mode] = r2
        print("  no-ball:     ", json.dumps(r2["settle"], default=str))

    out_path = OUT_DIR / "KC-01a-settle-diagnostics.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

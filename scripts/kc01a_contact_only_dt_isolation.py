"""KC-01a divergence decomposition, step 2 (user follow-up to
docs/records/KC-01a-VALIDATION.md A2): given an IDENTICAL pre-collision
state (captured once, at BASE_DT), does re-simulating ONLY the ball-bat
collision window at different physics_dt change the outcome? This isolates
the contact solver's own dt-sensitivity from any accumulated dt-dependent
drift in how the pre-collision state was reached (that side is
scripts/kc01a_noball_dt_isolation.py) -- together the two scripts decompose
A2's "접촉의 이산화 민감도로 추정" hypothesis into "drive-only" vs
"collision-only" contributions instead of leaving them conflated.

Method: record the real controller at BASE_DT (0.00025s) once, snapshotting
full (time, qpos, qvel) at the START of every control step. Take the
snapshot from the LAST control step whose start-time is strictly before
info['first_contact_time_s'] as the checkpoint (this control step is where
contact first occurs; the checkpoint itself is still pre-contact). For each
dt candidate, build a fresh env, overwrite its qpos/qvel/time arrays
directly from that checkpoint (mj_forward to refresh derived kinematics --
the env's own episode bookkeeping, e.g. _phase='pitch'/_contact_occurred=
False, is already correct for a strictly-pre-contact state, identical to
what reset() itself would set), then replay the SAME recorded action
sequence from that control step onward (zero-order hold past exhaustion,
same technique as scripts/kc01a_dt_convergence.py's run_replay) at the
target dt. Compares outcomes across the 3 dt candidates using A2's own
pre-registered thresholds (imported, not re-typed).
"""
from __future__ import annotations

import json
from pathlib import Path

import kc01a_dt_convergence as dtc
import numpy as np

from controllers.baseball_kc01a import TorsoBatController

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "records" / "evidence"

CONDITIONS = dtc.CONDITIONS


def record_with_checkpoints(cfg: dict) -> tuple[dict, list, tuple]:
    """Runs the real controller at BASE_DT, recording (time, qpos.copy(),
    qvel.copy()) at the START of each control step plus the action taken
    that step. Returns (info, actions_from_checkpoint, checkpoint) where
    checkpoint = (time, qpos, qvel, checkpoint_control_step_index)."""
    env = dtc._make_env_at_dt(dtc.BASE_DT, dtc.FRAME_SKIP_AT_BASE)
    try:
        controller = TorsoBatController(
            cfg["controller_mode"], 0.0, -1.96, 0.0, cfg["torso_target"], cfg["swing_target"], cfg["torso_ct"], cfg["swing_ct"]
        )
        obs, _ = env.reset(seed=0, options={"course": "mid_mid"})
        controller.reset()
        snapshots = []  # (time, qpos, qvel) at start of each control step
        actions = []
        info = {}
        while True:
            snapshots.append((float(env.data.time), env.data.qpos.copy(), env.data.qvel.copy()))
            action = controller.act(obs)
            actions.append(action.tolist())
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break

        if info["first_contact_time_s"] is None:
            return info, [], None

        checkpoint_idx = 0
        for i, (t, _q, _v) in enumerate(snapshots):
            if t < info["first_contact_time_s"]:
                checkpoint_idx = i
            else:
                break
        ckpt_time, ckpt_qpos, ckpt_qvel = snapshots[checkpoint_idx]
        checkpoint = (ckpt_time, ckpt_qpos, ckpt_qvel, checkpoint_idx)
        actions_from_checkpoint = actions[checkpoint_idx:]
        return info, actions_from_checkpoint, checkpoint
    finally:
        env.close()


def replay_from_checkpoint(checkpoint: tuple, actions: list, dt: float, frame_skip: int) -> tuple[dict, dtc.ContactLog]:
    ckpt_time, ckpt_qpos, ckpt_qvel, _idx = checkpoint
    env = dtc._make_env_at_dt(dt, frame_skip)
    try:
        env.reset(seed=0, options={"course": "mid_mid"})
        # Overwrite full physics state (torso/swing/tilt AND the ball's
        # free joint -- everything in qpos/qvel) from the BASE_DT
        # checkpoint. The env's own episode bookkeeping (_phase="pitch",
        # _contact_occurred=False, etc.) is left exactly as reset() set it
        # -- correct, because the checkpoint is strictly pre-contact, so a
        # fresh reset()'s bookkeeping already matches what the real
        # BASE_DT run's bookkeeping was at that same instant (nothing
        # contact-related has happened yet on either side).
        env.data.qpos[:] = ckpt_qpos
        env.data.qvel[:] = ckpt_qvel
        env.data.time = ckpt_time
        import mujoco

        mujoco.mj_forward(env.model, env.data)

        log = dtc.ContactLog()
        info = {}
        max_steps = max(len(actions) * 4, 200)
        for i in range(max_steps):
            action = actions[i] if i < len(actions) else actions[-1]
            _obs, _, terminated, truncated, info = env.step(np.array(action, dtype=np.float32), substep_callback=log)
            if terminated or truncated:
                break
        return info, log
    finally:
        env.close()


def main() -> None:
    result = {"per_condition": {}}
    for mode, cfg in CONDITIONS.items():
        print(f"\n=== {mode} (was {cfg['old_name']}) ===")
        info_base, actions_from_ckpt, checkpoint = record_with_checkpoints(cfg)
        if checkpoint is None:
            print("  no contact ever occurred at BASE_DT -- skipping (nothing to checkpoint before)")
            result["per_condition"][mode] = {"skipped": True, "reason": "no bat contact at BASE_DT"}
            continue
        ckpt_time, _q, _v, ckpt_idx = checkpoint
        print(f"  checkpoint: control_step={ckpt_idx} t={ckpt_time:.5f}s (first_contact_time_s={info_base['first_contact_time_s']:.5f}s)")

        cond_result = {"checkpoint_time_s": ckpt_time, "checkpoint_control_step": ckpt_idx, "per_dt": {}}
        for dt, frame_skip in zip(dtc.DT_CANDIDATES, (dtc.FRAME_SKIP_AT_BASE, 40, 80)):
            info, log = replay_from_checkpoint(checkpoint, actions_from_ckpt, dt, frame_skip)
            cond_result["per_dt"][str(dt)] = dtc.summarize(info, log)
            print(f"  dt={dt}: end_reason={info['end_reason']} valid={info['scoring_valid']} score={info['batting_score']} exit_speed={info['exit_speed']}")

        finest, fine = str(dtc.DT_CANDIDATES[2]), str(dtc.DT_CANDIDATES[1])
        acceptance = dtc.check_pair(cond_result["per_dt"][fine], cond_result["per_dt"][finest])
        cond_result["acceptance"] = acceptance
        cond_result["converged_contact_only"] = acceptance["all_ok"]
        print(f"  CONTACT-ONLY CONVERGED (identical pre-collision state): {acceptance['all_ok']}")
        result["per_condition"][mode] = cond_result

    out_path = OUT_DIR / "KC-01a-contact-only-dt-isolation.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

"""How narrow should the acute zone be, now that the decision window moved?

D37 halved swing-to-contact (24.60 -> 12.35 ms), which moved the decision
deadline 12 ms later and re-aimed the left eye from 2 ms into the flight to
29.65 (`world.batter.decision_point`, corrected in the same change). Both
change what the fly sees, and `studies.zone_rise` immediately showed the
cost: the default circuit stopped committing on high pitches at all.

`studies.decision_window` says what the eye still owes: the looming signal
peaks when the ball is about 3 pixels across, and at the new deadline it is
about 1.9. Narrowing the acute zone buys pixels directly -- 20 deg over 32 px
is 0.63 deg/px, and halving the field halves that -- and it is the one lever
left after the user ruled out changing the ball or the bat.

IT IS NOT FREE, AND NOT MONOTONIC. A narrower field is a smaller window for
the ball to stay inside, and the decision window is now 70% longer, so the
ball sweeps more of the field during it. VM-01 already measured this shape
once: at D32's release distance a 30 deg field detected the ball in 0 of 9
decision frames while 20 deg got 9 of 9. So this measures detection ACROSS
the window rather than the ball's angular size at one instant.

Criteria are VM-01's, reused rather than reinvented:

  DETECT_THRESHOLD   a pixel changing by >= 8 grey levels is the ball
  MIN_CONTINUITY     >= 0.8 of the decision window's frames detect it

    python -m flyohtani.studies.eye_field
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from flyohtani.studies.eye_rate import DETECT_THRESHOLD
from flyohtani.studies.eye_rate_v2 import MIN_CONTINUITY
from flyohtani.task.env import Action, BattingEnv, PitchSpec
from flyohtani.world import batter as B

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

FIELDS_DEG = (20.0, 17.0, 15.0, 13.0, 11.0, 9.0)
"""20 is what D32 chose. Below it is what D37's deadline might now afford."""

WINDOW_FRAMES = 8
"""VM-01's requirement: the last this many eye frames before the deadline."""


def _empty_frame(env: BattingEnv) -> np.ndarray:
    """The eye with the ball parked far away, for the difference the
    detection threshold is applied to (VM-01's method)."""
    m, d = env._model, env._data
    d.qpos[env._qa:env._qa + 3] = (0.0, -250.0, 5.0)
    d.qvel[env._va:env._va + 6] = 0
    import mujoco
    mujoco.mj_forward(m, d)
    return B.render_eyes(m, d, env._renderer)["L"].astype(np.int16)


def measure_field(fovy_deg: float, timings_ms=(-2.0, 0.0, 2.0)) -> dict:
    scene = B.build_scene(B.SceneOptions(eye_fovy_deg=fovy_deg))
    env = BattingEnv(scene=scene)
    blank = _empty_frame(env)
    deadline_frame = int((0.052 - B.SWING_TO_CONTACT_S - B.DECISION_LATENCY_S) * B.EYE_RATE_HZ)
    rows = []
    for zone in B.STRIKE_ZONES:
        for timing in timings_ms:
            obs = env.reset(PitchSpec(zone=zone, timing_ms=timing))
            seen, done = [], False
            while not done:
                change = np.abs(obs.eye_left.astype(np.int16) - blank)
                seen.append(int((change >= DETECT_THRESHOLD).sum()))
                obs, _, done, _ = env.step(Action(swing=False))
            lo = max(deadline_frame - WINDOW_FRAMES + 1, 0)
            window = seen[lo:deadline_frame + 1]
            rows.append({"zone": zone, "timing_ms": timing,
                         "frames": len(seen),
                         "continuity": (sum(px > 0 for px in window) / len(window)) if window else 0.0,
                         "max_px_in_window": max(window) if window else 0,
                         "max_px_overall": max(seen) if seen else 0})
    env.close()
    cont = [r["continuity"] for r in rows]
    return {
        "fovy_deg": fovy_deg,
        "deg_per_px": fovy_deg / B.EYE_RESOLUTION,
        "deadline_frame": deadline_frame,
        "worst_continuity": min(cont),
        "mean_continuity": float(np.mean(cont)),
        "worst_max_px": min(r["max_px_in_window"] for r in rows),
        "passes": min(cont) >= MIN_CONTINUITY,
        "rows": rows,
    }


def main() -> None:
    out = []
    header = (f"{'fovy':>6} {'deg/px':>7} {'worst cont':>11} {'mean cont':>10} "
              f"{'worst px':>9}  {'VM-01 W3':>9}")
    print(f"deadline is eye frame {int((0.052 - B.SWING_TO_CONTACT_S - B.DECISION_LATENCY_S) * B.EYE_RATE_HZ)}"
          f", window = last {WINDOW_FRAMES} frames, continuity must be >= {MIN_CONTINUITY}\n")
    print(header)
    print("-" * len(header))
    for fovy in FIELDS_DEG:
        r = measure_field(fovy)
        out.append(r)
        print(f"{fovy:5.0f}d {r['deg_per_px']:7.3f} {r['worst_continuity']:11.2f} "
              f"{r['mean_continuity']:10.2f} {r['worst_max_px']:9d}  "
              f"{'PASS' if r['passes'] else 'fail':>9}", flush=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / "EYE-FIELD.json"
    path.write_text(json.dumps({"detect_threshold": DETECT_THRESHOLD,
                                "min_continuity": MIN_CONTINUITY,
                                "window_frames": WINDOW_FRAMES,
                                "swing_to_contact_s": B.SWING_TO_CONTACT_S,
                                "fields": out}, indent=1) + "\n")
    print("\nwrote", path)
    _ = math


if __name__ == "__main__":
    main()

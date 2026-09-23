"""How much looming is there to see, at the moment the fly has to commit?

STATUS's first open item is "open the decision window", and three levers are
usually named for it: throw slower, swing faster, or use a lighter bat. This
measures what they actually buy, because they all act through ONE quantity --

    how close the ball is when the swing has to start

-- and that is measurable rather than arguable.

The deadline is `flight - swing_to_contact - decision_latency`. Both a slower
pitch and a faster swing move the ball closer to the plate at that instant:
the first gives the ball more time to arrive before the deadline, the second
moves the deadline later. So one simulation per flight time is enough for
both levers -- the retinal trace is recorded against the clock, and any
(flight, swing_to_contact) pair is then read off it.

WHAT IS BEING TESTED. `circuit.INPUT_GAIN` records that over the current
decision window the strongest pooled contrast runs about 0.010 early and
0.018 late -- it not quite doubles, while the 10x growth of a real looming
stimulus arrives AFTER the swing has had to start. If that is why the
connectome has nothing to work with (BRAIN-CIRCUIT's shuffled control), then
the thing to ask of any design change is how much it moves that ratio.

CAVEAT, stated because it bounds every number below: the left eye's acute
zone is aimed once, at the decision point of the STANDARD 52 ms pitch
(`world.batter.decision_point`). A slower pitch is not re-aimed here, so its
contrast is a lower bound -- re-aiming is part of the design change, not of
this measurement.

    python -m flyohtani.studies.decision_window
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from flyohtani.brain.connectome import SOURCE_TYPES, load_looming_subgraph
from flyohtani.brain.retina import Retina, build_receptive_fields
from flyohtani.task.env import Action, BattingEnv, PitchSpec
from flyohtani.world import batter as B
from flyshohei import pitch as P

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

FLIGHTS_S = (0.052, 0.065, 0.080, 0.100, 0.130)
"""0.052 is the pitch as thrown (D35). The rest are hypotheticals -- nothing
here changes `flyshohei.pitch.STANDARD`."""

SWING_TO_CONTACT_S = (0.0246, 0.020, 0.015, 0.010)
"""0.0246 is measured (`batter.SWING_TO_CONTACT_S`). The rest are what a
faster swing or a lighter bat would have to reach; whether they are reachable
is a separate question for the pose search and G1, not for this file."""

WINDOW_FRAMES = 8
"""VM-01's requirement: the evidence the fly decides on is the last this many
eye frames before the deadline."""


def trace(flight_s: float, env: BattingEnv, timing_ms: float = 0.0) -> dict:
    """Pooled retinal contrast per eye frame, for one pitch, no swing."""
    fields = build_receptive_fields(
        sum(len(load_looming_subgraph().ids_of_type(t)) for t in SOURCE_TYPES) // len(SOURCE_TYPES),
        B.EYE_RESOLUTION)
    retina = Retina(B.EYE_RESOLUTION)
    obs = env.reset(PitchSpec(flight_s=flight_s, timing_ms=timing_ms))
    contrast, ball_x = [], []
    done = False
    while not done:
        on, off = retina.encode(obs.eye_left)
        contrast.append(float(fields.pool(on + off).max()))
        ball_x.append(float(env._data.xpos[env._ball][0]))
        obs, _, done, _ = env.step(Action(swing=False))
    return {"flight_s": flight_s, "contrast": contrast, "ball_x_mm": ball_x}


def read_off(tr: dict, swing_to_contact_s: float, r_ball_mm: float) -> dict | None:
    """What the eye has actually delivered by the deadline, against what the
    flight delivers in total.

    NOT a frame-to-frame ratio. The first version of this measured
    contrast[last] / contrast[first] and produced nonsense (a faster swing
    scoring LOWER growth), because the pooled contrast is not monotonic: the
    ball is around one pixel wide and crosses between receptive fields, so
    single frames swing by a factor of three in both directions. What is
    stable is the PEAK available by a deadline, so that is what this reports.
    """
    rate = B.EYE_RATE_HZ
    t_decide = tr["flight_s"] - swing_to_contact_s - B.DECISION_LATENCY_S
    if t_decide <= 0:
        return None
    last = int(t_decide * rate)
    if last < 1 or last >= len(tr["contrast"]):
        return None
    by_deadline = max(tr["contrast"][:last + 1])
    overall = max(tr["contrast"])
    peak_frame = int(np.argmax(tr["contrast"]))
    distance = abs(tr["ball_x_mm"][last])
    return {
        "swing_to_contact_s": swing_to_contact_s,
        "window_ms": t_decide * 1e3,
        "deadline_frame": last,
        "peak_by_deadline": by_deadline,
        "peak_overall": overall,
        "fraction_available": (by_deadline / overall) if overall > 0 else 0.0,
        "peak_frame": peak_frame,
        "peak_arrives_ms_late": (peak_frame - last) / rate * 1e3,
        "distance_at_deadline_mm": distance,
        "angular_diameter_deg": math.degrees(2 * math.atan(r_ball_mm / distance)) if distance > 0 else math.inf,
        "pixels_across": math.degrees(2 * math.atan(r_ball_mm / distance)) / (B.EYE_FOVY_DEG / B.EYE_RESOLUTION)
        if distance > 0 else math.inf,
        "eye_rate_needed_hz": B.MIN_DECISION_FRAMES / t_decide,
    }


def measure(timings_ms: tuple[float, ...] = (-2.0, 0.0, 2.0)) -> dict:
    """Geometry for every condition; retinal contrast only where the eye is
    actually aimed for it.

    The left eye's acute zone is aimed once, at the decision point of the
    STANDARD pitch (`world.batter.build_scene`). A hypothetical flight is not
    re-aimed, and a slower pitch from the same mound is also lofted much
    higher, so its contrast here says "the ball left the narrow field", not
    "the ball was too small". Those rows are marked and their contrast is not
    comparable. Re-aiming is part of the design change, not of this file.
    """
    env = BattingEnv()
    r_ball = B.BALL_RADIUS_MM * env.scene.scale * B.BALL_SCALE
    strike = np.array([0.0, 0.0, 1.2])
    out = []
    for flight in FLIGHTS_S:
        traces = [trace(flight, env, t) for t in timings_ms]
        speed = P.STANDARD.speed_mm_s(strike, env.scene.scale, flight_s=flight)
        loft = P.STANDARD.launch_angle_deg(strike, env.scene.scale, flight_s=flight)
        rows = []
        for s in SWING_TO_CONTACT_S:
            reads = [r for tr in traces if (r := read_off(tr, s, r_ball)) is not None]
            if not reads:
                continue
            rows.append({k: (float(np.median([r[k] for r in reads]))
                             if isinstance(reads[0][k], (int, float)) else reads[0][k])
                         for k in reads[0]})
        out.append({"flight_s": flight, "speed_mm_s": speed, "launch_angle_deg": loft,
                    "eye_aimed_for_this_flight": flight == P.STANDARD.flight_s,
                    "reads": rows})
    return {"ball_radius_mm": r_ball, "eye_rate_hz": B.EYE_RATE_HZ,
            "pixel_deg": B.EYE_FOVY_DEG / B.EYE_RESOLUTION,
            "timings_ms": list(timings_ms), "conditions": out}


def main() -> None:
    result = measure()
    px = result["pixel_deg"]
    print(f"ball radius {result['ball_radius_mm']:.4f} mm · eye {result['eye_rate_hz']} Hz · "
          f"{px:.2f} deg/px · median over timings {result['timings_ms']} ms\n")
    print("GEOMETRY AT THE DEADLINE (exact -- no eye involved)")
    header = (f"{'flight':>7} {'speed':>7} {'loft':>6} | {'swing':>6} {'window':>7} "
              f"{'dist':>8} {'ang':>7} {'px':>6} {'eye_req':>8}")
    print(header)
    print("-" * len(header))
    for c in result["conditions"]:
        for i, r in enumerate(c["reads"]):
            head = (f"{c['flight_s']*1e3:6.0f}m {c['speed_mm_s']:6.0f} {c['launch_angle_deg']:+5.1f}"
                    if i == 0 else " " * 21)
            slow = "" if r["eye_rate_needed_hz"] <= result["eye_rate_hz"] else " eye too slow"
            print(f"{head} | {r['swing_to_contact_s']*1e3:5.1f}m {r['window_ms']:6.1f}m "
                  f"{r['distance_at_deadline_mm']:7.2f}m {r['angular_diameter_deg']:6.2f}d "
                  f"{r['pixels_across']:5.1f} {r['eye_rate_needed_hz']:7.0f}{slow}")
        print()

    print("WHAT THE EYE HAS DELIVERED BY THEN")
    header = (f"{'flight':>7} | {'swing':>6} {'peak<=dl':>9} {'peak_all':>9} "
              f"{'available':>10} {'peak arrives':>13}")
    print(header)
    print("-" * len(header))
    for c in result["conditions"]:
        aimed = c["eye_aimed_for_this_flight"]
        for i, r in enumerate(c["reads"]):
            head = f"{c['flight_s']*1e3:6.0f}m" if i == 0 else " " * 7
            note = "" if aimed else "   (eye not re-aimed; loft "f"{c['launch_angle_deg']:+.0f}d)"
            print(f"{head} | {r['swing_to_contact_s']*1e3:5.1f}m {r['peak_by_deadline']:9.3f} "
                  f"{r['peak_overall']:9.3f} {r['fraction_available']:9.0%} "
                  f"{r['peak_arrives_ms_late']:+9.1f} ms{note}")
        print()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "DECISION-WINDOW.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()

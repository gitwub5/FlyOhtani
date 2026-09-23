"""Can the fly reach the same contact poses in less time?

WHY. `studies.decision_window` measured that the fly commits on 44% of the
looming signal, and that what it needs is a ball ~3 pixels across at the
deadline against the 1.2 it gets. Every lever for that costs realism -- a
bigger ball, a more acute eye, a slower pitch, moving the pitcher back --
except one: the swing's own duration. The deadline is
`flight - swing_to_contact - latency`, so a shorter swing moves the deadline
later and the ball is closer when it arrives.

WHAT IS ACTUALLY SLOW. Not the muscles. `joint_RFCoxa_yaw` travels 260.6
degrees from READY_POSE to CONTACT_POSE while no other joint travels more
than 78.8, and a cosine ease reaches peak_omega = dtheta * pi(1+follow) /
(2*duration), so that ONE joint sets the whole swing's duration. Its analytic
minimum at a 300 rad/s ceiling is 38.1 ms, which is exactly the 38 ms
`batter.DEMO_SWING_S` records as "the fastest the commanded swing could be".
The long way around is taken because the short way sweeps the bat through the
ground. `find_ready_pose` never scored the path -- only the contact instant --
so nothing pushed back on 260 degrees.

PRE-REGISTERED, fixed before this was run. A candidate stance must, for ALL
THREE zones and with ONE stance shared between them (D36):

  1. peak joint speed <= 300 rad/s                  LIT-01's ceiling
  2. ground clearance >= 0.25 mm                    poses.GROUND_CLEARANCE_MM
  3. attack angle within [+5, +15] deg              poses.SWING_ATTACK_DEG's range
  4. bat speed at contact >= 400 mm/s               the pose in use gets 538-555
  5. sweet spot passes within 0.20 mm of the        ANCHORED TO THE STATUS QUO,
     contact point                                  not invented: the pose in use
                                                    misses by 0.056/0.121/0.184,
                                                    so a tolerance under 0.184
                                                    would reject the swing the
                                                    project already runs on.
                                                    This is the check that the
                                                    arm still TRACKS a faster
                                                    command instead of lagging
                                                    and never reaching the ball.

SUCCESS = such a stance exists with a swing shorter than the 40 ms in use.
The shortest found is reported whatever it is, and the criteria are not
relaxed afterwards. Three seeds are run because one hill-climb is one sample.

NOTHING IS ADOPTED HERE. Changing the swing moves `SWING_TO_CONTACT_S`, and
with it the decision deadline, the required eye rate and every timing number
downstream -- that is a design decision with a D-number, not a measurement.

    python -m flyohtani.studies.fast_swing [seed]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

from flyohtani.world import batter as B
from flyohtani.world.poses import find_fast_ready_pose, minimum_duration_s, probe_swing

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

CEILING_RAD_S = 300.0
ATTACK_RANGE_DEG = (5.0, 15.0)
SPEED_FLOOR_MM_S = 400.0
TRACKING_TOL_MM = 0.20


def status_quo() -> dict:
    """The swing in use, measured the same way, so the comparison is like
    for like rather than against numbers quoted from a document."""
    poses = list(B.CONTACT_POSES.values())
    probes = [probe_swing(p, B.READY_POSE, duration_s=B.DEMO_SWING_S,
                          follow=B.DEMO_SWING_FOLLOW, dt_s=2.5e-5) for p in poses]
    travel = max(abs(c[j] - B.READY_POSE[j]) for c in poses for j in B.ACTIVE_JOINTS)
    return {
        "duration_s": B.DEMO_SWING_S,
        "analytic_minimum_s": minimum_duration_s(B.READY_POSE, poses, B.DEMO_SWING_FOLLOW,
                                                 CEILING_RAD_S),
        "max_joint_travel_deg": math.degrees(travel),
        "zones": _zone_rows(probes),
    }


def _zone_rows(probes) -> list[dict]:
    return [{"zone": z, "speed_mm_s": p.speed_mm_s, "attack_deg": p.attack_deg,
             "peak_joint_speed_rad_s": p.peak_joint_speed_rad_s,
             "clearance_mm": p.clearance_mm, "closest_mm": p.closest_mm,
             "time_to_contact_s": p.time_to_contact_s}
            for z, p in zip(B.STRIKE_ZONES, probes, strict=True)]


def yaw_sweep() -> list[dict]:
    """Move ONLY joint_RFCoxa_yaw toward the contact poses, leave the other
    four where the stance in use puts them, and see what stops the swing from
    being shorter. This is a diagnostic, not a candidate: it says which of the
    five criteria actually binds, which the search result alone would not."""
    import numpy as np

    from flyohtani.world.poses import fastest_feasible_swing

    joints = list(B.ACTIVE_JOINTS)
    poses = list(B.CONTACT_POSES.values())
    q_ready = np.array([B.READY_POSE[j] for j in joints])
    q_contact = np.mean([[c[j] for j in joints] for c in poses], axis=0)
    yaw = joints.index("joint_RFCoxa_yaw")
    rows = []
    for gap_deg in (45.0, 60.0, 90.0, 120.0, 150.0, 180.0, 195.0, 210.0, 260.6):
        q = q_ready.copy()
        q[yaw] = q_contact[yaw] - math.radians(gap_deg)
        ready = dict(zip(joints, q, strict=True))
        duration, probes = fastest_feasible_swing(
            ready, poses, scene=B.build_scene(), follow=B.DEMO_SWING_FOLLOW,
            ceiling_rad_s=CEILING_RAD_S, dt_s=2.5e-5, attack_range_deg=ATTACK_RANGE_DEG,
            speed_floor_mm_s=SPEED_FLOOR_MM_S, tracking_tol_mm=TRACKING_TOL_MM,
            max_duration_s=B.DEMO_SWING_S)
        row = {"yaw_gap_deg": gap_deg, "feasible": duration is not None,
               "duration_s": duration}
        if probes:
            row |= {"min_speed_mm_s": min(p.speed_mm_s for p in probes),
                    "attack_min_deg": min(p.attack_deg for p in probes),
                    "attack_max_deg": max(p.attack_deg for p in probes),
                    "min_clearance_mm": min(p.clearance_mm for p in probes),
                    "max_closest_mm": max(p.closest_mm for p in probes)}
        rows.append(row)
    return rows


def run(seed: int, restarts: int = 24, iterations: int = 40) -> dict:
    poses = list(B.CONTACT_POSES.values())
    t0 = time.time()
    duration, ready, probes = find_fast_ready_pose(
        B.CONTACT_POSES, seed=seed, restarts=restarts, iterations=iterations,
        ceiling_rad_s=CEILING_RAD_S, attack_range_deg=ATTACK_RANGE_DEG,
        speed_floor_mm_s=SPEED_FLOOR_MM_S, tracking_tol_mm=TRACKING_TOL_MM)
    if ready is None or not math.isfinite(duration):
        return {"seed": seed, "found": False, "seconds": time.time() - t0}
    travel = max(abs(c[j] - ready[j]) for c in poses for j in B.ACTIVE_JOINTS)
    return {
        "seed": seed, "found": True, "seconds": time.time() - t0,
        "duration_s": duration,
        "max_joint_travel_deg": math.degrees(travel),
        "ready_pose_deg": {j: math.degrees(v) for j, v in ready.items()},
        "swing_to_contact_s": max(p.time_to_contact_s for p in probes),
        "zones": _zone_rows(probes),
    }


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sq = status_quo()
    print(f"status quo: swing {sq['duration_s']*1e3:.1f} ms "
          f"(analytic minimum {sq['analytic_minimum_s']*1e3:.1f} ms), "
          f"largest joint travel {sq['max_joint_travel_deg']:.1f} deg")
    for r in sq["zones"]:
        print(f"  {r['zone']:7s} speed={r['speed_mm_s']:6.1f} attack={r['attack_deg']:+6.2f} "
              f"peak_q={r['peak_joint_speed_rad_s']:6.1f} clear={r['clearance_mm']:.3f} "
              f"closest={r['closest_mm']:.4f} contact_at={r['time_to_contact_s']*1e3:5.2f}ms")
    print()
    print("yaw-only sweep -- which criterion binds as the path shortens:")
    sweep = yaw_sweep()
    for r in sweep:
        if r["feasible"]:
            print(f"  gap {r['yaw_gap_deg']:6.1f}d -> {r['duration_s']*1e3:6.2f} ms  FEASIBLE")
        elif "attack_min_deg" in r:
            print(f"  gap {r['yaw_gap_deg']:6.1f}d -> blocked: speed {r['min_speed_mm_s']:5.0f} "
                  f"attack [{r['attack_min_deg']:+5.1f},{r['attack_max_deg']:+5.1f}] "
                  f"clear {r['min_clearance_mm']:.2f} closest {r['max_closest_mm']:.3f}")
        else:
            print(f"  gap {r['yaw_gap_deg']:6.1f}d -> rejected before simulating")
    print()
    result = run(seed)
    if not result["found"]:
        print(f"seed {seed}: no stance satisfied the criteria ({result['seconds']:.0f}s)")
    else:
        print(f"seed {seed}: swing {result['duration_s']*1e3:.2f} ms "
              f"(was {sq['duration_s']*1e3:.1f}), largest travel "
              f"{result['max_joint_travel_deg']:.1f} deg (was {sq['max_joint_travel_deg']:.1f}), "
              f"swing->contact {result['swing_to_contact_s']*1e3:.2f} ms "
              f"(was {B.SWING_TO_CONTACT_S*1e3:.2f})  [{result['seconds']:.0f}s]")
        for r in result["zones"]:
            print(f"  {r['zone']:7s} speed={r['speed_mm_s']:6.1f} attack={r['attack_deg']:+6.2f} "
                  f"peak_q={r['peak_joint_speed_rad_s']:6.1f} clear={r['clearance_mm']:.3f} "
                  f"closest={r['closest_mm']:.4f} contact_at={r['time_to_contact_s']*1e3:5.2f}ms")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"FAST-SWING-seed{seed}.json"
    out.write_text(json.dumps({"criteria": {
        "ceiling_rad_s": CEILING_RAD_S, "attack_range_deg": list(ATTACK_RANGE_DEG),
        "speed_floor_mm_s": SPEED_FLOOR_MM_S, "tracking_tol_mm": TRACKING_TOL_MM},
        "status_quo": sq, "yaw_sweep": sweep, "result": result}, indent=1) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()

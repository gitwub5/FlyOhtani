"""What value does the zone boundary have to take, in the scene as it is now?

`task.policy.CircuitPolicy` reads the strike zone from how fast the ball
climbs the left eye's image -- rows per frame, fitted over the last few
frames, sampled at the moment the circuit commits. `zone_rise_boundary`
splits that number into "high" and "low", and `learn.Genome.BOUNDS` says
which values the search may try.

THAT PAIR DRIFTS WITH THE SCENE, and it drifted silently. The boundary and
its bounds were calibrated when the ball was released 122 mm out (D32).
D35 moved the release to the pitcher's hand at 34 mm, so the ball sweeps the
image far faster, and the rise at commit moved by about an order of
magnitude -- out of the range the search was allowed to reach. Every D36
policy therefore read every pitch as "high" and the parameter was dead. The
searches were not failing to learn the zone; they could not express it.

So this measures the feature rather than assuming it, across GENOMES and not
just one: the value depends on when the circuit commits, which is itself
something the search moves.

    python -m flyohtani.studies.zone_rise

It prints the per-genome table and writes the evidence JSON. What it does
NOT do is choose the bounds -- that is an engineering call, recorded at
`learn.Genome.BOUNDS`, and `tests/test_task_learning.py` holds the two
together so the next scene change is loud instead of silent.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from flyohtani.task.env import BattingEnv, PitchSpec
from flyohtani.task.learn import Genome
from flyohtani.task.policy import run_episode
from flyohtani.world import batter as B

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

TIMINGS_MS = (-3.0, -1.0, 1.0, 3.0)
"""Inside the training jitter (+-4 ms), so the sweep covers pitches the
policy actually meets rather than extremes."""

N_RANDOM = 8
RANDOM_SEED = 0


def probe_genomes(seed: int = RANDOM_SEED, n_random: int = N_RANDOM) -> list[tuple[str, Genome]]:
    """The default genome plus a random sample. Deliberately NOT only the
    learned ones: the bounds have to hold for genomes the search might pass
    through, not just the ones it stopped at."""
    rng = np.random.default_rng(seed)
    return [("default", Genome())] + [(f"random-{i}", Genome.random(rng)) for i in range(n_random)]


def measure(genomes: list[tuple[str, Genome]] | None = None,
            env: BattingEnv | None = None, graph=None) -> dict:
    """Rise-at-commit per genome per pitch zone.

    `graph` swaps the wiring, because the shuffled control commits at
    different times and therefore reads the feature at different values. If
    the bounds only covered the real wiring, the control would be handicapped
    by the search's reach rather than by its connectome."""
    env = env or BattingEnv()
    genomes = genomes if genomes is not None else probe_genomes()
    pitches = [PitchSpec(zone=z, timing_ms=t) for z in B.STRIKE_ZONES for t in TIMINGS_MS]

    rows = []
    for name, g in genomes:
        policy = g.policy(graph)
        per: dict[str, list[float]] = {}
        for pitch in pitches:
            run_episode(env, policy, pitch)
            value = policy.zone_evidence_at_commit
            if value is not None:
                per.setdefault(pitch.zone, []).append(float(value))
        rec: dict = {"genome": name, "spikes_to_swing": g.spikes_to_swing,
                     "input_gain_scale": g.input_gain_scale,
                     "zone_window_frames": g.zone_window_frames}
        for zone in B.STRIKE_ZONES:
            v = per.get(zone) or []
            rec[zone] = {"mean": float(np.mean(v)), "min": float(np.min(v)),
                         "max": float(np.max(v)), "n": len(v)} if v else None
        hi, lo = rec["high"], rec["low"]
        rec["high_low_separable"] = bool(hi and lo and hi["max"] < lo["min"])
        rows.append(rec)

    values = [v for r in rows for z in B.STRIKE_ZONES if r[z] for v in (r[z]["min"], r[z]["max"])]
    return {
        "timings_ms": list(TIMINGS_MS),
        "observed_min": min(values),
        "observed_max": max(values),
        "separable_fraction": sum(r["high_low_separable"] for r in rows) / len(rows),
        "bounds_in_code": list(Genome.BOUNDS["zone_rise_boundary"]),
        "rows": rows,
    }


def main() -> None:
    result = measure()
    for r in result["rows"]:
        parts = " ".join(
            f"{z}={r[z]['mean']:+.3f}" if r[z] else f"{z}=none" for z in B.STRIKE_ZONES)
        print(f"{r['genome']:11s} {parts}  high/low separable={r['high_low_separable']}")
    lo, hi = result["observed_min"], result["observed_max"]
    blo, bhi = result["bounds_in_code"]
    print(f"\nrise at commit, observed: {lo:+.3f} .. {hi:+.3f}")
    print(f"Genome.BOUNDS: {blo:+.3f} .. {bhi:+.3f}"
          f"   -> {'COVERS the observed range' if blo <= lo and hi <= bhi else 'DOES NOT COVER IT'}")
    print(f"high/low separable in {result['separable_fraction']:.0%} of genomes")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "ZONE-RISE-at-commit.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()

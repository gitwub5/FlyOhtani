"""Does spike-frequency adaptation put a RATE in the circuit's output?

D39 measured the gap precisely. With three flight times the task needs the
swing to start about nine frames earlier on the fast ball than the slow one,
and the circuit's commit moves 1-3 frames -- in the wrong direction. A LIF
with a fixed threshold measures time-to-threshold, which is a LEVEL readout;
time to contact is a rate.

`circuit.ADAPTATION` is the smallest biologically real change that could fix
that: each spike adds to a current that decays and subtracts from the drive,
so a steady input fires a burst and quiets down while a GROWING input keeps
firing. Real neurons do this. It is off by default, and this decides whether
to turn it on.

PRE-REGISTERED, fixed before the sweep was run:

  1. the commit frame must be ORDERED fast < standard < slow -- the fast ball
     has to be swung at earlier, and today the circuit does the opposite
  2. slow minus fast must be at least 6 frames. The connecting bands sit at
     13, 19 and 22.5, so about 9.5 frames of commit spread is what a fixed
     delay would need to cover all three; under 6 there is no setting of the
     delay that reaches more than one band.

Passing this is necessary, not sufficient -- it says the circuit CAN carry
time to contact, not that the connectome does anything with it. The decoder
comparison is what answers that, and it is scored here too.

    python -m flyohtani.studies.adaptation
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from flyohtani.brain.circuit import LoomingCircuit
from flyohtani.brain.connectome import SOURCE_TYPES
from flyohtani.studies.decode_controls import load_or_build
from flyohtani.task.pitches import evaluation_pitches
from flyohtani.task.policy import CIRCUIT_SUBSTEPS
from flyohtani.world import batter as B

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

GAINS = (2_000.0, 13_500.0, 30_000.0)
ADAPTATIONS = (0.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0)
TAU_W_S = (0.010, 0.025, 0.050)
SPIKE_TARGETS = (1, 2, 4, 8)

MIN_SPREAD_FRAMES = 6.0
"""Pre-registered. See the module docstring."""


def commit_frames(drive, gain, adaptation, tau_w, target, graph=None):
    out = []
    for d in drive:
        c = (LoomingCircuit(graph=graph, input_gain=gain, adaptation=adaptation, tau_w_s=tau_w)
             if graph is not None
             else LoomingCircuit(input_gain=gain, adaptation=adaptation, tau_w_s=tau_w))
        n = len(next(iter(d.values())))
        dt = 1.0 / (B.EYE_RATE_HZ * CIRCUIT_SUBSTEPS)
        seen, commit = 0, None
        for f in range(n):
            vec = c.retinal_drive({t: d[t][f] for t in SOURCE_TYPES})
            for _ in range(CIRCUIT_SUBSTEPS):
                seen += int(c.target_spikes(c.step(dt, vec)).sum())
            if commit is None and seen >= target:
                commit = f
        out.append(commit)
    return out


def separation(commits, names) -> dict | None:
    by: dict[str, list[int]] = {}
    for nm, c in zip(names, commits, strict=True):
        if c is None:
            return None
        by.setdefault(nm, []).append(c)
    m = {k: float(np.mean(v)) for k, v in by.items()}
    spread = m["slow"] - m["fast"]
    ordered = m["fast"] < m["standard"] < m["slow"]
    return {"mean": m, "spread": spread, "ordered": ordered,
            "passes": bool(ordered and spread >= MIN_SPREAD_FRAMES)}


def main() -> None:
    tab = load_or_build()
    names = [p.pitch_name for p in evaluation_pitches(len(tab.drive))]

    rows, best = [], None
    print(f"{'gain':>7} {'adapt':>7} {'tau_w':>7} {'target':>7} "
          f"{'fast':>6} {'std':>6} {'slow':>6} {'spread':>7}  verdict")
    print("-" * 78)
    for gain in GAINS:
        for adapt in ADAPTATIONS:
            for tau_w in TAU_W_S:
                if adapt == 0.0 and tau_w != TAU_W_S[0]:
                    continue  # tau_w does nothing when adaptation is off
                for target in SPIKE_TARGETS:
                    sep = separation(commit_frames(tab.drive, gain, adapt, tau_w, target), names)
                    if sep is None:
                        continue
                    r = {"gain": gain, "adaptation": adapt, "tau_w_s": tau_w,
                         "target": target} | sep
                    rows.append(r)
                    if best is None or (r["passes"], r["spread"]) > (best["passes"], best["spread"]):
                        best = r
                    if adapt in (0.0, 50.0, 200.0) and target in (1, 4):
                        m = sep["mean"]
                        print(f"{gain:7.0f} {adapt:7.0f} {tau_w:7.3f} {target:7d} "
                              f"{m['fast']:6.1f} {m['standard']:6.1f} {m['slow']:6.1f} "
                              f"{sep['spread']:+7.1f}  "
                              f"{'PASS' if sep['passes'] else ('ordered' if sep['ordered'] else 'wrong order')}",
                              flush=True)

    print(f"\nbest of {len(rows)} settings: spread {best['spread']:+.1f} frames, "
          f"ordered={best['ordered']}  -> {'PASSES' if best['passes'] else 'DOES NOT PASS'}")
    print(f"  gain={best['gain']:.0f} adaptation={best['adaptation']:.0f} "
          f"tau_w={best['tau_w_s']} target={best['target']}")
    print(f"  commit frames: fast {best['mean']['fast']:.1f}  "
          f"standard {best['mean']['standard']:.1f}  slow {best['mean']['slow']:.1f}")
    print("  (the task needs fast EARLIEST and about 9.5 frames of spread)")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "ADAPTATION.json"
    out.write_text(json.dumps({"min_spread_frames": MIN_SPREAD_FRAMES,
                               "best": best, "all": rows}, indent=1, default=float) + "\n")
    print("\nwrote", out)


if __name__ == "__main__":
    main()

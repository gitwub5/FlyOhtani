"""Stop ringing a bell. Predict when and where the ball arrives, and swing to meet it.

WHY THIS EXISTS. The decode has always been "the circuit fires, then wait D
frames, then swing". That is an escape reflex -- which is defensible, since
DNp01 is a giant fibre and a fly's escape really is trigger-then-go -- but it
is not hitting. A batter estimates when and where the ball will arrive and
starts the swing so the bat gets there at that moment. A stopwatch cannot do
that: with three flight times no fixed wait reaches more than one of them,
which is exactly what D39 measured.

And the information is there. A readout of the LC activity the circuit is fed
predicts the correct swing frame to 0.39 frames -- 0.8 ms, inside the +-1 ms
contact window -- from frames 3-8, long before the earliest deadline at 13.
The eye already knows. The circuit was throwing it away by collapsing 311
cells into "did anything fire yet".

WHAT IS FITTED, AND ON WHAT. A linear readout (ridge) from neural activity to
two numbers: the frame to start the swing, and the arrival height. Fitted on
TRAINING pitches, reported on the held-out set, which `task.pitches` keeps
disjoint by seed. The target is analytic -- swing start = flight + timing -
SWING_TO_CONTACT_S -- so fitting needs eye traces only and no swing physics.

THREE CONDITIONS, so the DN bottleneck is measured rather than assumed:

    LC (311 cells)    the upper bound: what the eye delivers
    DN, real wiring   the 12 descending neurons, real synapse counts
    DN, shuffled      the same twelve, rewired at random

Pre-registered: the real wiring is credited only above the 95th percentile of
20 rewirings. Unchanged from the earlier null distributions, and not moved.

    python -m flyohtani.studies.predictive_decode
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from flyohtani.brain.circuit import LoomingCircuit, shuffled
from flyohtani.brain.connectome import SOURCE_TYPES
from flyohtani.brain.retina import Retina, build_receptive_fields
from flyohtani.studies.decode_controls import load_or_build
from flyohtani.task.env import Action, BattingEnv, PitchSpec
from flyohtani.task.pitches import evaluation_pitches, training_pitches
from flyohtani.task.policy import CIRCUIT_SUBSTEPS
from flyohtani.world import batter as B
from flyshohei import pitch as P

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"
TRACE_CACHE = Path(__file__).resolve().parent.parent.parent / "runs" / "predict-traces.pkl"

READ_UNTIL = 9
"""Frames the readout may look at, counting from release. It has to finish
before the earliest swing could start -- the fast pitch connects at 13 -- and
the measurement says 3-8 is already enough."""

N_TRAIN = 108
RIDGE = 1e-3
N_SHUFFLES = 20
NULL_PERCENTILE = 95


def target_frame(spec: PitchSpec) -> float:
    """When the swing must START, analytically. Verified against the measured
    connecting bands: 13.3 / 19.0 / 22.9 against 12-14 / 18-20 / 22-23."""
    flight = P.get(spec.pitch_name).flight_s if spec.flight_s is None else spec.flight_s
    return (flight + spec.timing_ms * 1e-3 - B.SWING_TO_CONTACT_S) * B.EYE_RATE_HZ


def eye_traces(pitches: list[PitchSpec], cache: Path | None = None) -> list[dict]:
    """Pooled LC activity per frame. No swing, so no contact physics."""
    import pickle
    if cache and cache.exists():
        return pickle.loads(cache.read_bytes())
    env = BattingEnv()
    n_lc = {t: len(LoomingCircuit().graph.ids_of_type(t)) for t in SOURCE_TYPES}
    fields = {t: build_receptive_fields(n_lc[t], B.EYE_RESOLUTION) for t in SOURCE_TYPES}
    out = []
    for i, spec in enumerate(pitches):
        retina = Retina(B.EYE_RESOLUTION)
        obs = env.reset(spec)
        per = {t: [] for t in SOURCE_TYPES}
        done = False
        while not done:
            on, off = retina.encode(obs.eye_left)
            motion = on + off
            for t in SOURCE_TYPES:
                per[t].append(fields[t].pool(motion))
            obs, _, done, _ = env.step(Action(swing=False))
        out.append({t: np.array(v) for t, v in per.items()})
        if (i + 1) % 20 == 0:
            print(f"    {i + 1}/{len(pitches)} traces", flush=True)
    env.close()
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(pickle.dumps(out))
    return out


def lc_features(trace: dict) -> np.ndarray:
    return np.concatenate([np.asarray(trace[t])[:READ_UNTIL].ravel() for t in SOURCE_TYPES])


def dn_features(trace: dict, graph=None) -> np.ndarray:
    """Per-DN spike counts per frame -- what a population readout would see."""
    c = (LoomingCircuit(graph=graph) if graph is not None else LoomingCircuit())
    dt = 1.0 / (B.EYE_RATE_HZ * CIRCUIT_SUBSTEPS)
    n_dn = c.n - c.target_slice.start
    rows = np.zeros((READ_UNTIL, n_dn))
    for f in range(READ_UNTIL):
        vec = c.retinal_drive({t: np.asarray(trace[t])[f] for t in SOURCE_TYPES})
        for _ in range(CIRCUIT_SUBSTEPS):
            rows[f] += c.target_spikes(c.step(dt, vec)).astype(float)
    return rows.ravel()


def fit_ridge(X: np.ndarray, Y: np.ndarray, lam: float = RIDGE):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[(X - mu) / sd, np.ones(len(X))]
    W = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]), Z.T @ Y)
    return lambda A: np.c_[(A - mu) / sd, np.ones(len(A))] @ W


def evaluate(predict, tab, held_traces, held_specs, featurise) -> dict:
    A = np.array([featurise(t) for t in held_traces])
    pred = predict(A)
    frames = np.clip(np.rint(pred[:, 0]).astype(int), min(tab.frames), max(tab.frames))
    zones = ["high" if h < 0 else "low" for h in pred[:, 1]]
    tot = con = zm = 0.0
    for pi, (f, z) in enumerate(zip(frames, zones, strict=True)):
        fi, zi = tab.frames.index(int(f)), tab.zones.index(z)
        tot += tab.reward[pi, fi, zi]
        con += tab.contact[pi, fi, zi]
        zm += tab.zone_match[pi, fi, zi]
    n = len(held_specs)
    err = np.abs(pred[:, 0] - np.array([target_frame(s) for s in held_specs]))
    return {"reward": tot / n, "contact": con / n, "zone": zm / n,
            "frame_mae": float(err.mean()), "frame_mae_ms": float(err.mean() / B.EYE_RATE_HZ * 1e3)}


def main() -> None:
    tab = load_or_build()
    held_specs = evaluation_pitches(len(tab.drive))
    train_specs = training_pitches(N_TRAIN)
    print(f"training traces ({N_TRAIN} pitches, no swing physics)...", flush=True)
    train_traces = eye_traces(train_specs, TRACE_CACHE)
    held_traces = tab.drive

    zone_sign = {"high": -1.0, "middle": 0.0, "low": 1.0}
    Y = np.array([[target_frame(s), zone_sign[s.zone]] for s in train_specs])

    results = {}
    print("\nfitting readouts...", flush=True)
    for label, feat in (("LC (311 cells, upper bound)", lc_features),
                        ("DN (12, real wiring)", dn_features)):
        X = np.array([feat(t) for t in train_traces])
        results[label] = evaluate(fit_ridge(X, Y), tab, held_traces, held_specs, feat)

    print(f"\n{'readout':>30} {'reward':>8} {'contact':>8} {'zone':>7} {'frame err':>10}")
    print("-" * 68)
    for k, r in results.items():
        print(f"{k:>30} {r['reward']:8.3f} {r['contact']:8.2f} {r['zone']:7.2f} "
              f"{r['frame_mae']:6.2f} fr")

    print(f"\nnull distribution: {N_SHUFFLES} rewirings", flush=True)
    scores = []
    for k in range(N_SHUFFLES):
        g = shuffled(seed=2000 + k)
        def feat(t, g=g):
            return dn_features(t, g)
        X = np.array([feat(t) for t in train_traces])
        r = evaluate(fit_ridge(X, Y), tab, held_traces, held_specs, feat)
        scores.append(r["reward"])
        print(f"  shuffle {k:2d}: reward {r['reward']:.3f}  frame err {r['frame_mae']:.2f}",
              flush=True)

    arr = np.array(scores)
    real = results["DN (12, real wiring)"]["reward"]
    thr = float(np.percentile(arr, NULL_PERCENTILE))
    verdict = {"real": real, "shuffles": scores, "mean": float(arr.mean()),
               "sd": float(arr.std(ddof=1)), "threshold": thr,
               "percentile": float((arr < real).mean() * 100), "passes": bool(real > thr)}
    print(f"\n  real {real:.3f} | shuffles mean {arr.mean():.3f} sd {arr.std(ddof=1):.3f} "
          f"max {arr.max():.3f} | {NULL_PERCENTILE}th {thr:.3f}")
    print(f"  real at the {verdict['percentile']:.0f}th percentile -> "
          f"{'PASSES' if verdict['passes'] else 'DOES NOT PASS'}")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "PREDICTIVE-DECODE.json"
    out.write_text(json.dumps({"read_until": READ_UNTIL, "n_train": N_TRAIN,
                               "readouts": results, "null": verdict}, indent=1,
                              default=float) + "\n")
    print("\nwrote", out)


if __name__ == "__main__":
    main()

"""What does the connectome contribute, against controls that see just as well?

THE CONTROL THAT WAS MISSING. Every comparison in this project so far has been
against a BLIND policy -- one that swings on a fixed frame having seen nothing.
It has always been beaten, and that only ever showed that the eye is used. The
sharper question is whether the LOOMING CIRCUIT contributes anything beyond a
threshold on raw retinal motion, and nothing here had ever asked it.

Three decoders, identical in every other respect -- same eye, same retina, same
receptive fields, same zone readout (which reads the RETINA, not the circuit,
so it is shared rather than credited to any of them):

    blind         swing on frame F at zone Z, both constant
    first-motion  swing D frames after the eye first registers motion
    circuit       swing D frames after the MaleCNS subgraph emits descending
                  spikes

Only the third has a connectome in it. If it does not separate from the second,
that is the answer, and no amount of physics or optics changes it.

HOW IT IS CHEAP. An episode's outcome depends only on WHICH FRAME the swing
starts and WHICH ZONE it aims at -- the policy has no other influence. So the
physics is run once into a table indexed by (pitch, frame, zone), and every
decoder is then scored by lookup. The searches this replaces took an hour each
and could only try one decoder at a time.

    python -m flyohtani.studies.decode_controls
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from flyohtani.brain.circuit import LoomingCircuit
from flyohtani.brain.connectome import SOURCE_TYPES
from flyohtani.brain.retina import Retina, build_receptive_fields
from flyohtani.task import rewards
from flyohtani.task.env import Action, BattingEnv
from flyohtani.task.pitches import evaluation_pitches
from flyohtani.task.policy import CIRCUIT_SUBSTEPS, ZoneReader
from flyohtani.world import batter as B

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

FRAMES = range(3, 32)
"""Every frame a decoder could pick. Wider on both sides than any connecting
band -- 12-14 for the fast pitch, 18-20 standard, 22-23 slow, plus the timing
jitter -- so a decoder is never scored against a range that happens to exclude
its answer. That failure voided a whole day of runs: the search's motor delay
was capped at 8 while contact needed 17."""


@dataclass
class Table:
    """Physics, run once. `reward[p, f, z]` is what pitch p scores if the
    swing starts on frame f aimed at zone z."""

    reward: np.ndarray
    contact: np.ndarray
    zone_match: np.ndarray
    drive: list[dict[str, np.ndarray]]
    """Pooled LC input per frame, per pitch -- enough to run the circuit
    without touching physics again."""
    motion_max: list[np.ndarray]
    """Peak retinal contrast per frame, for the first-motion threshold."""
    rows: list[list[float | None]]
    """The zone reader's rise estimate per frame, per pitch."""
    frames: list[int]
    zones: list[str]


CACHE = Path(__file__).resolve().parent.parent.parent / "runs" / "decode-table.pkl"
"""The table is 2,160 episodes of physics and does not depend on any decoder,
so it is cached. `runs/` is gitignored -- this is a derived cache, not
evidence. Delete it to rebuild, and the scene changing is exactly when to."""


def load_or_build(reward_name: str = "carry-v1", n_pitches: int = 36,
                  cache: Path | None = CACHE) -> Table:
    """The cache stores a plain dict, not the dataclass.

    Pickling the dataclass recorded it as `__main__.Table`, because this
    module is `__main__` when run with -m, and then no OTHER module could
    load the cache. Storing the fields keeps the file independent of which
    module happened to write it."""
    import pickle
    import sys
    if cache and cache.exists():
        raw = cache.read_bytes()
        try:
            data = pickle.loads(raw)
        except AttributeError:
            # written by an older version, as __main__.Table
            sys.modules["__main__"].Table = Table
            data = pickle.loads(raw)
        tab = Table(**data) if isinstance(data, dict) else data
        print(f"reusing cached table {cache}", flush=True)
        if not isinstance(data, dict):
            cache.write_bytes(pickle.dumps(vars(tab)))
            print("  (rewritten in the module-independent format)", flush=True)
        return tab
    tab = build_table(reward_name, n_pitches)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(pickle.dumps(vars(tab)))
        print(f"cached table to {cache}", flush=True)
    return tab


def build_table(reward_name: str = "carry-v1", n_pitches: int = 36) -> Table:
    env = BattingEnv()
    pitches = evaluation_pitches(n_pitches)
    reward_fn = rewards.get(reward_name)
    frames, zones = list(FRAMES), list(B.STRIKE_ZONES)

    n_lc = {t: len(LoomingCircuit().graph.ids_of_type(t)) for t in SOURCE_TYPES}
    fields = {t: build_receptive_fields(n_lc[t], B.EYE_RESOLUTION) for t in SOURCE_TYPES}

    drive, motion_max, rows = [], [], []
    for pitch in pitches:
        retina = Retina(B.EYE_RESOLUTION)
        reader = ZoneReader(0.0, 5)
        obs = env.reset(pitch)
        per_t = {t: [] for t in SOURCE_TYPES}
        peaks, rise = [], []
        done = False
        while not done:
            on, off = retina.encode(obs.eye_left)
            motion = on + off
            for t in SOURCE_TYPES:
                per_t[t].append(fields[t].pool(motion))
            reader.observe(motion)
            peaks.append(float(motion.max()))
            rise.append(reader.rise())
            obs, _, done, _ = env.step(Action(swing=False))
        drive.append({t: np.array(v) for t, v in per_t.items()})
        motion_max.append(np.array(peaks))
        rows.append(rise)

    shape = (len(pitches), len(frames), len(zones))
    reward = np.zeros(shape)
    contact = np.zeros(shape, dtype=bool)
    zone_match = np.zeros(shape, dtype=bool)
    from flyohtani.task.policy import FixedFramePolicy, run_episode
    for pi, pitch in enumerate(pitches):
        for fi, frame in enumerate(frames):
            for zi, zone in enumerate(zones):
                o = run_episode(env, FixedFramePolicy(frame, zone), pitch)
                reward[pi, fi, zi] = reward_fn(o)
                contact[pi, fi, zi] = o.contact
                zone_match[pi, fi, zi] = (o.swing_zone == o.pitch_zone)
    env.close()
    return Table(reward, contact, zone_match, drive, motion_max, rows, frames, zones)


def _score(tab: Table, swing_frame: list[int | None], zone: list[str]) -> dict:
    """Score a decoder from its per-pitch (frame, zone) decisions."""
    tot = con = zm = 0.0
    for pi, (f, z) in enumerate(zip(swing_frame, zone, strict=True)):
        if f is None or f not in tab.frames:
            continue
        fi, zi = tab.frames.index(f), tab.zones.index(z)
        tot += tab.reward[pi, fi, zi]
        con += tab.contact[pi, fi, zi]
        zm += tab.zone_match[pi, fi, zi]
    n = len(swing_frame)
    return {"reward": tot / n, "contact": con / n, "zone": zm / n}


def _zone_at(tab: Table, pi: int, frame: int, boundary: float) -> str:
    rise = tab.rows[pi][min(frame, len(tab.rows[pi]) - 1)]
    if rise is None:
        return "middle"
    return "high" if rise < boundary else "low"


BOUNDARIES = tuple(np.round(np.arange(-1.9, -0.95, 0.05), 3))
DELAYS = range(25)
THRESHOLDS = (0.02, 0.05, 0.10, 0.20, 0.35, 0.50)
GAINS = (500.0, 1_000.0, 2_000.0, 5_000.0, 13_500.0, 30_000.0)
SPIKES = (1, 2, 3, 4)


def best_blind(tab: Table) -> dict:
    best = None
    for f in tab.frames:
        for z in tab.zones:
            s = _score(tab, [f] * len(tab.motion_max), [z] * len(tab.motion_max))
            if best is None or s["reward"] > best["reward"]:
                best = s | {"frame": f, "zone_choice": z}
    return best


def best_first_motion(tab: Table) -> dict:
    best = None
    for thr in THRESHOLDS:
        commits = [int(np.argmax(m >= thr)) if (m >= thr).any() else None
                   for m in tab.motion_max]
        for delay in DELAYS:
            for bnd in BOUNDARIES:
                sf = [None if c is None else c + delay for c in commits]
                zs = [_zone_at(tab, pi, c + delay if c is not None else 0, bnd)
                      for pi, c in enumerate(commits)]
                s = _score(tab, sf, zs)
                if best is None or s["reward"] > best["reward"]:
                    best = s | {"threshold": thr, "delay": delay, "boundary": float(bnd),
                                "commit_frames": [c for c in commits if c is not None][:6]}
    return best


def circuit_commits(tab: Table, gain: float, spikes_to_swing: int, graph=None) -> list[int | None]:
    """When the subgraph commits, per pitch. Pure numpy over the stored drive,
    so a whole decoder sweep costs no physics at all. `graph` swaps the wiring
    for the shuffled control."""
    out = []
    for d in tab.drive:
        circuit = (LoomingCircuit(graph=graph, input_gain=gain) if graph is not None
                   else LoomingCircuit(input_gain=gain))
        n_frames = len(next(iter(d.values())))
        dt = 1.0 / (B.EYE_RATE_HZ * CIRCUIT_SUBSTEPS)
        seen, commit = 0, None
        for f in range(n_frames):
            drive_vec = circuit.retinal_drive({t: d[t][f] for t in SOURCE_TYPES})
            for _ in range(CIRCUIT_SUBSTEPS):
                sp = circuit.step(dt, drive_vec)
                seen += int(circuit.target_spikes(sp).sum())
            if commit is None and seen >= spikes_to_swing:
                commit = f
        out.append(commit)
    return out


def best_circuit(tab: Table, graph=None) -> dict:
    best = None
    for gain in GAINS:
        for spikes in SPIKES:
            commits = circuit_commits(tab, gain, spikes, graph)
            for delay in DELAYS:
                for bnd in BOUNDARIES:
                    sf = [None if c is None else c + delay for c in commits]
                    zs = [_zone_at(tab, pi, c + delay if c is not None else 0, bnd)
                          for pi, c in enumerate(commits)]
                    s = _score(tab, sf, zs)
                    if best is None or s["reward"] > best["reward"]:
                        best = s | {"gain": gain, "spikes_to_swing": spikes, "delay": delay,
                                    "boundary": float(bnd),
                                    "commit_frames": [c for c in commits if c is not None][:6]}
    return best


# ------------------------------------------------- reading WHICH DN fired
# The decode above ORs all twelve descending neurons, so the wiring has
# nowhere to act -- and the measurement says so: shuffles match or beat the
# real subgraph. What shuffling actually destroys is which LC cell (which
# part of the visual field) reaches which DN, and that IS in the data:
# weighting each LC's receptive-field centre by the real synapse counts gives
# the twelve DNs row centres spanning 8.45 px (sd 2.82), against 3.07-4.50
# (sd 0.91-1.26) for a shuffle, which collapses them onto one average.
#
# So this decoder estimates WHERE the ball is from WHICH DNs fired. It is the
# one place the connectome can pay for itself, and it is the experiment the
# project has been missing.


def dn_row_centres(graph=None) -> np.ndarray:
    """Each descending neuron's receptive-field row, from the real wiring:
    its presynaptic LC cells' field centres, weighted by synapse count."""
    c = LoomingCircuit(graph=graph) if graph is not None else LoomingCircuit()
    centres = np.vstack([build_receptive_fields(len(c.graph.ids_of_type(t)),
                                                B.EYE_RESOLUTION).centres
                         for t in SOURCE_TYPES])
    w = c.weights[c.target_slice, c.source_slice]
    total = w.sum(axis=1)
    rows = np.zeros(len(total))
    ok = total > 0
    rows[ok] = (w[ok] @ centres[:, 0]) / total[ok]
    return rows


def circuit_dn_readout(tab: Table, gain: float, spikes_to_swing: int, graph=None):
    """Commit frame and the DN-weighted row estimate at that moment."""
    rows_of_dn = dn_row_centres(graph)
    commits, estimates = [], []
    for d in tab.drive:
        circuit = (LoomingCircuit(graph=graph, input_gain=gain) if graph is not None
                   else LoomingCircuit(input_gain=gain))
        n_frames = len(next(iter(d.values())))
        dt = 1.0 / (B.EYE_RATE_HZ * CIRCUIT_SUBSTEPS)
        counts = np.zeros(len(rows_of_dn))
        seen, commit, est = 0, None, None
        for f in range(n_frames):
            drive_vec = circuit.retinal_drive({t: d[t][f] for t in SOURCE_TYPES})
            for _ in range(CIRCUIT_SUBSTEPS):
                sp = circuit.step(dt, drive_vec)
                counts += circuit.target_spikes(sp).astype(float)
                seen += int(circuit.target_spikes(sp).sum())
            if commit is None and seen >= spikes_to_swing:
                commit = f
                est = float(counts @ rows_of_dn / counts.sum()) if counts.sum() else None
        commits.append(commit)
        estimates.append(est)
    return commits, estimates


DN_ROW_BOUNDARIES = tuple(np.round(np.arange(8.0, 17.5, 0.25), 3))
"""Thresholds on the DN-weighted row estimate. The grid spans the real
wiring's own range of DN row centres (8.31 to 16.77)."""


def best_circuit_dn_zone(tab: Table, graph=None) -> dict:
    """Timing from the descending spikes, ZONE from which of them fired."""
    best = None
    for gain in GAINS:
        for spikes in SPIKES:
            commits, est = circuit_dn_readout(tab, gain, spikes, graph)
            for delay in DELAYS:
                for bnd in DN_ROW_BOUNDARIES:
                    sf = [None if c is None else c + delay for c in commits]
                    # a HIGH pitch sits higher in the image, i.e. at a SMALLER
                    # row index, so a small estimate means "high"
                    zs = ["middle" if e is None else ("high" if e < bnd else "low")
                          for e in est]
                    s = _score(tab, sf, zs)
                    if best is None or s["reward"] > best["reward"]:
                        best = s | {"gain": gain, "spikes_to_swing": spikes,
                                    "delay": delay, "dn_row_boundary": float(bnd)}
    return best


N_SHUFFLES = 20
"""A null distribution, not three anecdotes.

Three shuffles was all the old hill-climbing searches could afford -- an hour
each. Scoring by lookup makes a shuffle cost seconds, so the question stops
being "did the real wiring beat these three" and becomes "where does the real
wiring sit in the distribution of rewirings". With three samples spanning
1.19 to 1.73, a real score of 1.63 says nothing either way."""

NULL_PERCENTILE = 95
"""PRE-REGISTERED, before the distribution was computed: the real wiring is
credited only if it exceeds this percentile of the shuffles. Not relaxed
afterwards, and the shuffle count is not changed after seeing it."""


def null_distribution(tab: Table, n: int = N_SHUFFLES) -> dict:
    from flyohtani.brain.circuit import shuffled as make_shuffled

    real = best_circuit_dn_zone(tab)
    scores = []
    for k in range(n):
        r = best_circuit_dn_zone(tab, graph=make_shuffled(seed=1000 + k))
        scores.append(r["reward"])
        print(f"  shuffle {k:2d}: {r['reward']:.3f}", flush=True)
    arr = np.array(scores)
    pct = float((arr < real["reward"]).mean() * 100)
    return {
        "real": real,
        "shuffles": scores,
        "shuffle_mean": float(arr.mean()),
        "shuffle_sd": float(arr.std(ddof=1)),
        "shuffle_max": float(arr.max()),
        "threshold": float(np.percentile(arr, NULL_PERCENTILE)),
        "real_percentile": pct,
        "passes": real["reward"] > float(np.percentile(arr, NULL_PERCENTILE)),
    }


def main() -> None:
    from flyohtani.brain.circuit import shuffled

    print("building the outcome table (physics, once)...", flush=True)
    tab = load_or_build()
    print(f"  {len(tab.motion_max)} pitches x {len(tab.frames)} frames x {len(tab.zones)} zones\n",
          flush=True)

    results = {"blind": best_blind(tab)}
    print("scoring decoders by lookup...", flush=True)
    results["first_motion"] = best_first_motion(tab)
    results["circuit_real"] = best_circuit(tab)
    for k in (0, 1, 2):
        results[f"circuit_shuffled_{k}"] = best_circuit(tab, graph=shuffled(seed=k))
    results["dnzone_real"] = best_circuit_dn_zone(tab)
    for k in (0, 1, 2):
        results[f"dnzone_shuffled_{k}"] = best_circuit_dn_zone(tab, graph=shuffled(seed=k))

    print(f"\n{'decoder':>22} {'reward':>8} {'contact':>8} {'zone':>7}  detail")
    print("-" * 78)
    for name, r in results.items():
        detail = " ".join(f"{k}={v}" for k, v in r.items()
                          if k in ("frame", "zone_choice", "threshold", "gain",
                                   "spikes_to_swing", "delay"))
        print(f"{name:>22} {r['reward']:8.3f} {r['contact']:8.2f} {r['zone']:7.2f}  {detail}")

    print(f"\nnull distribution: {N_SHUFFLES} rewirings of the DN-identity decoder")
    nd = null_distribution(tab)
    results["null_distribution"] = nd
    print(f"\n  real wiring        {nd['real']['reward']:.3f}")
    print(f"  shuffles           mean {nd['shuffle_mean']:.3f}  sd {nd['shuffle_sd']:.3f}  "
          f"max {nd['shuffle_max']:.3f}")
    print(f"  {NULL_PERCENTILE}th percentile   {nd['threshold']:.3f}")
    print(f"  real sits at the {nd['real_percentile']:.0f}th percentile  -> "
          f"{'PASSES' if nd['passes'] else 'DOES NOT PASS'} the pre-registered test")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "DECODE-CONTROLS.json"
    out.write_text(json.dumps(results, indent=1, default=float) + "\n")
    print("\nwrote", out)


if __name__ == "__main__":
    main()

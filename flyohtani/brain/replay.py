"""Feeding the brain viewer (viewer/, fly-connectome-template -- D30).

The viewer takes a "replay": frames of [MaleCNS bodyId, value in 0..1]. Its
own loader (viewer/src/lib/replay.ts) rejects anything malformed;
`validate_replay` mirrors those rules here so a bad file is caught before a
browser ever sees it.

What this module can export TODAY is wiring, not activity: no circuit is
simulated yet (Phase 4). `wiring_replay` therefore declares itself
`synthetic` and says, in its own `source` block, that the brightness is
synapse counts. When a simulation exists, `activity_replay` converts firing
rates with the viewer's documented convention (rate / 50 Hz, clamped).

    .venv/bin/python -m flyohtani.brain.replay --run runs/record/hit
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from flyohtani.brain.connectome import (
    SOURCE_TYPES,
    TARGET_TYPES,
    LoomingSubgraph,
    load_looming_subgraph,
)

REPO = Path(__file__).resolve().parent.parent.parent
VIEWER = REPO / "viewer"
BUNDLE = VIEWER / "public" / "experiment"

REPLAY_VERSION = 1
DATASET = "male-cns:v1.0"
MIN_FRAMES, MAX_FRAMES = 2, 10_000
RATE_FULL_SCALE_HZ = 50.0
"""The viewer's documented normalization: firing rate / 50 Hz, clamped."""
VISIBLE_GROUP_LIMIT = 3
"""Atlas groups below this are drawn (optic, central, descending)."""


def load_viewer_atlas(viewer: Path = VIEWER) -> dict[str, np.ndarray]:
    root = viewer / "public" / "data" / "brain-atlas"
    manifest = json.loads((root / "manifest.json").read_text())
    ids = np.frombuffer((root / "ids.bin").read_bytes(), dtype="<u4").astype(np.int64)
    groups = np.frombuffer((root / "groups.bin").read_bytes(), dtype="u1")
    positions = np.frombuffer((root / "positions.bin").read_bytes(), dtype="<f4").reshape(-1, 3)
    if not (len(ids) == len(groups) == len(positions) == manifest["count"]):
        raise ValueError("atlas file lengths do not match its manifest")
    return {"ids": ids, "groups": groups, "positions": positions, "manifest": manifest}


def visible_ids(atlas: Mapping[str, np.ndarray]) -> set[int]:
    return {int(b) for b, g in zip(atlas["ids"], atlas["groups"], strict=True) if g < VISIBLE_GROUP_LIMIT}


def validate_replay(replay: Mapping, visible: set[int]) -> None:
    """Same rules as the viewer's parseReplay. Raises ValueError."""
    if replay.get("version") != REPLAY_VERSION or replay.get("dataset") != DATASET:
        raise ValueError(f"expected replay version {REPLAY_VERSION} for {DATASET}")
    src = replay.get("source")
    if (not isinstance(src, Mapping) or src.get("kind") not in ("synthetic", "predicted", "measured")
            or not str(src.get("name", "")).strip() or not str(src.get("normalization", "")).strip()):
        raise ValueError("declare source kind, name and normalization")
    frames = replay.get("frames")
    if not isinstance(frames, Sequence) or not MIN_FRAMES <= len(frames) <= MAX_FRAMES:
        raise ValueError(f"supply {MIN_FRAMES} to {MAX_FRAMES} frames")
    previous = -1.0
    for frame in frames:
        t = frame.get("time")
        if not isinstance(t, (int, float)) or not np.isfinite(t) or t < 0 or t <= previous:
            raise ValueError("frame times must be finite, nonnegative and strictly increasing")
        previous = t
        seen: set[int] = set()
        for pair in frame.get("values", ()):
            if len(pair) != 2 or not isinstance(pair[0], int) or pair[0] not in visible:
                raise ValueError(f"not a visible MaleCNS brain body ID: {pair[0]!r}")
            if pair[0] in seen:
                raise ValueError(f"duplicate body ID in a frame: {pair[0]}")
            v = pair[1]
            if not isinstance(v, (int, float)) or not np.isfinite(v) or not 0 <= v <= 1:
                raise ValueError("values must be finite and within [0, 1]")
            seen.add(pair[0])
    if frames[0]["time"] != 0:
        raise ValueError("the first frame must start at time 0")


def _per_cell_synapses(graph: LoomingSubgraph) -> dict[int, int]:
    """Outgoing synapses for source cells, incoming for target cells --
    counted within this subgraph only."""
    total: dict[int, int] = {}
    for pre, post, w in zip(graph.body_pre, graph.body_post, graph.weight, strict=True):
        total[int(pre)] = total.get(int(pre), 0) + int(w)
        total[int(post)] = total.get(int(post), 0) + int(w)
    return total


WIRING_FLOOR = 0.35
"""Every circuit cell is drawn at least this bright, so weakly connected
cells are still visible; the rest of the range carries the synapse count."""


def wiring_replay(graph: LoomingSubgraph | None = None, hold_s: float = 1.5) -> dict:
    """Frames that light up the looming circuit type by type:
    anatomy only -> LC4 -> LPLC2 -> the descending neurons -> all together.
    Brightness is synapse count within the subgraph, normalised per cell
    type. NOT neural activity."""
    graph = graph or load_looming_subgraph()
    syn = _per_cell_synapses(graph)

    def layer(types: Sequence[str]) -> list[list[float]]:
        out = []
        for t in types:
            ids = [int(b) for b in graph.ids_of_type(t)]
            peak = max(syn[b] for b in ids)
            out += [[b, round(WIRING_FLOOR + (1 - WIRING_FLOOR) * syn[b] / peak, 4)] for b in ids]
        return out

    stages = [[], layer(["LC4"]), layer(["LPLC2"]), layer(TARGET_TYPES),
              layer([*SOURCE_TYPES, *TARGET_TYPES])]
    frames = [{"time": round(i * hold_s, 3), "values": v} for i, v in enumerate(stages)]
    frames.append({"time": round(len(stages) * hold_s, 3), "values": stages[-1]})
    return {
        "version": REPLAY_VERSION,
        "dataset": DATASET,
        "source": {
            "kind": "synthetic",
            "name": ("FlyOhtani looming circuit, WIRING ONLY (not activity): "
                     "LC4 -> LPLC2 -> DNp01/02/03/04/06/11 -> all"),
            "normalization": (f"{WIRING_FLOOR} + {1 - WIRING_FLOOR:.2f} x (synapses within the LC4/LPLC2->DN "
                              "subgraph / max for that cell type): outgoing for LC4/LPLC2, incoming for DNs. "
                              "No firing rates; no neuron is simulated."),
        },
        "frames": frames,
    }


def activity_replay(times_s: Sequence[float], rates_hz: Sequence[Mapping[int, float]], *,
                    kind: str, name: str) -> dict:
    """For when a circuit is simulated: one frame per time, rate / 50 Hz."""
    if len(times_s) != len(rates_hz):
        raise ValueError("one rate map per time")
    frames = [{"time": float(t),
               "values": [[int(b), float(min(max(r / RATE_FULL_SCALE_HZ, 0.0), 1.0))] for b, r in sorted(m.items())]}
              for t, m in zip(times_s, rates_hz, strict=True)]
    return {"version": REPLAY_VERSION, "dataset": DATASET,
            "source": {"kind": kind, "name": name,
                       "normalization": f"firing rate / {RATE_FULL_SCALE_HZ:g} Hz, clamped to [0, 1]"},
            "frames": frames}


def export_bundle(run: Path, out: Path = BUNDLE, replay: dict | None = None,
                  viewer: Path = VIEWER) -> dict:
    """Puts one recorded episode and one replay where the viewer looks for
    them (viewer/public/experiment/, gitignored)."""
    replay = replay or wiring_replay()
    validate_replay(replay, visible_ids(load_viewer_atlas(viewer)))
    run_manifest = json.loads((run / "manifest.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run / "video.mp4", out / "video.mp4")
    if (run / "final.png").exists():
        shutil.copyfile(run / "final.png", out / "poster.png")
    (out / "circuit.replay.json").write_text(json.dumps(replay, separators=(",", ":")) + "\n")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
                                         stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    experiment = {
        "run": str(run.relative_to(REPO)) if run.is_relative_to(REPO) else str(run),
        "scenario": run_manifest.get("scenario"),
        "scripted": run_manifest.get("scripted", True),
        "outcome": run_manifest.get("outcome"),
        "recorded_at_commit": run_manifest.get("git_commit"),
        "exported_at_commit": commit,
        "replay": {"kind": replay["source"]["kind"], "name": replay["source"]["name"],
                   "frames": len(replay["frames"])},
        "video_and_brain_are_linked": False,
        "note": ("The video is a scripted episode; the brain panel shows the circuit's wiring. "
                 "Nothing in the brain panel is driven by the video yet."),
    }
    (out / "experiment.json").write_text(json.dumps(experiment, indent=1, ensure_ascii=False) + "\n")
    return experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a recorded run and the circuit replay for viewer/.")
    parser.add_argument("--run", type=Path, required=True, help="a runs/record/<run> directory")
    parser.add_argument("--out", type=Path, default=BUNDLE)
    args = parser.parse_args()
    exp = export_bundle(args.run.resolve(), args.out)
    print(json.dumps(exp, indent=1, ensure_ascii=False))
    print(f"\nnow:  cd viewer && npm run dev   (bundle in {args.out})")


if __name__ == "__main__":
    main()

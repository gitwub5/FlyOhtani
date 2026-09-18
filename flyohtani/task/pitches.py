"""What the pitcher throws, and the pitches nobody trains on.

A policy that sees one pitch learns one answer. The environment already has
the two levers that make a pitch different to hit -- where it arrives (the
strike zones, 0.80 mm apart) and when (release timing) -- so this draws from
them and, more importantly, keeps a set back.

THE HELD-OUT SET IS THE POINT. G3 asks for evaluation pitches separated from
training ones before any learning starts, because a number measured on the
pitches a policy was tuned on says nothing. `training_pitches` and
`evaluation_pitches` draw from disjoint seeds and the split is fixed here,
in code, not chosen later when the results are in.
"""
from __future__ import annotations

import numpy as np

from flyohtani.task.env import PitchSpec
from flyohtani.world import batter as B

TIMING_JITTER_MS = 4.0
"""Release timing spread, uniform in +/- this. The scripted swing connects
over about +-1 ms, so at 4 ms a fixed-timing policy misses most pitches --
which is what makes timing something to see rather than memorise."""

TRAINING_SEED = 20260918
EVALUATION_SEED = 77
"""Disjoint streams, fixed before any policy existed."""


def sample_pitch(rng: np.random.Generator) -> PitchSpec:
    """One pitch: a zone and a release time."""
    return PitchSpec(
        zone=str(rng.choice(B.STRIKE_ZONES)),
        timing_ms=float(rng.uniform(-TIMING_JITTER_MS, TIMING_JITTER_MS)),
    )


def training_pitches(n: int, seed: int = TRAINING_SEED) -> list[PitchSpec]:
    rng = np.random.default_rng(seed)
    return [sample_pitch(rng) for _ in range(n)]


def evaluation_pitches(n: int = 60, seed: int = EVALUATION_SEED) -> list[PitchSpec]:
    """The held-out set. Every zone appears the same number of times so a
    score cannot move because the draw happened to be kind."""
    rng = np.random.default_rng(seed)
    per_zone = max(n // len(B.STRIKE_ZONES), 1)
    out = [PitchSpec(zone=zone,
                     timing_ms=float(rng.uniform(-TIMING_JITTER_MS, TIMING_JITTER_MS)))
           for zone in B.STRIKE_ZONES for _ in range(per_zone)]
    rng.shuffle(out)
    return out

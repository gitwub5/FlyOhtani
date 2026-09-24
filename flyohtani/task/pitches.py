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
from flyshohei import pitch as P

TIMING_JITTER_MS = 4.0
"""Release timing spread, uniform in +/- this. The scripted swing connects
over about +-1 ms, so at 4 ms a fixed-timing policy misses most pitches --
which is what makes timing something to see rather than memorise."""

TRAINING_SEED = 20260918
EVALUATION_SEED = 77
"""Disjoint streams, fixed before any policy existed."""


PITCH_NAMES: tuple[str, ...] = tuple(P.ARSENAL)
"""D39. Three flight times, which is the lever that makes the task need
looming at all: their connecting frames are 12-14, 18-20 and 22-23, so a
policy that waits a fixed time after first motion cannot cover them."""


def sample_pitch(rng: np.random.Generator) -> PitchSpec:
    """One pitch: a type, a zone and a release time."""
    return PitchSpec(
        pitch_name=str(rng.choice(PITCH_NAMES)),
        zone=str(rng.choice(B.STRIKE_ZONES)),
        timing_ms=float(rng.uniform(-TIMING_JITTER_MS, TIMING_JITTER_MS)),
    )


def training_pitches(n: int, seed: int = TRAINING_SEED) -> list[PitchSpec]:
    rng = np.random.default_rng(seed)
    return [sample_pitch(rng) for _ in range(n)]


def evaluation_pitches(n: int = 36, seed: int = EVALUATION_SEED) -> list[PitchSpec]:
    """The held-out set. Every (type, zone) cell appears the same number of
    times so a score cannot move because the draw happened to be kind.

    The default is 36 rather than 30 because there are nine cells now (three
    flight times x three zones) and an unbalanced draw across FLIGHT TIMES
    would be the worst kind: the decoders differ mainly in whether they can
    tell the flight times apart."""
    rng = np.random.default_rng(seed)
    cells = [(name, zone) for name in PITCH_NAMES for zone in B.STRIKE_ZONES]
    per_cell = max(n // len(cells), 1)
    out = [PitchSpec(pitch_name=name, zone=zone,
                     timing_ms=float(rng.uniform(-TIMING_JITTER_MS, TIMING_JITTER_MS)))
           for name, zone in cells for _ in range(per_cell)]
    rng.shuffle(out)
    return out

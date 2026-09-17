"""How fast a real fly leg actually moves, and what this project does about it.

G1 measured a bat tip at 16.8 m/s with joints turning at 1,682 rad/s. That
number is a property of `kp` and the commanded angle, not of a fly, and
LIT-01 (docs/records/LIT-01-FLY-LEG-LIMITS.md) went looking for what a real
fly can do. This module holds the answer in the form the rest of the code
needs.

The three kinds of number below are kept apart on purpose, because mixing
them is how an engineering choice starts getting cited as a fact:

  MEASURED   -- computed here from a real recording, reproducibly.
  PUBLISHED  -- read out of a paper, with the citation attached.
  DERIVED    -- arithmetic on the two above, carrying their assumptions.
  CHOSEN     -- what this project decided to impose. Not evidence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "behavior_neuromechfly"
WALKING_NPZ = _ASSETS / "walking-joint-angles-210902-pr-fly1.npz"
WALKING_PROVENANCE = _ASSETS / "PROVENANCE.json"


# --- PUBLISHED ------------------------------------------------------------

JUMP_LEG_EXTENSION_S = 3.3e-3
"""Giant-Fiber-mediated escape: how long the leg extension takes.
IQR 0.46 ms. Card & Dickinson (2008), J. Exp. Biol. 211(3):341-353,
doi:10.1242/jeb.012682."""

JUMP_TAKEOFF_SPEED_MM_S = 480.0
"""Peak translational speed over the first 2 ms of escape flight,
0.48 +/- 0.01 m/s. Same paper. This is the WHOLE FLY's speed, not a joint's."""

JUMP_PEAK_LEG_FORCE_UN = 101.0
"""Peak force of the main jump muscle through the mesothoracic leg,
101 +/- 4.4 uN in female Canton-S, 8.2 ms to peak (tethered strain gauge).
Zumstein et al. (2004), J. Exp. Biol. 207(20):3515-3522, PMID 15339947.

Compare `units.POSITION_CONTROL_FORCERANGE` (65 uN*mm): at a 1 mm moment arm
these are the same order of magnitude, so the model's force limit is
defensible. Force was never what made G1's number unphysical."""


# --- DERIVED --------------------------------------------------------------

JUMP_JOINT_SPEED_RANGE_RAD_S = (240.0, 516.0)
"""Joint angular speed implied by the escape jump, as `takeoff speed /
effective radius`, for radii of 2.00 mm down to 0.93 mm. Mesothoracic
Femur+Tibia is 1.451 mm (measured from the source MJCF).

An order-of-magnitude estimate, not a measurement: it collapses a
multi-joint push against the ground into one rigid rotation. No paper found
in the LIT-01 search reports per-joint angular velocity during a jump."""


# --- CHOSEN ---------------------------------------------------------------

MAX_JOINT_SPEED_RAD_S = 300.0
"""The design ceiling this project imposes on joint angular speed.

Sits inside the derived escape-jump range and roughly 3x above measured
walking. Choosing the jump rather than walking is deliberate: batting is a
maximal-effort act, so holding it to strolling speed would be the wrong
bound. It is still generous -- the jump numbers come from the MIDDLE leg,
which has a dedicated jump muscle (TDT); the FORELEG used here does not, and
nothing shows a foreleg matches that performance.

THIS IS NOT ENFORCED BY THE MODEL. G1's runs under this ceiling never
saturate their actuators (0.0%), so nothing in the physics stops a
controller from exceeding it. A controller must respect it, or the result
must be labelled a derived engineering model.
"""

MAX_BAT_TIP_SPEED_MM_S = 4533.0
"""Fastest bat tip in the G1 grid that stays under MAX_JOINT_SPEED_RAD_S:
4.53 m/s, with a 5e-7 g x 4 mm bat.

Two caveats travel with this number. The G1 grid's coarsest target angle
already reaches 280 rad/s, so the grid cannot tell a 300 rad/s ceiling from
a 520 rad/s one -- both select the same run. And that lightest bat is the
one contaminated by `boundmass` clamping (G1 section 5.3). Treat it as
"about 4.5 m/s", and re-measure on a finer grid before anything depends on
the third digit."""


@dataclass(frozen=True)
class JointSpeedStats:
    """Per-joint angular speed, in rad/s, from a real recording."""

    name: str
    range_of_motion_rad: float
    mean_abs: float
    p95_abs: float
    max_abs: float


@lru_cache(maxsize=1)
def walking_joint_speeds() -> dict[str, JointSpeedStats]:
    """MEASURED: differentiates the vendored 2 kHz recording of a tethered
    walking fly (42 DOF, 1 s). Not a literature value -- this is computed
    every time the tests run.

    Caveat, from the recording's own provenance: one fly, one second, one
    behaviour. Normal-behaviour speed, not a ceiling."""
    data = np.load(WALKING_NPZ, allow_pickle=False)
    angles = data["joint_angles_rad"]
    names = [str(n) for n in data["joint_names"]]
    dt = float(data["timestep_s"])

    out = {}
    for name, series in zip(names, angles, strict=True):
        speed = np.abs(np.gradient(series, dt))
        out[name] = JointSpeedStats(
            name=name,
            range_of_motion_rad=float(series.max() - series.min()),
            mean_abs=float(speed.mean()),
            p95_abs=float(np.percentile(speed, 95)),
            max_abs=float(speed.max()),
        )
    return out


def walking_provenance() -> dict:
    return json.loads(WALKING_PROVENANCE.read_text())


def exceeds_biological_speed(peak_joint_speed_rad_s: float) -> bool:
    """True when a run is faster than any real fly leg movement this project
    has evidence for. Such a run is not invalid -- it just may not be
    described as something a fly does."""
    return peak_joint_speed_rad_s > MAX_JOINT_SPEED_RAD_S

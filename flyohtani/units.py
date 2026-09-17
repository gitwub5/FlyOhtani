"""The unit convention, defined once.

NeuroMechFly's MJCF -- which this project's body model is derived from --
does NOT use SI. Its own documentation states the convention explicitly:

    "we use millimeter and gram as base units for length and mass instead
    of their SI counterparts, meter and kilogram... forces read out from
    the simulation are in g*mm*s^-1 (i.e., micronewton, uN)"
    -- https://neuromechfly.org/tutorials/1b_advanced_model_composition/

So: length = mm, mass = g, time = s, and therefore force = uN, torque =
uN*mm. Gravity is written as 9810 mm/s^2, which is what keeps accelerations
in real seconds while positions stay in millimetres.

Everything in this package works in MODEL units (mm/g/s). The `to_si_*`
helpers exist for reporting and for comparing against literature, not for
internal computation -- converting back and forth in a hot loop is exactly
the floating-point noise this convention was chosen to avoid.

Every constant below was read from the flygym==1.2.1 sources, not estimated.
Provenance: flyohtani/assets/mesh_neuromechfly/PROVENANCE.json,
docs/RESEARCH_SOURCES.md, docs/records/PRIOR-FINDINGS.md section 1.
"""
from __future__ import annotations

from typing import Final

# --- the convention itself -------------------------------------------------

LENGTH_UNIT: Final = "mm"
MASS_UNIT: Final = "g"
TIME_UNIT: Final = "s"
FORCE_UNIT: Final = "uN"  # g*mm/s^2
TORQUE_UNIT: Final = "uN*mm"  # g*mm^2/s^2

GRAVITY: Final = 9810.0
"""Magnitude of gravity in model units (mm/s^2). == 9.81 m/s^2."""

# --- SI conversion (for reporting only) ------------------------------------

MM_PER_M: Final = 1e3
G_PER_KG: Final = 1e3
UN_PER_N: Final = 1e6
TORQUE_MODEL_PER_NM: Final = 1e9
"""1 N*m == 1e9 uN*mm. (g*mm^2/s^2 = 1e-3 kg * 1e-6 m^2 / s^2 = 1e-9 N*m.)"""


def to_si_length(mm: float) -> float:
    """mm -> m."""
    return mm / MM_PER_M


def to_si_mass(g: float) -> float:
    """g -> kg."""
    return g / G_PER_KG


def to_si_force(un: float) -> float:
    """uN -> N."""
    return un / UN_PER_N


def to_si_torque(un_mm: float) -> float:
    """uN*mm -> N*m."""
    return un_mm / TORQUE_MODEL_PER_NM


# --- measured facts about the source model ---------------------------------
# These are READ values, not design choices. A design choice that happens to
# start from one of these belongs in the module that makes the choice.

BODY_MASS: Final = 1e-3
"""Whole-fly mass in model units (g) == 1 mg, summed from the raw MJCF's geom
masses. Same order of magnitude as the commonly cited adult D. melanogaster
mass; no specific literature citation has been pinned down for the exact
figure (docs/RESEARCH_SOURCES.md).

A naive regex sum of the raw XML gives ~1.0 instead. That is a known
measurement bug -- it also matches `<statistic meanmass="1.0">`, a
visualization hint that is not a physical mass. Count mass from MuJoCo's
compiled `model.body_mass`, never from the XML text.
"""

FORELEG_MASS: Final = 1.389e-5
"""One front leg, all segments, in model units (g) == 13.89 ug."""

FORELEG_SEGMENT_MASS_FRACTION: Final = {
    "Coxa": 0.326,
    "Femur": 0.453,
    "Tibia": 0.149,
    "Tarsus1": 0.033,
    "Tarsus2_5": 0.039,  # passive, summed
}
"""Per-segment share of FORELEG_MASS. Ratios are scale-invariant, so these
carry over to any rescaled derivative of the model; the absolute masses do
not."""

ACTIVE_FORELEG_JOINTS: Final = (
    "Coxa_yaw",
    "Coxa",
    "Coxa_roll",
    "Femur",
    "Femur_roll",
    "Tibia",
    "Tarsus1",
)
"""The 7 position-controlled DOFs per leg in flygym's own `all_leg_dofs`.
Tarsus2-5 have joints in the raw MJCF but are NOT in the actuated list --
flygym leaves them as passive springs, and so does this project.

These are SUFFIXES. flygym builds the real joint name as
`joint_{side}{position}{dof}`, e.g. `joint_RFCoxa_yaw` for the right
foreleg. Do not use these bare strings as joint names.

Only five of the seven are driveable with the model's own actuator spec;
see LOCKED_DOFS in flyohtani/body/minimal_body.py for the measurement."""

# Original position-control defaults, in model units.
POSITION_CONTROL_KP: Final = 45.0  # uN*mm/rad == 4.5e-8 N*m/rad
POSITION_CONTROL_FORCERANGE: Final = (-65.0, 65.0)  # uN*mm == +/-65 nN*m
JOINT_DAMPING: Final = 0.06
JOINT_STIFFNESS: Final = 0.05
TARSUS_PASSIVE_STIFFNESS: Final = 7.5
TARSUS_PASSIVE_DAMPING: Final = 0.01

NATURAL_JOINT_RANGE_IS_UNCONSTRAINED: Final = True
"""The raw MJCF has NO `<joint range=...>` on the leg joints -- flygym manages
posture through pose data (pose_stretch / pose_tripod), not hard limits.

Two samples cannot define a range. Phase 1 (docs/PLAN.md) must either gather
more pose data or proceed without hard limits as the original does, and label
anything outside the natural envelope a DERIVED ENGINEERING MODEL. Do not
invent a range here.
"""

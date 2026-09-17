"""The contact parameters G2 selected, in the one place the rest of the code
should read them from.

Selected by G2 protocol v2 (docs/records/G2-CONTACT.md section 10), an
EXPLORATORY protocol: it was designed after protocol v1 failed, and the
winning candidate is the one the post-hoc diagnostic had already examined.
It then passed an RK4 cross-check and 10 hold-out configurations it had not
been tuned on. Read section 10.2 before leaning on it.

These values are valid ONLY for what G2 tested: a 0.1 mm ball of 2.9e-6 g
against a 0.05 mm bat or a fixed block, frictionless, impact speeds up to
4,500 mm/s. A different ball, friction, or faster impacts need G2 again.
"""
from __future__ import annotations

from typing import Final

SOLREF_TIMECONST_S: Final = 3e-6
SOLREF_DAMPRATIO: Final = 0.3
SOLIMP: Final = (0.9, 0.95, 0.001, 0.5, 2.0)
"""MuJoCo's own default solimp -- the "default" candidate in G2."""

CONTACT_TIMESTEP_S: Final = SOLREF_TIMECONST_S / 128
"""2.344e-8 s. The step at which G2 v2 found contact converged.

Running a whole episode at this step is ~12.8 million steps per 0.3 s.
It is meant to be used AROUND contact only, and that multi-rate scheme is
not yet built or validated (G2 section 10.4)."""

MAX_VALIDATED_IMPACT_SPEED_MM_S: Final = 4500.0
"""Above this, G2 says nothing -- and the small-timeconst candidates already
tripped MuJoCo's bad-acceleration reset at this speed (section 10.3)."""

EXPECTED_COR_RANGE: Final = (0.418, 0.457)
"""Coefficient of restitution G2 v2 measured with these parameters, across
the main grid and the hold-out. Not a target -- an observation to check a
later integrated run against."""

BALL_RADIUS_MM: Final = 0.1
BALL_MASS_G: Final = 2.9e-6
BAT_RADIUS_MM: Final = 0.05


def solref_attr() -> str:
    return f"{SOLREF_TIMECONST_S!r} {SOLREF_DAMPRATIO!r}"


def solimp_attr() -> str:
    return " ".join(repr(v) for v in SOLIMP)

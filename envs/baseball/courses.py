"""ENV-002 B1 course geometry and per-course aim/timing config
(docs/design/ENV-002-B1-courses.md section 1-3). Pure data -- no MuJoCo
state, no side effects -- extracted from envs/baseball_b1_env.py by R-02
(docs/implementation/REFACTOR-PLAN.md) so it can be read/edited without the
810-line env orchestration file. `envs/baseball_b1_env.py` imports and
re-exports these same names, and `controllers/baseball_b1.py` imports
COURSES/ALIGNMENT/CROSSING_TIME_S from `envs.baseball_b1_env` as before --
this move changes no import path outside this package.

CROSSING_TIME_S is the DEFAULT calibration and is read-only
(`types.MappingProxyType`) -- `CROSSING_TIME_S["mid_mid"] = (...)` now raises
`TypeError` instead of silently mutating shared state. This replaces the
previous pattern where tests/demos/scripts temporarily monkeypatched one
course's entry, ran an episode, then restored the original value in a
`finally` block (docs/implementation/REFACTOR-PLAN.md R-02's flagged
technical debt, and the 2026-09-17 follow-up cleanup that resolved it).
Callers that need a different calibration build their own `dict(...)` copy
with the course(s) they want to override and pass it explicitly via
`OracleAimController(..., crossing_time_s=...)` /
`ScriptedAimController(..., crossing_time_s=...)`
(controllers/baseball_b1.py) -- the env itself never reads this mapping, so
this module's default is unaffected by any of that, and every existing
default-constructed controller behaves exactly as before.
"""
from __future__ import annotations

import types

import numpy as np

# Course grid (docs/design/ENV-002-B1-courses.md section 1). x is always the
# same plate-front reference as B0 (0.4318); only y (inside/outside) and z
# (high/low) vary per course.
ZONE_CENTER = np.array([0.4318, 0.0, 1.0])
ZONE_HALF_WIDTH_Y = 0.2159
ZONE_HALF_HEIGHT_Z = 0.35
_U = {"in": 2 / 3, "mid": 0.0, "out": -2 / 3}
_V = {"high": 2 / 3, "mid": 0.0, "low": -2 / 3}
COURSES: dict[str, np.ndarray] = {
    f"{uname}_{vname}": np.array(
        [ZONE_CENTER[0], ZONE_CENTER[1] + u * ZONE_HALF_WIDTH_Y, ZONE_CENTER[2] + v * ZONE_HALF_HEIGHT_Z]
    )
    for uname, u in _U.items()
    for vname, v in _V.items()
}

# Per-course (swing, tilt) geometric alignment: the (swing, tilt) angle pair
# where the bat passes closest to the course's target point (2D grid search,
# docs/design/ENV-002-B1-courses.md section 3). This is direction-independent
# geometry, so it is UNCHANGED by the I-07b-fix swing-direction reversal --
# only which direction/prep angle the bat approaches it from changed.
ALIGNMENT: dict[str, tuple[float, float]] = {
    "in_high": (-1.226, 0.410),
    "in_mid": (-1.226, 0.000),
    "in_low": (-1.226, -0.410),
    "mid_high": (-1.298, 0.332),
    "mid_mid": (-1.298, 0.000),
    "mid_low": (-1.298, -0.332),
    "out_high": (-1.346, 0.280),
    "out_mid": (-1.346, 0.000),
    "out_low": (-1.346, -0.280),
}

# Per-course (swing_crossing_time, tilt_crossing_time): how long before the
# ball's predicted arrival each axis's bang-bang trigger should fire so it
# crosses ALIGNMENT near arrival ("cross, don't stop-and-hold", same
# philosophy as BaseballB0Env's scripted controller -- see
# controllers/baseball_b1.py). ONLY mid_mid is recalibrated (first for
# I-07b-fix, then again for I-07c-swing below). The other 8 entries are
# UNCHANGED from before I-07b-fix (commit c812766): calibrated for the old
# prep_swing=1.0, decreasing-angle (backward) swing at gear=12, against a
# contact-only success criterion. They are almost certainly wrong for the
# current prep_swing/gear=30/solref-fixed physics and must NOT be used as
# evidence of reachability until a future 9-course expansion step
# recalibrates them the same way mid_mid was.
#
# I-07c-swing (docs/design/BATTING-QUALITY-AND-SWING.md section 2;
# docs/records/VALIDATION_LOG.md has the full prep-angle/trigger sweep):
# prep_swing widened from -1.9 to -1.96 (bat_hinge's fixed joint range is
# [-2.0, 2.0] -- gear/mass/inertia/material/dt/pitch all held fixed, ONLY
# the windup distance and its matching trigger time changed). Under the
# swing axis's already-optimal constant-max-torque "accelerate" phase (no
# premature target-arrival braking -- see _SwingAxis), a longer windup
# purely from a further-back prep angle raises contact-point speed
# (v=sqrt(2*a_max*delta_theta)): mid_mid, trigger=0.09425316355759385s of a
# 0.459091s flight, bat_contact_vx=+7.40 m/s (was +6.98), exit_speed=8.61
# m/s (was 8.53), forward_flight_success=True, batting_score=8.48m (was
# 5.82m, +46%), settle 0.431s post-contact / 4.3e-5rad peak-to-peak (both
# within the 0.5s/0.02rad targets). Trade-off found and reported, not
# hidden: exit launch angle rose to 41.2deg (was 14.0deg) -- a markedly
# higher trajectory, not merely a faster line drive, because the new
# contact instant (still a purely kinematic function of trigger timing, not
# hand-picked for its look) lands at a different point along the bat's
# continuous sweep. ALSO found and reported: BOTH the old (-1.9) and new
# (-1.96) trigger times are extremely sensitive to a single control-step
# (0.005s) shift -- either direction flips forward_flight_success to False
# on BOTH prep angles (verified for -1.9 too, not unique to this change).
# This is a pre-existing contact-timing fragility of the bang-bang
# oracle/collision design, unchanged in kind by this recalibration; fixing
# it would need a different (closed-loop/contact-triggered) control
# approach, out of scope here. Only mid_mid uses -1.96; the other 8 courses
# keep whatever prep_swing they're constructed with (single scalar; see
# BaseballB1Env.__init__).
CROSSING_TIME_S: types.MappingProxyType[str, tuple[float, float]] = types.MappingProxyType(
    {
        "in_high": (0.25, 0.41),
        "in_mid": (0.27, 0.0),
        "in_low": (0.23, 0.33),
        "mid_high": (0.27, 0.28),
        "mid_mid": (0.09425316355759385, 0.0),  # I-07c-swing recalibration (was 0.094091 for prep_swing=-1.9; see comment above)
        "mid_low": (0.25, 0.30),
        "out_high": (0.29, 0.28),
        "out_mid": (0.29, 0.0),
        "out_low": (0.26, 0.31),
    }
)

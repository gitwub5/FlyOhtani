"""KC-01a calibrated constants (docs/design/KC-01a-TORSO-BAT-COORDINATION.md
section 2). Two kinds of numbers live here, kept explicitly distinct:

- ENGINEERING ASSUMPTIONS: chosen by the implementer, not measured from any
  real fly or human, and not derived from simulation. Marked as such.
- CALIBRATED VALUES: derived by actually running envs.baseball_kc01a_env
  (grid search over target geometry, empirical actuator-gear/trigger-time
  sweeps) -- reproducible via scripts/kc01a_calibrate.py, not hand-picked.

mid_mid is the ONLY calibrated course, matching B1's own established scope
(docs/design/BASEBALL-SPEC.md section 5's precedent) -- this module makes
no claim about any other course.
"""
from __future__ import annotations

# --- Engineering assumptions (envs/assets/baseball_park_kc01a.xml has the
# authoritative copies + full reasoning; repeated here only as plain
# numbers for scripts that need them without parsing the XML) ---
TORSO_MASS_KG = 35.0  # trunk+head fraction of a 70kg-equivalent character; NOT fly anatomy, NOT measured
TORSO_YAW_RANGE_RAD = (-0.6, 0.6)  # modest windup, same order of magnitude as the tilt axis's own range

# --- Calibrated: actuator gear (scripts/kc01a_calibrate.py step 1, no-ball
# sweep, swing/tilt held at prep, ctrl=+1, time to reach 0.5rad from rest;
# budget 0.30s, same budget bat_tilt_motor's own B1 calibration used) ---
TORSO_MOTOR_GEAR = 30.0  # gear=25 -> 0.33s (misses); gear=30 -> 0.300s (meets)

# --- Calibrated: measured max angular acceleration at ctrl=1, this gear,
# WITH the bat loaded at prep (not the isolated-body value) ---
TORSO_A_MAX_RAD_S2 = 11.41
SWING_A_MAX_RAD_S2 = 134.4  # inherited from B1's own measurement (identical bat/hinge physics)

# --- Calibrated: target angles for mid_mid (scripts/kc01a_calibrate.py
# step 2, numerical grid search minimizing bat-capsule-to-target-point
# distance; residuals all < 6.2cm contact threshold, most < 1mm) ---
PREP_TORSO = 0.0
PREP_SWING = -1.96
PREP_TILT = 0.0

# arm_only: torso locked at 0 -- reproduces B1's own geometry exactly
# (identical XML subtree when torso_yaw=0), residual 4.9e-5m.
ARM_ONLY_SWING_TARGET = -1.298

# torso_only: swing/tilt locked at prep -- residual 3.3e-4m, REACHABLE, but
# see TORSO_ONLY's timing calibration below: the best achievable timing
# still does not produce a valid batted ball (a real finding, not a search
# failure -- see docs/design/KC-01a-TORSO-BAT-COORDINATION.md section 5).
TORSO_ONLY_TORSO_TARGET = 0.496

# simultaneous / staggered: a chosen 1-parameter split of the same
# 1-parameter family of (torso, swing) pairs that reach the target (any
# torso value in roughly [-0.5, -0.2] has a matching swing solution) --
# -0.4 picked to leave margin inside the +-0.6 range while still being a
# substantial (not token) torso contribution. residual 3.6e-4m.
SHARED_TORSO_TARGET = -0.4
SHARED_SWING_TARGET = -0.726

# --- Calibrated: trigger ("crossing") times, seconds of remaining flight
# time before which each axis's bang-bang accelerate phase starts
# (scripts/kc01a_calibrate.py step 3, empirical sweep -- NOT globally
# optimized, just the center of the first working window found; the
# ±5ms sensitivity check in docs/design/KC-01a-TORSO-BAT-COORDINATION.md
# section 4 characterizes how narrow that window is) ---
ARM_ONLY_SWING_CROSSING_TIME_S = 0.09425316355759385  # B1's own calibrated value; reproduces closely, not identically (see section 5's timing-fragility note)
TORSO_ONLY_TORSO_CROSSING_TIME_S = 0.310  # best found; does NOT reach a valid hit at this or any timing searched
SIMULTANEOUS_CROSSING_TIME_S = 0.096  # same crossing time on both axes (center of the [0.0942, 0.0990] valid window found)
STAGGERED_SWING_CROSSING_TIME_S = 0.122  # center of the [0.120, 0.124] valid window found
STAGGERED_TORSO_LEAD_S = 0.12  # torso triggers this much earlier than swing (torso_crossing_time = swing_crossing_time + this)

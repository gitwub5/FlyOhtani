"""I-08a-fix (docs/records/FLY-VISUAL-REVIEW.md): NeuroMechFly visual
overlay for BaseballB1Env. Purely cosmetic -- everything here reads
already-computed physics state and writes only to mocap bodies (which have
no DOF and cannot affect dynamics); it must never be called from inside
env.step()'s physics loop, only before rendering. See
docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json for mesh provenance
and scripts/build_fly_visual_asset.py for how the static rig (envs/assets/
fly_visual_assets.xml, fly_visual_body.xml) was generated.

Posture (per the review's explicit spec): LH/RH stand on the ground
(static, part of the baked rig). LM/RM are folded in against the body
(static, also part of the baked rig -- not grounded, not used as arms).
LF/RF are the only DYNAMIC legs: their Femur/Tibia/Tarsus1 segments are
driven every render frame by a 3-segment IK from each shoulder (LFCoxa/
RFCoxa, static) to a "grip target" site on the bat handle, via three mocap
bodies per arm. All segments use the SAME uniform mesh scale as the rest of
the body (envs/assets/fly_visual_front_legs.xml) -- I-08a's separate 3x arm
enlargement was removed per the review; if the natural (uniform-scale) arm
length cannot reach a required target, `update()` reports it via
`unreachable` in the returned dict rather than stretching anything.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np

# Segment lengths (meters), uniform K=400 (matches the rest of the body --
# see scripts/build_fly_visual_asset.py; NOT the 3x-enlarged I-08a values).
# Measured from the source rig's own rest-pose child-body offsets: each is
# the distance a segment's mesh is authored to span between its own
# proximal and distal joints. Symmetric L/R by construction.
FEMUR_LEN_M = 0.2820958200920793
TIBIA_LEN_M = 0.20735908259017755
TARSUS1_LEN_M = 0.09018919848715663
TOTAL_REACH_M = FEMUR_LEN_M + TIBIA_LEN_M + TARSUS1_LEN_M

# Elbow bend-plane reference: without a real shoulder joint's natural
# range to draw on, the 2-link (Femur/Tibia) IK's elbow position is only
# constrained up to rotation about the shoulder-wrist axis. -Z (world down)
# makes the elbow bend downward, a plausible/neutral "gripping forward and
# down" arm posture; picked by visual inspection, not anatomically derived.
BEND_REF = np.array([0.0, 0.0, -1.0])


def _quat_align_neg_z(direction: np.ndarray) -> np.ndarray:
    """Quaternion rotating local -Z to world `direction` (unit vector).
    Matches the NeuroMechFly leg meshes' own convention (each segment's
    mesh, drawn at its body's local origin, extends toward -Z on its own
    child joint) -- see scripts/build_fly_visual_asset.py."""
    z = np.array([0.0, 0.0, -1.0])
    d = direction / (np.linalg.norm(direction) + 1e-12)
    c = float(np.dot(z, d))
    if c > 1.0 - 1e-9:
        return np.array([1.0, 0.0, 0.0, 0.0])
    if c < -1.0 + 1e-9:
        return np.array([0.0, 1.0, 0.0, 0.0])
    axis = np.cross(z, d)
    axis /= np.linalg.norm(axis)
    angle = math.acos(np.clip(c, -1.0, 1.0))
    s = math.sin(angle / 2.0)
    return np.array([math.cos(angle / 2.0), axis[0] * s, axis[1] * s, axis[2] * s])


def _solve_elbow(shoulder: np.ndarray, wrist: np.ndarray, l1: float, l2: float) -> np.ndarray:
    """2-link (Femur, Tibia) inverse kinematics: elbow position such that
    |shoulder-elbow|=l1 and |elbow-wrist|=l2, in the plane containing
    shoulder, wrist, and BEND_REF. Clamps to the reachable envelope
    (|l1-l2| <= dist <= l1+l2) -- callers must separately check/report
    whether the UNCLAMPED distance actually fits (see `update()`)."""
    d = wrist - shoulder
    dist = float(np.linalg.norm(d))
    dist_clamped = min(max(dist, abs(l1 - l2) + 1e-6), l1 + l2 - 1e-6)
    dir_hat = d / (np.linalg.norm(d) + 1e-12)
    cos_a = (l1 * l1 + dist_clamped * dist_clamped - l2 * l2) / (2.0 * l1 * dist_clamped)
    cos_a = float(np.clip(cos_a, -1.0, 1.0))
    a = math.acos(cos_a)
    perp = np.cross(dir_hat, BEND_REF)
    if np.linalg.norm(perp) < 1e-8:
        perp = np.cross(dir_hat, np.array([1.0, 0.0, 0.0]))
    perp /= np.linalg.norm(perp)
    bend_axis = np.cross(perp, dir_hat)
    bend_axis /= np.linalg.norm(bend_axis) + 1e-12
    bend_dir = dir_hat * math.cos(a) + bend_axis * math.sin(a)
    return shoulder + bend_dir * l1


class FrontLegGripOverlay:
    """Drives the 6 dynamic mocap bodies (LF/RF x femur/tibia/tarsus1) each
    render frame so both front legs' fingertips track the bat's grip
    sites. Call `update(model, data)` after mj_forward/mj_step, before
    rendering -- never during the physics substep loop.

    3-segment IK: Femur+Tibia (2-link analytic IK, `_solve_elbow`) reach a
    "wrist" point placed TARSUS1_LEN_M back from the actual grip target
    along the current wrist-to-target direction (i.e. as if Tarsus1 were
    already aimed at the target); Tarsus1 then spans wrist -> target
    directly, so it is always the segment that actually touches the grip
    site (real fingertip mesh, per the review's "발끝(Tarsus 포함)을
    보존" requirement) rather than a clamped abstract IK endpoint.
    """

    def __init__(self, model: mujoco.MjModel) -> None:
        def bid(name: str) -> int:
            return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)

        def sid(name: str) -> int:
            return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, name)

        self.shoulder_body = {"L": bid("LFCoxa"), "R": bid("RFCoxa")}
        self.grip_site = {"L": sid("grip_L"), "R": sid("grip_R")}
        self.mocap_femur = {s: model.body_mocapid[bid(f"fly_{s}F_femur")] for s in ("L", "R")}
        self.mocap_tibia = {s: model.body_mocapid[bid(f"fly_{s}F_tibia")] for s in ("L", "R")}
        self.mocap_tarsus1 = {s: model.body_mocapid[bid(f"fly_{s}F_tarsus1")] for s in ("L", "R")}
        for s in ("L", "R"):
            for seg in ("femur", "tibia", "tarsus1"):
                name = f"fly_{s}F_{seg}"
                if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) < 0:
                    raise ValueError(f"missing mocap body {name!r}; is the front-leg fragment included?")

    def update(self, model: mujoco.MjModel, data: mujoco.MjData) -> dict:
        """Returns {"L": reach_error_m, "R": reach_error_m} -- the amount
        (meters, 0 if in reach) by which the true shoulder-to-target
        distance exceeds TOTAL_REACH_M this frame. Positive values mean
        the fingertip physically CANNOT touch the grip site this frame
        (arm fully extended, pointed at it, but short) -- callers doing
        acceptance checks should treat any positive value as a failure,
        not silently accept the clamped pose."""
        reach_error = {}
        for side in ("L", "R"):
            shoulder = data.xpos[self.shoulder_body[side]].copy()
            target = data.site_xpos[self.grip_site[side]].copy()
            dist = float(np.linalg.norm(target - shoulder))
            reach_error[side] = max(0.0, dist - TOTAL_REACH_M)

            target_dir = (target - shoulder) / (dist + 1e-12)
            wrist_target = target - target_dir * TARSUS1_LEN_M
            elbow = _solve_elbow(shoulder, wrist_target, FEMUR_LEN_M, TIBIA_LEN_M)

            femur_quat = _quat_align_neg_z(elbow - shoulder)
            data.mocap_pos[self.mocap_femur[side]] = shoulder
            data.mocap_quat[self.mocap_femur[side]] = femur_quat

            # The 2-link IK's own wrist point (not wrist_target, which is a
            # target-side construction) is elbow + TIBIA_LEN_M along its
            # own solved direction -- but since _solve_elbow already places
            # elbow exactly TIBIA_LEN_M from wrist_target by construction,
            # wrist_target IS that point.
            tibia_quat = _quat_align_neg_z(wrist_target - elbow)
            data.mocap_pos[self.mocap_tibia[side]] = elbow
            data.mocap_quat[self.mocap_tibia[side]] = tibia_quat

            tarsus1_quat = _quat_align_neg_z(target - wrist_target)
            data.mocap_pos[self.mocap_tarsus1[side]] = wrist_target
            data.mocap_quat[self.mocap_tarsus1[side]] = tarsus1_quat

        # mocap_pos/mocap_quat are inputs to kinematics, not outputs -- the
        # derived geom_xpos MuJoCo actually renders stays stale (from
        # whatever qpos-driven mj_forward last computed, e.g. inside the
        # last env.step()) until kinematics is recomputed. Recomputing here
        # only refreshes DERIVED quantities (xpos, geom_xpos, ...) from the
        # current qpos/qvel/mocap state; it does not advance qpos/qvel via
        # integration, so it cannot change the physics trajectory.
        mujoco.mj_forward(model, data)
        return reach_error

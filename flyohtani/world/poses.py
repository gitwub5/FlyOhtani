"""Finding arm poses that put the bat somewhere specific.

READY_POSE and CONTACT_POSE in `batter.py` were found by a search that was
never kept, which meant the next pose had to be found by a new ad-hoc one.
This is that search, written down: give it a strike point and it returns
joint angles that put the sweet spot there with the bat across the plate.

It exists because the task is about to need more than one contact pose. A
pitch that can arrive high or low is only a harder task if the fly has to
swing somewhere different, and it can only do that if such poses exist and
are reachable -- both of which are measured here rather than assumed.

The search is a random restart plus a coordinate-descent refinement. No
optimiser dependency, deterministic given a seed, and slow enough (a second
or so) that results are cached as constants rather than recomputed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import mujoco
import numpy as np

from flyohtani.world import batter as B

BAT_ACROSS_PLATE = np.array([0.0, -1.0, 0.0])
"""What "the bat is across the plate" means: the barrel pointing toward the
first-base side, i.e. the pose a right-handed batter meets the ball in. The
search scores alignment with this, it does not enforce it."""

GROUND_CLEARANCE_MM = 0.25
"""How far the lowest point of the bat must stay above the dirt. The demo
swing clears by ~1 mm; this is the floor for a pose to be usable at all."""

NEAR_REFERENCE_WEIGHT = 0.15
"""Pull toward the reference pose, per radian of joint-space distance.

Five joints reaching for one point is redundant, so a plain search returns a
different contortion for every target -- three unrelated poses, not three
versions of one swing. That matters here: the swing is an interpolation from
READY, and it has to stay under LIT-01's joint-speed ceiling and out of the
ground for every zone. Staying near the reference keeps the family coherent.
Weak enough (0.15 per radian against millimetres of error) that it never buys
accuracy away."""


@dataclass(frozen=True)
class PoseSearchResult:
    angles: dict[str, float]
    sweet_xyz: np.ndarray
    error_mm: float
    bat_alignment: float
    """cos of the angle between the bat and BAT_ACROSS_PLATE: 1 is perfect."""
    clearance_mm: float

    @property
    def usable(self) -> bool:
        return self.error_mm < 0.05 and self.clearance_mm > GROUND_CLEARANCE_MM


def _measure(model: mujoco.MjModel, data: mujoco.MjData, angles: dict[str, float],
             target: np.ndarray, sweet: int, tip: int, grip: int) -> tuple[float, np.ndarray, float, float]:
    B.set_arm(model, data, angles)
    p = data.site_xpos[sweet]
    axis = data.site_xpos[tip] - data.site_xpos[grip]
    axis = axis / max(float(np.linalg.norm(axis)), 1e-12)
    alignment = float(axis @ BAT_ACROSS_PLATE)
    clearance = float(min(data.site_xpos[tip][2], data.site_xpos[grip][2], p[2])) - B.DIRT_TOP_MM
    return float(np.linalg.norm(p - target)), p.copy(), alignment, clearance


def find_contact_pose(target_xyz, *, seed: int = 0, restarts: int = 400,
                      iterations: int = 60, scene: B.Scene | None = None,
                      reference: dict[str, float] | None = None) -> PoseSearchResult:
    """Joint angles putting the sweet spot at `target_xyz` (mm, world).

    Scored as distance to the target, with the bat's direction and its
    ground clearance as penalties -- a pose that hits the target by dragging
    the bat through the dirt is not a batting pose.
    """
    scene = scene or B.build_scene()
    from flyohtani.world.rollout import compiled

    model = compiled(scene)
    data = mujoco.MjData(model)
    sweet = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")
    tip = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "bat_tip")
    grip = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "grip")
    target = np.asarray(target_xyz, dtype=float)
    joints = list(B.ACTIVE_JOINTS)
    rng = np.random.default_rng(seed)

    ref = reference if reference is not None else B.CONTACT_POSE
    ref_q = np.array([ref[j] for j in joints])

    def cost(angles: dict[str, float]) -> tuple[float, tuple]:
        err, p, align, clear = _measure(model, data, angles, target, sweet, tip, grip)
        near = float(np.abs(np.array([angles[j] for j in joints]) - ref_q).sum())
        penalty = (2.0 * max(0.0, 1.0 - align)
                   + 5.0 * max(0.0, GROUND_CLEARANCE_MM - clear)
                   + NEAR_REFERENCE_WEIGHT * near)
        return err + penalty, (err, p, align, clear)

    best_cost, best_angles, best_info = math.inf, None, None
    start = ref_q.copy()
    for r in range(restarts):
        q = start + rng.normal(0.0, 0.6, size=len(joints)) if r else start.copy()
        angles = dict(zip(joints, q, strict=True))
        c, info = cost(angles)
        step = 0.35
        for _ in range(iterations):
            improved = False
            for k, j in enumerate(joints):
                for direction in (+1.0, -1.0):
                    trial = dict(angles)
                    trial[j] = angles[j] + direction * step
                    tc, tinfo = cost(trial)
                    if tc < c:
                        angles, c, info, improved = trial, tc, tinfo, True
                        break
            if not improved:
                step *= 0.5
                if step < 1e-4:
                    break
        if c < best_cost:
            best_cost, best_angles, best_info = c, angles, info
    err, p, align, clear = best_info
    return PoseSearchResult(angles=best_angles, sweet_xyz=p, error_mm=err,
                            bat_alignment=align, clearance_mm=clear)

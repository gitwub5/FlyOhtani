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


COARSE_SEARCH_DT_S = 2.5e-5
"""Timestep while searching. See swing_velocity_at_contact."""

SWING_ATTACK_DEG = 10.0
"""The attack angle a swing should meet the ball with: the bat's velocity,
tilted up from horizontal, at the moment of contact.

Measured reason. The pitch arrives descending at -23 degrees, and the demo
swing met it moving DOWN at -13 to -22 -- bat and ball travelling the same
way, which is why every solid hit went into the ground (launch angles of -30
to -78) and why exit speeds sat at half the bat speed. A real swing meets a
descending pitch slightly upward; +10 is the middle of what hitters are
measured at (+5 to +15) and is not fitted to this task's reward."""


def swing_velocity_at_contact(contact_pose: dict[str, float], ready: dict[str, float],
                              zone: str = "middle", scene: B.Scene | None = None,
                              duration_s: float | None = None,
                              follow: float | None = None,
                              dt_s: float | None = None) -> tuple[np.ndarray, float, float]:
    """(velocity, peak joint speed, ground clearance) where the sweet spot
    passes closest to where `contact_pose` puts it."""
    from flyohtani.world.rollout import compiled

    scene = scene or B.build_scene()
    model = compiled(scene)
    duration = B.DEMO_SWING_S if duration_s is None else duration_s
    follow_t = B.DEMO_SWING_FOLLOW if follow is None else follow
    sweet = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")
    ball = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "ball")

    probe = mujoco.MjData(model)
    B.set_arm(model, probe, contact_pose)
    target = probe.site_xpos[sweet].copy()

    data = mujoco.MjData(model)
    B.set_arm(model, data, ready)
    adr = model.jnt_qposadr[model.body_jntadr[ball]]
    data.qpos[adr:adr + 3] = (0.0, -250.0, 5.0)
    # A search runs this thousands of times and only needs the swing's own
    # dynamics, not contact: G1 converged the arm at 2.5e-5, so that is what
    # a search uses. The chosen pose is re-measured at the contact timestep.
    model.opt.timestep = B.TIMESTEP_S if dt_s is None else dt_s
    vel = np.zeros(6)
    best = (math.inf, np.zeros(3))
    peak_q = 0.0
    clearance = math.inf
    for _ in range(round(duration * (1 + follow_t) / model.opt.timestep)):
        u = (data.time / duration)
        e = (0.5 - 0.5 * math.cos(math.pi * min(u, 1.0))) * (1.0 + follow_t)
        data.ctrl[:] = [ready[j] + e * (contact_pose[j] - ready[j]) for j in B.ACTIVE_JOINTS]
        mujoco.mj_step(model, data)
        peak_q = max(peak_q, float(np.max(np.abs(data.qvel[:5]))))
        p = data.site_xpos[sweet]
        clearance = min(clearance, float(p[2]) - B.DIRT_TOP_MM)
        dist = float(np.linalg.norm(p - target))
        if dist < best[0]:
            mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_SITE, sweet, vel, 0)
            best = (dist, vel[3:].copy())
    _ = zone
    return best[1], peak_q, clearance


def find_ready_pose(contact_poses, *, attack_deg: float = SWING_ATTACK_DEG,
                    seed: int = 0, restarts: int = 80, iterations: int = 40,
                    scene: B.Scene | None = None,
                    max_joint_speed: float = 300.0) -> tuple[dict[str, float], dict]:
    """A starting pose whose swing meets the ball moving forward and slightly
    up, as fast as the joint-speed ceiling allows.

    `contact_poses` is one pose or several. Several matters: the fly waits in
    ONE stance, because it does not know where the pitch is going until it
    sees it, so a per-zone stance would leak the answer into the pose. With
    several, the score is the WORST zone -- a stance that is superb for high
    pitches and useless for low ones is not a stance.

    The contact poses are held fixed -- where the bat meets the ball is
    already decided -- and only the path into them is searched."""
    if isinstance(contact_poses, dict) and contact_poses and isinstance(
            next(iter(contact_poses.values())), (int, float)):
        contact_poses = [contact_poses]
    elif isinstance(contact_poses, dict):
        contact_poses = list(contact_poses.values())
    scene = scene or B.build_scene()
    joints = list(B.ACTIVE_JOINTS)
    want = np.array([math.cos(math.radians(attack_deg)), 0.0, math.sin(math.radians(attack_deg))])
    rng = np.random.default_rng(seed)

    def score_one(contact_pose, ready, dt_s):
        v, peak_q, clear = swing_velocity_at_contact(contact_pose, ready, scene=scene, dt_s=dt_s)
        speed = float(np.linalg.norm(v))
        if speed < 1e-9:
            return -math.inf, {}
        attack = math.degrees(math.atan2(v[2], math.hypot(v[0], v[1])))
        info = {"speed": speed, "attack_deg": attack, "peak_joint_speed": peak_q,
                "clearance_mm": clear, "velocity": v}
        # The ceiling and the ground are limits, not costs: a swing that
        # breaks either is not a candidate at all. The first version of this
        # made them penalties and the search bought 1408 mm/s by going 17
        # rad/s over and 0.07 mm under.
        if peak_q > max_joint_speed or clear < GROUND_CLEARANCE_MM:
            return -math.inf, info
        # Fast AND pointed the right way: the component along the wanted
        # direction, less what is wasted perpendicular to it.
        along = float(v @ want)
        across = float(np.linalg.norm(v - along * want))
        return along - 0.5 * across, info

    def score(ready: dict[str, float], dt_s: float | None = COARSE_SEARCH_DT_S) -> tuple[float, dict]:
        values, infos = [], []
        for pose in contact_poses:
            value, info = score_one(pose, ready, dt_s)
            if value == -math.inf:
                return -math.inf, info
            values.append(value)
            infos.append(info)
        worst = int(np.argmin(values))
        return values[worst], {**infos[worst], "per_zone": infos}

    start = np.array([B.READY_POSE[j] for j in joints])
    best_value, best_ready = -math.inf, dict(B.READY_POSE)
    for r in range(restarts):
        q = start + rng.normal(0.0, 0.5, size=len(joints)) if r else start.copy()
        ready = dict(zip(joints, q, strict=True))
        value, _ = score(ready)
        step = 0.3
        for _ in range(iterations):
            improved = False
            for j in joints:
                for direction in (+1.0, -1.0):
                    trial = dict(ready)
                    trial[j] = ready[j] + direction * step
                    v2, _ = score(trial)
                    if v2 > value:
                        ready, value, improved = trial, v2, True
                        break
            if not improved:
                step *= 0.5
                if step < 5e-3:
                    break
        if value > best_value:
            best_value, best_ready = value, ready
    # the winner is re-measured at the contact timestep, since that is the
    # one every other number in the project is quoted at
    _, exact = score(best_ready, dt_s=None)
    return best_ready, exact

"""Stepping a swing, and describing what the ball did afterwards.

This exists because the same loop was written three times -- in
`world.rollout`, in `task.env` and in `record.scenarios` -- and they drifted.
The env and the recorder disagreed about which frame a policy had committed
on, and about the carry of the ball it hit, because each had its own copy of
"step until the ball leaves the bat" and its own copy of "turn the ball's
velocity into a launch angle". Neither was wrong on purpose.

So the physics of a swing lives here, once:

    swing_table         the joint targets, precomputed
    step_swing          integrate until the ball leaves the bat, or until
                        it is past the plate having missed
    batted_ball         exit speed, launch, spray, landing, fair

Callers keep their own reasons for existing: rollout is the fast path, env
is the interactive one, scenarios renders. What they no longer keep is their
own version of this.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import mujoco
import numpy as np

from flyohtani import units
from flyohtani.world import batter as B

_TRAJECTORIES: dict[tuple, np.ndarray] = {}


def swing_table(duration_s: float, follow: float, dt: float, n: int,
                zone: str = "middle") -> np.ndarray:
    """The whole swing's joint targets, precomputed as (n, 5).

    The targets are a fixed function of time, so building the dict and taking
    a cosine inside the stepping loop was pure overhead -- about half the
    per-step cost, since mj_step itself is 7 us and the loop was taking 20.
    """
    key = (duration_s, follow, dt, n, zone)
    if key not in _TRAJECTORIES:
        table = np.empty((n, len(B.ACTIVE_JOINTS)))
        for i in range(n):
            targets = B.swing_targets(i * dt, duration_s=duration_s, follow=follow, zone=zone)
            table[i] = [targets[j] for j in B.ACTIVE_JOINTS]
        _TRAJECTORIES[key] = table
    return _TRAJECTORIES[key]


def bat_geom_ids(model: mujoco.MjModel) -> set[int]:
    """The bat's collision capsules, by id."""
    return {mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"bat_c{i}") for i in range(5)}


@dataclass
class SwingRun:
    contact: bool
    contact_time_s: float | None
    """Measured from the first step of the swing."""
    sweet_speed_at_contact_mm_s: float
    peak_joint_speed_rad_s: float
    steps: int


def step_swing(model: mujoco.MjModel, data: mujoco.MjData, table: np.ndarray, *,
               ball_geom: int, ball_body: int, bat_geoms: set[int],
               stop_x_mm: float, sweet_site: int | None = None) -> SwingRun:
    """Integrate the swing until the ball leaves the bat, or until it is
    behind `stop_x_mm` having missed.

    The model's timestep is whatever the caller set; the table has to have
    been built for it.
    """
    t0 = float(data.time)
    ctrl, contacts, arm_vel = data.ctrl, data.contact, data.qvel[:5]
    velocity = np.zeros(6)
    in_contact = False
    contact_time = None
    sweet_speed = 0.0
    peak_q = 0.0
    steps = 0
    for row in table:
        ctrl[:] = row
        mujoco.mj_step(model, data)
        steps += 1
        peak_q = max(peak_q, float(max(arm_vel.max(), -arm_vel.min())))
        touching = False
        for k in range(data.ncon):
            c = contacts[k]
            if ((c.geom1 == ball_geom and c.geom2 in bat_geoms)
                    or (c.geom2 == ball_geom and c.geom1 in bat_geoms)):
                touching = True
                break
        if touching:
            if not in_contact:
                in_contact = True
                contact_time = float(data.time) - t0
                if sweet_site is not None:
                    mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_SITE,
                                             sweet_site, velocity, 0)
                    sweet_speed = float(np.linalg.norm(velocity[3:]))
        elif in_contact or float(data.xpos[ball_body][0]) < stop_x_mm:
            break  # off the bat, or past the plate having missed
    return SwingRun(in_contact, contact_time, sweet_speed, peak_q, steps)


def ballistic(pos: np.ndarray, vel: np.ndarray, t: float) -> np.ndarray:
    g = np.array([0.0, 0.0, -units.GRAVITY])
    return pos + vel * t + 0.5 * g * t * t


def time_to_ground(pos: np.ndarray, vel: np.ndarray, radius_mm: float) -> float:
    """When a projectile's surface first reaches the ground plane. Returns
    inf if it never does (only possible if it is already rising away and the
    scene had no gravity)."""
    g = units.GRAVITY
    z0 = float(pos[2]) - radius_mm - B.DIRT_TOP_MM
    vz = float(vel[2])
    if g <= 0:
        return math.inf if vz >= 0 else -z0 / vz
    disc = vz * vz + 2 * g * z0
    if disc < 0:
        return math.inf
    return (vz + math.sqrt(disc)) / g


def is_fair(landing: np.ndarray) -> bool:
    """Inside the foul lines: the two 45 degree lines from home plate."""
    x, y = float(landing[0]), float(landing[1])
    return x > 0 and abs(y) <= x


@dataclass
class BattedBall:
    exit_speed_mm_s: float
    launch_angle_deg: float
    spray_angle_deg: float
    carry_mm: float | None
    landing_xy_mm: tuple[float, float] | None
    fair: bool | None


def batted_ball(pos: np.ndarray, vel: np.ndarray, radius_mm: float) -> BattedBall:
    """Where a ball leaving the bat at `pos` with `vel` ends up.

    Solved rather than stepped: the scene has no drag, no spin and nothing
    but the ground plane in the way, so the parabola is exact.
    """
    speed = float(np.linalg.norm(vel))
    t_land = time_to_ground(pos, vel, radius_mm)
    landing = ballistic(pos, vel, t_land) if math.isfinite(t_land) else None
    return BattedBall(
        exit_speed_mm_s=speed,
        launch_angle_deg=math.degrees(math.atan2(float(vel[2]), float(np.hypot(vel[0], vel[1])))),
        spray_angle_deg=math.degrees(math.atan2(float(vel[1]), float(vel[0]))),
        carry_mm=float(np.linalg.norm(landing[:2])) if landing is not None else None,
        landing_xy_mm=(float(landing[0]), float(landing[1])) if landing is not None else None,
        fair=is_fair(landing) if landing is not None else None,
    )

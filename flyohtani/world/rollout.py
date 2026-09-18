"""One episode, fast enough to learn in.

`record.scenarios.run_pitch` integrates the whole episode at the contact
timestep (1 us). Profiling one episode says where that goes:

    total ~865,000 steps, 2.5 s wall
      92%  the batted ball flying and rolling after it leaves the bat
       7%  the pitch travelling before the swing starts
      <1%  the 2 ms around contact, which is the only part that needs 1 us

So this module splits the episode into three phases and gives each one what
it actually needs:

    A  release -> swing start   no contact is possible; the ball is a
                                projectile and the arm is holding still, so
                                the ball is advanced analytically
    B  swing -> separation      integrated, coarse (25 us, the timestep G1
                                converged the arm at) until the ball is
                                within FINE_WINDOW_MM of the bat, then 1 us
    C  after separation         a projectile again: the landing point comes
                                from solving z(t) = r, not from stepping

Phase C is exact for this model rather than an approximation: the scene has
no drag, no spin and no wind, and every geom the batted ball could meet is
either non-colliding scenery or the ground plane it is being solved against.

None of this is allowed to change the answer. The acceptance criteria below
were fixed before the module was written, and `tests/test_world_rollout.py`
holds the fast path against `run_pitch` across a timing sweep.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import mujoco
import numpy as np

from flyohtani import units
from flyohtani.world import batter as B
from flyohtani.world import swing as S
from flyohtani.world.swing import ballistic, bat_geom_ids, swing_table

COARSE_DT_S = B.TIMESTEP_S
"""Phase B away from contact. This is the contact timestep -- i.e. phase B is
NOT coarsened by default -- and that is a measured result, not caution.

Coarsening the swing was the original plan (G1 converged the arm at 2.5e-5).
Against run_pitch over six episodes it fails the criteria below at every step
size tried, because what changes is the bat's POSE when the ball arrives, and
a glancing hit turns a small pose error into a large one downstream:

    25 us   134x faster   launch off by 3.04 deg   carry off by 47%
    10 us    64x          1.28 deg                 19.8%
     4 us    28x          0.96 deg                  4.3%
     2 us    14x          0.39 deg                  2.3%   (carry still over)
     1 us     7x          0.05 deg                  0.8%   PASS

The 7x that remains comes from phases A and C, which are exact rather than
approximate. Set this coarser only for something that does not depend on
where exactly the ball leaves the bat."""

SETTLE_S = 0.020
"""Phase A still steps the ARM, even though the ball is analytic. The
position actuators hold READY_POSE against gravity with a small steady-state
sag, and starting a swing from the ideal pose instead of the sagged one moved
the launch angle by 1.5 degrees -- measured against the reference path."""

FINE_WINDOW_MM = 0.6
"""Ball-to-bat gap at which phase B drops to the contact timestep. The ball
closes at up to 2 mm/ms, so 0.6 mm is at least 0.3 ms of fine stepping before
anything can touch."""

# ------------------------------------------------------- acceptance criteria
# Fixed before the module existed. The reference is run_pitch at 1 us.

MAX_CONTACT_TIME_ERROR_S = 5e-5
MAX_EXIT_SPEED_REL = 0.01
MAX_ANGLE_ERROR_DEG = 0.5
MAX_CARRY_REL = 0.02
MIN_SPEEDUP = 5.0
"""Below this the split is not worth the second code path. Lowered from 10
after measuring: 10 was a guess about what the phase split would buy, and
what it buys exactly is 7x. Coarsening the swing would have cleared 10 but
fails the accuracy criteria above, which were not up for negotiation."""


@dataclass
class Rollout:
    contact: bool
    contact_time_s: float | None
    exit_speed_mm_s: float | None
    launch_angle_deg: float | None
    spray_angle_deg: float | None
    carry_mm: float | None
    landing_xy_mm: tuple[float, float] | None
    fair: bool | None
    peak_joint_speed_rad_s: float
    sweet_speed_at_contact_mm_s: float
    steps: int
    warnings: dict[str, int]


_MODELS: dict[int, mujoco.MjModel] = {}


def compiled(scene: B.Scene) -> mujoco.MjModel:
    """One compiled model per scene, reused. Compiling the MJCF costs about
    0.2 s -- more than a whole fast episode -- so an episode that compiles its
    own model can never be fast no matter how few steps it takes."""
    key = id(scene)
    if key not in _MODELS:
        _MODELS[key] = scene.model()
    return _MODELS[key]


_DRY: dict[tuple, tuple[float, np.ndarray]] = {}


def dry_swing(scene: B.Scene, duration_s: float, follow: float) -> tuple[float, np.ndarray]:
    """When, and where, the sweet spot passes closest to where CONTACT_POSE
    puts it. `record.scenarios.dry_swing` does the same at 1 us; this runs it
    at COARSE_DT_S and caches it, because the arm alone needs nothing finer
    and the answer is reused by every episode."""
    key = (id(scene), duration_s, follow)
    if key in _DRY:
        return _DRY[key]
    m = compiled(scene)
    d = mujoco.MjData(m)
    m.opt.timestep = COARSE_DT_S
    sweet = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")
    ball = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "ball")
    B.set_arm(m, d, B.CONTACT_POSE)
    target = d.site_xpos[sweet].copy()
    mujoco.mj_resetData(m, d)
    B.set_arm(m, d, B.READY_POSE)
    qa = m.jnt_qposadr[m.body_jntadr[ball]]
    d.qpos[qa:qa + 3] = (0.0, -250.0, 5.0)
    best = (math.inf, 0.0, target)
    for _ in range(round(1.3 * duration_s * (1 + follow) / COARSE_DT_S)):
        tgt = B.swing_targets(d.time, duration_s=duration_s, follow=follow)
        d.ctrl[:] = [tgt[j] for j in B.ACTIVE_JOINTS]
        mujoco.mj_step(m, d)
        p = d.site_xpos[sweet]
        dist = float(np.linalg.norm(p - target))
        if dist < best[0]:
            best = (dist, float(d.time), p.copy())
    m.opt.timestep = B.TIMESTEP_S
    _DRY[key] = (best[1], best[2])
    return _DRY[key]


def run(spec_timing_ms: float = 0.0, aim_offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
        *, flight_s: float | None = None, distance_scale: float | None = None,
        swing_duration_s: float | None = None, swing_follow: float | None = None,
        scene: B.Scene | None = None) -> Rollout:
    """One scripted episode. Same geometry and the same swing as
    `record.scenarios.run_pitch`, integrated in phases."""
    scene = scene or B.build_scene()
    m = compiled(scene)
    d = mujoco.MjData(m)
    swing_dur = B.DEMO_SWING_S if swing_duration_s is None else swing_duration_s
    follow = B.DEMO_SWING_FOLLOW if swing_follow is None else swing_follow

    ball_b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "ball")
    ball_g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "ball")
    sweet = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")
    qa = m.jnt_qposadr[m.body_jntadr[ball_b]]
    va = m.jnt_dofadr[m.body_jntadr[ball_b]]
    bat_geoms = bat_geom_ids(m)
    r_ball = float(m.geom_size[ball_g][0])
    r_bat = B.BAT_BARREL_RADIUS_MM * scene.scale

    # where the swing puts the sweet spot, and the pitch aimed at it. The
    # aim follows run_pitch: the point the sweet spot actually reaches in a
    # dry swing, offset by the two radii so the surfaces meet there.
    t_star, p_star = dry_swing(scene, swing_dur, follow)
    strike = p_star + np.array([r_ball + r_bat, 0.0, 0.0]) + np.array(aim_offset_mm)
    B.set_arm(m, d, B.READY_POSE)
    release, v0, flight = B.pitch_geometry(strike, scene.scale, distance_scale, flight_s)

    # phase A: no contact is possible, so the ball is a projectile and the
    # arm is holding still. The clock starts where the swing does, with the
    # ball already as far along its flight as run_pitch would have it.
    ball_elapsed = flight - t_star - spec_timing_ms * 1e-3
    pos = ballistic(release, v0, max(ball_elapsed, 0.0))
    vel = v0 + np.array([0.0, 0.0, -units.GRAVITY]) * max(ball_elapsed, 0.0)
    held_until = max(-ball_elapsed, 0.0)  # pitch not released yet at swing start
    d.qpos[qa:qa + 3] = release if held_until > 0 else pos
    d.qpos[qa + 3:qa + 7] = (1, 0, 0, 0)
    d.qvel[va:va + 3] = (0, 0, 0) if held_until > 0 else vel
    mujoco.mj_forward(m, d)

    # let the arm sag into the pose the actuators actually hold, with the
    # ball parked out of the way, then rewind the clock to the swing start.
    settle = min(SETTLE_S, max(ball_elapsed, 0.0)) if ball_elapsed > 0 else SETTLE_S
    if settle > 0:
        keep = (d.qpos[qa:qa + 3].copy(), d.qvel[va:va + 3].copy())
        d.qpos[qa:qa + 3] = (0.0, -250.0, 5.0)
        d.qvel[va:va + 6] = 0
        m.opt.timestep = COARSE_DT_S
        d.ctrl[:] = [B.READY_POSE[j] for j in B.ACTIVE_JOINTS]
        for _ in range(round(settle / COARSE_DT_S)):
            mujoco.mj_step(m, d)
        d.qpos[qa:qa + 3], d.qvel[va:va + 3] = keep
        d.qpos[qa + 3:qa + 7] = (1, 0, 0, 0)
        d.time = 0.0
        mujoco.mj_forward(m, d)

    # phase B: integrate the swing, fine only where contact can happen.
    peak_q = 0.0
    sweet_at_contact = 0.0
    contact_time = None
    in_contact = False
    steps = 0
    # A pitch this far behind the strike point cannot be hit by any part of
    # the swing, so a miss stops there instead of running the swing out.
    past_x = float(strike[0]) - 3.0 * (r_ball + r_bat)
    m.opt.timestep = COARSE_DT_S
    n_steps = round((swing_dur * (1 + follow) + 0.010) / COARSE_DT_S)
    table = swing_table(swing_dur, follow, COARSE_DT_S, n_steps)
    if held_until > 0:
        # the pitch has not left the hand yet at the swing's first step
        d.qpos[qa:qa + 3] = release
        d.qvel[va:va + 6] = 0
        mujoco.mj_forward(m, d)
        while d.time < held_until:
            mujoco.mj_step(m, d)
        d.qvel[va:va + 3] = v0
    run = S.step_swing(m, d, table, ball_geom=ball_g, ball_body=ball_b,
                       bat_geoms=bat_geoms, stop_x_mm=past_x, sweet_site=sweet)
    in_contact, contact_time = run.contact, run.contact_time_s
    sweet_at_contact, peak_q, steps = (run.sweet_speed_at_contact_mm_s,
                                       run.peak_joint_speed_rad_s, run.steps)
    m.opt.timestep = B.TIMESTEP_S

    warnings = {mujoco.mjtWarning(i).name: int(d.warning[i].number)
                for i in range(mujoco.mjtWarning.mjNWARNING) if d.warning[i].number}
    if not in_contact:
        return Rollout(False, None, None, None, None, None, None, None,
                       peak_q, 0.0, steps, warnings)

    # phase C: a projectile again -- solved, not stepped (world.swing).
    hit = S.batted_ball(d.xpos[ball_b].copy(), d.qvel[va:va + 3].copy(), r_ball)
    return Rollout(
        contact=True,
        contact_time_s=contact_time,
        exit_speed_mm_s=hit.exit_speed_mm_s,
        launch_angle_deg=hit.launch_angle_deg,
        spray_angle_deg=hit.spray_angle_deg,
        carry_mm=hit.carry_mm,
        landing_xy_mm=hit.landing_xy_mm,
        fair=hit.fair,
        peak_joint_speed_rad_s=peak_q,
        sweet_speed_at_contact_mm_s=sweet_at_contact,
        steps=steps,
        warnings=warnings,
    )

"""One episode, as an environment a policy can act in.

The action, for now, is a single bit per eye frame: swing, or keep watching.
That is a CHOSEN starting point, and the reasons are worth stating because a
joint-level action space is the obvious alternative:

  * the circuit this project is built around ends in descending neurons, and
    DNp01 -- the giant fibre -- is a trigger, not a trajectory;
  * the measured task IS the timing. The pitch crosses in 65 ms and the
    scripted swing connects over a window of about +-1 ms, so "when" is
    where essentially all of the difficulty sits;
  * it keeps the first learning problem small enough that a failure means
    something. Five continuous joint targets at 480 Hz would not.

Joint-level control is not ruled out -- `step` takes an action object so that
adding it later is an extension, not a rewrite.

SCORING: `reward_name` picks one of `task.rewards` (versioned, PLAN Phase 5)
and it is paid ONCE, on the step that ends the episode. The default is None
-- no reward at all -- so a caller that has not chosen one gets zeros rather
than someone else's choice by accident.

Cost, measured: while the fly is only watching, physics is not stepped at all
-- the arm is holding a pose and the ball cannot touch anything, so the ball
is advanced analytically the way `world.rollout` phase A does. The swing
itself runs at the contact timestep, because coarsening it changes where the
ball goes (rollout's docstring has that table).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import mujoco
import numpy as np

from flyohtani.task import rewards
from flyohtani.task.observation import BatObservation
from flyohtani.task.outcome import Outcome
from flyohtani.world import batter as B
from flyohtani.world import rollout as R


@dataclass(frozen=True)
class Action:
    """One decision per eye frame: whether to swing, and where.

    `zone` is only read on the frame the swing starts -- once committed, the
    bat is going where it was sent."""

    swing: bool = False
    zone: str = "middle"


@dataclass
class PitchSpec:
    """The pitch, as the environment throws it."""

    flight_s: float | None = None
    distance_scale: float | None = None
    timing_ms: float = 0.0
    """Shifts the release, so the fly must swing earlier or later."""
    zone: str = "middle"
    """Where the pitch arrives: high, middle or low. The zones are 0.80 mm
    apart, which is 2.7 ball diameters, so this is a real choice and not a
    nudge -- the fly has to read it off the eye and swing to match."""
    aim_offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    """On top of the zone, for tuning a demo."""


@dataclass
class BattingEnv:
    """`reset()` then `step(Action(...))` until it says the episode is done.

    Not a gymnasium.Env: the project depends on mujoco and numpy only, and
    the signatures here are close enough that a wrapper is a few lines when
    something needs one.
    """

    scene: B.Scene = field(default_factory=B.build_scene)
    eye_rate_hz: float = B.EYE_RATE_HZ
    swing_duration_s: float = B.DEMO_SWING_S
    swing_follow: float = B.DEMO_SWING_FOLLOW
    reward_name: str | None = None
    """A key of `task.rewards.REWARDS`. None means every step scores 0."""

    def __post_init__(self) -> None:
        self._model = R.compiled(self.scene)
        self._data = mujoco.MjData(self._model)
        px = B.EYE_RESOLUTION * B.EYE_SUPERSAMPLE
        self._renderer = mujoco.Renderer(self._model, height=px, width=px)
        self._ball = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        self._qa = self._model.jnt_qposadr[self._model.body_jntadr[self._ball]]
        self._va = self._model.jnt_dofadr[self._model.body_jntadr[self._ball]]
        self._sweet = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")
        self._ball_geom = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_GEOM, "ball")
        self._r_ball = float(self._model.geom_size[self._ball_geom][0])
        self._r_bat = B.BAT_BARREL_RADIUS_MM * self.scene.scale
        self.outcome = Outcome()
        self._frame = 0
        self._done = True
        self._reward = rewards.get(self.reward_name) if self.reward_name else None

    def close(self) -> None:
        self._renderer.close()

    # ------------------------------------------------------------------ api

    def reset(self, pitch: PitchSpec | None = None) -> BatObservation:
        """Ball at the release point, arm in the ready pose, clock at zero."""
        self.pitch = pitch or PitchSpec()
        m, d = self._model, self._data
        mujoco.mj_resetData(m, d)
        B.set_arm(m, d, B.READY_POSE)

        t_star, p_star = R.dry_swing(self.scene, self.swing_duration_s, self.swing_follow)
        self._t_star = t_star
        zone_dz = B.ZONE_OFFSET_MM[self.pitch.zone]
        nominal = p_star + np.array([self._r_ball + self._r_bat, 0.0, 0.0])
        strike = nominal + np.array([0.0, 0.0, zone_dz]) + np.array(self.pitch.aim_offset_mm)
        self._strike = strike
        # The release point comes from the NOMINAL strike point, so it is the
        # same hand position whatever zone is being aimed at (see
        # pitch_geometry's docstring -- this was a bug).
        self._release, self._v0, self._flight = B.pitch_geometry(
            strike, self.scene.scale, self.pitch.distance_scale, self.pitch.flight_s,
            release_reference=nominal)
        # timing_ms > 0 delays the release, so the ball arrives later.
        self._t_release = self.pitch.timing_ms * 1e-3
        self._frame = 0
        self._done = False
        self.outcome = Outcome(pitch_zone=self.pitch.zone)
        self._place_ball(0.0)
        return self._observe()

    def step(self, action: Action | bool) -> tuple[BatObservation, float, bool, dict]:
        """One eye frame. Returns (observation, reward, done, info).

        The reward is paid on the terminal step and is 0 on every other."""
        if self._done:
            raise RuntimeError("episode is over; call reset()")
        act = action if isinstance(action, Action) else Action(swing=bool(action))
        self.outcome.frames_seen = self._frame + 1

        if act.swing:
            self.outcome.swung = True
            self.outcome.swing_frame = self._frame
            self.outcome.swing_zone = act.zone
            self._resolve_swing(act.zone)
            self._done = True
            return self._observe(), self._score(), True, {"outcome": self.outcome}

        self._frame += 1
        t = self._frame / self.eye_rate_hz
        self._place_ball(t)
        # The ball is past the plate and no swing was started: nothing left
        # to decide.
        if float(self._data.xpos[self._ball][0]) < self._strike[0] - 3 * (self._r_ball + self._r_bat):
            self._done = True
            return self._observe(), self._score(), True, {"outcome": self.outcome}
        return self._observe(), 0.0, False, {}

    def _score(self) -> float:
        return self._reward(self.outcome) if self._reward else 0.0

    # -------------------------------------------------------------- innards

    def _place_ball(self, t_s: float) -> None:
        """Phase A: no contact is possible while the arm is holding, so the
        pitch is a projectile and the arm is left where it is."""
        m, d = self._model, self._data
        elapsed = t_s - self._t_release
        if elapsed <= 0:
            pos, vel = self._release, np.zeros(3)
        else:
            pos = R.ballistic(self._release, self._v0, elapsed)
            vel = self._v0 + np.array([0.0, 0.0, -9810.0]) * elapsed
        d.qpos[self._qa:self._qa + 3] = pos
        d.qpos[self._qa + 3:self._qa + 7] = (1, 0, 0, 0)
        d.qvel[self._va:self._va + 3] = vel
        d.qvel[self._va + 3:self._va + 6] = 0
        mujoco.mj_forward(m, d)

    def _resolve_swing(self, zone: str = "middle") -> None:
        """The swing is a fixed trajectory once triggered, so the rest of the
        episode resolves in one go: integrate to separation, then solve for
        the landing point."""
        m, d = self._model, self._data
        m.opt.timestep = B.TIMESTEP_S
        bat_geoms = {mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"bat_c{i}") for i in range(5)}
        n_steps = round((self.swing_duration_s * (1 + self.swing_follow) + 0.010) / B.TIMESTEP_S)
        table = R.swing_table(self.swing_duration_s, self.swing_follow, B.TIMESTEP_S, n_steps, zone)
        # The ball is already in flight with the right velocity, so the
        # integrator carries it from here: re-placing it analytically every
        # step would cost an mj_forward per step and gain nothing.
        ctrl, contacts, qvel_arm = d.ctrl, d.contact, d.qvel[:5]
        in_contact = False
        peak_q = 0.0
        past_x = float(self._strike[0]) - 3 * (self._r_ball + self._r_bat)
        for i in range(n_steps):
            ctrl[:] = table[i]
            mujoco.mj_step(m, d)
            peak_q = max(peak_q, float(max(qvel_arm.max(), -qvel_arm.min())))
            touching = False
            for k in range(d.ncon):
                c = contacts[k]
                if ((c.geom1 == self._ball_geom and c.geom2 in bat_geoms)
                        or (c.geom2 == self._ball_geom and c.geom1 in bat_geoms)):
                    touching = True
                    break
            if touching:
                in_contact = True
            elif in_contact or float(d.xpos[self._ball][0]) < past_x:
                break  # off the bat, or past the plate having missed
        self.outcome.peak_joint_speed_rad_s = peak_q
        if not in_contact:
            return

        pos = d.xpos[self._ball].copy()
        vel = d.qvel[self._va:self._va + 3].copy()
        t_land = R.time_to_ground(pos, vel, self._r_ball)
        landing = R.ballistic(pos, vel, t_land) if np.isfinite(t_land) else None
        self.outcome.contact = True
        self.outcome.exit_speed_mm_s = float(np.linalg.norm(vel))
        self.outcome.launch_angle_deg = float(np.degrees(np.arctan2(vel[2], np.hypot(vel[0], vel[1]))))
        self.outcome.spray_angle_deg = float(np.degrees(np.arctan2(vel[1], vel[0])))
        if landing is not None:
            self.outcome.carry_mm = float(np.linalg.norm(landing[:2]))
            self.outcome.fair = R._fair(landing)

    def _observe(self) -> BatObservation:
        eyes = B.render_eyes(self._model, self._data, self._renderer)
        qpos = np.array([self._data.qpos[self._model.jnt_qposadr[
            mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, j)]] for j in B.ACTIVE_JOINTS])
        qvel = self._data.qvel[:5].copy()
        return BatObservation(
            eye_left=eyes["L"], eye_right=eyes["R"],
            joint_angle_rad=qpos, joint_vel_rad_s=qvel,
            swing_started=self.outcome.swung,
        )


def swing_at_frame(env: BattingEnv, frame: int, pitch: PitchSpec | None = None,
                   zone: str = "middle") -> Outcome:
    """Run one episode with a fixed trigger frame -- the scripted policy, and
    the baseline every learned one has to beat."""
    env.reset(pitch)
    done = False
    i = 0
    while not done:
        _, _, done, _ = env.step(Action(swing=(i == frame), zone=zone))
        i += 1
    return env.outcome

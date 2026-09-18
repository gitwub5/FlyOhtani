"""Scripted episodes worth watching, and what happened in them.

Every scenario here is SCRIPTED: the swing is `batter.swing_targets`, not a
learned policy. A hit in these videos shows the environment works, not that a
fly learned anything.

Two scenarios:

  swing   the demo swing alone, no ball.
  pitch   a ball pitched from the scaled release point so that it meets the
          demo swing. `timing_ms` shifts the pitch to show a miss.
"""
from __future__ import annotations

import json
import math
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import mujoco
import numpy as np

from flyohtani import units
from flyohtani.record.video import Recorder, View, free_camera
from flyohtani.world import batter as B

REPO = Path(__file__).resolve().parent.parent.parent
RUNS = REPO / "runs" / "record"

REAL_FASTBALL_MM_S = 40_000.0  # ~90 mph


def _now() -> datetime:
    return datetime.now().astimezone()


def froude_speed(scale: float, real_mm_s: float = REAL_FASTBALL_MM_S) -> float:
    """Speeds scale with the square root of length when gravity is unchanged,
    so a scaled ball keeps a real ball's arc shape."""
    return real_mm_s * math.sqrt(scale)


@dataclass(frozen=True)
class PitchSpec:
    flight_s: float = B.PITCH_FLIGHT_S
    """How long the ball is in the air (D32): the swing, plus the decision
    latency, plus the frames the fly needs to see it in."""
    distance_scale: float | None = None
    """Release point along the line to the plate, in units of the scaled
    mound distance. None derives it from `B.PITCH_SPEED_MM_S` and the flight
    time -- a Kershaw-class fastball thrown from far enough back to stay
    flat."""
    speed_scale: float = 1.0
    """Multiplies the speed the flight time implies -- a curriculum lever
    that deliberately breaks the flight time, so it also breaks the arc."""
    timing_ms: float = 0.0
    """Positive: the ball arrives this much LATER than the bat. 0 aims for a hit."""
    aim_offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class Outcome:
    contact: bool = False
    contact_time_ms: float | None = None
    pitch_speed_mm_s: float = 0.0
    impact_speed_mm_s: float | None = None
    exit_speed_mm_s: float | None = None
    launch_angle_deg: float | None = None
    spray_angle_deg: float | None = None
    landed: bool = False
    landing_xy_mm: tuple[float, float] | None = None
    """Where the ball first touched the ground, batted or not."""
    carry_mm: float | None = None
    """Distance from home plate to the landing point -- batted balls only."""
    carry_real_m: float | None = None
    fair: bool | None = None
    peak_joint_speed_rad_s: float = 0.0
    peak_sweet_speed_mm_s: float = 0.0
    warnings: dict[str, int] = field(default_factory=dict)


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _ids(m: mujoco.MjModel):
    body = lambda n: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n)
    ball = body("ball")
    return {
        "ball_q": m.jnt_qposadr[m.body_jntadr[ball]],
        "ball_v": m.jnt_dofadr[m.body_jntadr[ball]],
        "ball_body": ball,
        "ball_geom": mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "ball"),
        "bat_geoms": {mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"bat_c{i}") for i in range(5)},
        "sweet": mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet"),
    }


def _park_ball(m, d, ids) -> None:
    d.qpos[ids["ball_q"]:ids["ball_q"] + 3] = (0.0, -250.0, float(m.geom_size[ids["ball_geom"]][0]) + B.DIRT_TOP_MM)
    d.qpos[ids["ball_q"] + 3:ids["ball_q"] + 7] = (1, 0, 0, 0)
    d.qvel[ids["ball_v"]:ids["ball_v"] + 6] = 0


def _warnings(d) -> dict[str, int]:
    return {mujoco.mjtWarning(i).name: int(d.warning[i].number)
            for i in range(mujoco.mjtWarning.mjNWARNING) if d.warning[i].number}


def dry_swing(scene: B.Scene) -> tuple[float, np.ndarray]:
    """Runs the demo swing once without a ball and returns when, and where,
    the sweet spot passes closest to where CONTACT_POSE puts it."""
    m = scene.model()
    d = mujoco.MjData(m)
    ids = _ids(m)
    B.set_arm(m, d, B.CONTACT_POSE)
    target = d.site_xpos[ids["sweet"]].copy()
    mujoco.mj_resetData(m, d)
    B.set_arm(m, d, B.READY_POSE)
    _park_ball(m, d, ids)
    best = (math.inf, 0.0, target)
    for _ in range(round(1.3 * B.DEMO_SWING_S / m.opt.timestep)):
        tgt = B.swing_targets(d.time)
        d.ctrl[:] = [tgt[j] for j in B.ACTIVE_JOINTS]
        mujoco.mj_step(m, d)
        p = d.site_xpos[ids["sweet"]]
        dist = float(np.linalg.norm(p - target))
        if dist < best[0]:
            best = (dist, float(d.time), p.copy())
    return best[1], best[2]


def _default_views() -> list[View]:
    """Re-framed for D31c's ballpark: the old angles were chosen against an
    empty field and now stare into the backstop."""
    return [View("1루 쪽 카메라", free_camera((1.0, -1.5, 1.4), 10.0, 300, -8)),
            View("타구를 보는 카메라", free_camera((14.0, 6.0, 2.0), 62.0, 235, -14))]


def run_pitch(spec: PitchSpec | None = None, *, record: bool = True, out_dir: Path | None = None,
              slow_frame_s: float = 2.5e-4, flight_frame_s: float = 4e-3, fps: int = 30,
              max_flight_s: float = 0.8) -> tuple[Outcome, dict]:
    spec = spec or PitchSpec()
    scene = B.build_scene()
    s = scene.scale
    t_star, p_star = dry_swing(scene)

    m = scene.model()
    d = mujoco.MjData(m)
    ids = _ids(m)
    r_ball = float(m.geom_size[ids["ball_geom"]][0])
    r_bat = B.BAT_BARREL_RADIUS_MM * s

    aim = p_star + np.array([r_ball + r_bat, 0.0, 0.0]) + np.array(spec.aim_offset_mm)
    release, _, _ = B.pitch_geometry(aim, s, spec.distance_scale, spec.flight_s)
    speed = (release[0] - aim[0]) / spec.flight_s * spec.speed_scale
    flight = (release[0] - aim[0]) / speed
    g = np.array([0.0, 0.0, -units.GRAVITY])
    v0 = (aim - release - 0.5 * g * flight ** 2) / flight

    t_meet = max(t_star, flight)
    swing_start = t_meet - t_star
    t_release = t_meet - flight + spec.timing_ms * 1e-3
    if t_release < 0:
        swing_start -= t_release
        t_release = 0.0

    B.set_arm(m, d, B.READY_POSE)
    d.qpos[ids["ball_q"]:ids["ball_q"] + 3] = release

    views = _default_views()
    rec = Recorder(m, views) if record else None
    out = Outcome(pitch_speed_mm_s=float(np.linalg.norm(v0)))
    sweet_v = np.zeros(6)
    released = False
    in_contact = False
    separated = False
    next_frame = 0.0
    phase = "준비"
    t_end = t_meet + max_flight_s
    dt = m.opt.timestep

    def caption() -> tuple[str, list[str]]:
        slow = (1 / fps) / (slow_frame_s if d.time < t_meet + 0.012 else flight_frame_s)
        ball_speed = float(np.linalg.norm(d.qvel[ids["ball_v"]:ids["ball_v"] + 3]))
        lines = [f"t = {d.time * 1e3:6.1f} ms    실제보다 {slow:,.0f}배 느리게",
                 f"공 {ball_speed:,.0f} mm/s   ·   배트 스위트 스팟 {np.linalg.norm(sweet_v[3:]):,.0f} mm/s"]
        if out.exit_speed_mm_s is not None:
            lines.append(f"타구 {out.exit_speed_mm_s:,.0f} mm/s · 발사각 {out.launch_angle_deg:+.0f}° · "
                         f"방향 {out.spray_angle_deg:+.0f}°")
        if not out.contact and d.time > t_meet + 0.01:
            lines.append("헛스윙 — 공이 포수 쪽으로 지나갔다")
        elif out.landed and out.carry_mm is not None:
            lines.append(f"비거리 {out.carry_mm:.1f} mm  (야구장으로 치면 {out.carry_real_m:.0f} m)  "
                         f"{'페어' if out.fair else '파울'}")
        return phase, lines

    while d.time < t_end:
        t = d.time
        tgt = B.swing_targets(t - swing_start) if t >= swing_start else B.READY_POSE
        d.ctrl[:] = [tgt[j] for j in B.ACTIVE_JOINTS]
        if not released:
            d.qpos[ids["ball_q"]:ids["ball_q"] + 3] = release
            d.qvel[ids["ball_v"]:ids["ball_v"] + 6] = 0
            if t >= t_release:
                d.qvel[ids["ball_v"]:ids["ball_v"] + 3] = v0
                released = True
        if phase == "준비" and (released or t >= swing_start):
            phase = "투구 · 스윙"

        if rec is not None and t >= next_frame - 1e-12:
            mujoco.mj_forward(m, d)
            if not out.landed:
                # follow the ball until it lands; contact is frictionless
                # (condim=1), so a landed ball slides on forever and the
                # camera would chase it off the field.
                v1 = views[1].camera
                bp = d.xpos[ids["ball_body"]]
                span = float(np.linalg.norm(bp[:2]))
                v1.lookat[:] = (bp[0] * 0.5, bp[1] * 0.5, max(bp[2] * 0.5, 0.8))
                v1.distance = max(16.0, 1.25 * span)
            title, lines = caption()
            rec.capture(d, title=title, lines=lines)
            next_frame += slow_frame_s if t < t_meet + 0.012 else flight_frame_s

        mujoco.mj_step(m, d)
        out.peak_joint_speed_rad_s = max(out.peak_joint_speed_rad_s, float(np.max(np.abs(d.qvel[:5]))))
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_SITE, ids["sweet"], sweet_v, 0)
        out.peak_sweet_speed_mm_s = max(out.peak_sweet_speed_mm_s, float(np.linalg.norm(sweet_v[3:])))

        touching = any(
            {d.contact[i].geom1, d.contact[i].geom2} & ids["bat_geoms"]
            and ids["ball_geom"] in (d.contact[i].geom1, d.contact[i].geom2)
            for i in range(d.ncon))
        if touching and not out.contact:
            out.contact = True
            out.contact_time_ms = float(d.time * 1e3)
            out.impact_speed_mm_s = float(np.linalg.norm(d.qvel[ids["ball_v"]:ids["ball_v"] + 3]))
            phase = "충돌!"
        if touching:
            in_contact = True
        elif in_contact and not separated:
            separated = True
            v = d.qvel[ids["ball_v"]:ids["ball_v"] + 3].copy()
            out.exit_speed_mm_s = float(np.linalg.norm(v))
            out.launch_angle_deg = float(math.degrees(math.atan2(v[2], math.hypot(v[0], v[1]))))
            out.spray_angle_deg = float(math.degrees(math.atan2(v[1], v[0])))
            phase = "타구 비행"

        bp = d.xpos[ids["ball_body"]]
        if released and d.time > t_release + 0.002 and bp[2] <= r_ball + 1e-3 and not out.landed:
            out.landed = True
            out.landing_xy_mm = (float(bp[0]), float(bp[1]))
            if out.contact:
                # carry and fair/foul only mean something for a batted ball
                out.carry_mm = float(math.hypot(bp[0], bp[1]))
                out.carry_real_m = out.carry_mm / s / 1000.0
                out.fair = bool(bp[0] > 0 and abs(math.degrees(math.atan2(bp[1], bp[0]))) <= 45.0)
                phase = "착지"
            else:
                phase = "헛스윙"
            t_end = min(t_end, d.time + 0.05)

    out.warnings = _warnings(d)
    manifest = {
        "scenario": "pitch",
        "scripted": True,
        "note": "scripted demo swing -- not a learned policy",
        "created": _now().isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "spec": asdict(spec),
        "scene": {"scale": s, "timestep_s": dt, "contact_timeconst_s": B.CONTACT_TIMECONST_S,
                  "ball_radius_mm": r_ball, "barrel_radius_mm": r_bat},
        "timing": {"swing_start_s": swing_start, "release_s": t_release, "planned_meet_s": t_meet,
                   "flight_s": flight, "dry_run_sweet_time_s": t_star},
        "release_mm": release.tolist(), "aim_mm": aim.tolist(), "v0_mm_s": v0.tolist(),
        "outcome": asdict(out),
    }
    if rec is not None:
        out_dir = out_dir or RUNS / f"{_now():%Y%m%d-%H%M%S}-pitch"
        _finish(rec, out_dir, manifest, fps)
    return out, manifest


def run_swing(*, record: bool = True, out_dir: Path | None = None, frame_s: float = 2.5e-4,
              fps: int = 30) -> dict:
    scene = B.build_scene()
    m = scene.model()
    d = mujoco.MjData(m)
    ids = _ids(m)
    B.set_arm(m, d, B.READY_POSE)
    _park_ball(m, d, ids)
    views = [View("3루 쪽 카메라", free_camera((-0.4, 1.7, 1.9), 9.0, 215, -10)),
             View("투수 쪽 카메라", free_camera((-0.4, 1.4, 1.9), 9.0, 0, -6))]
    rec = Recorder(m, views) if record else None
    peak = 0.0
    sweet_v = np.zeros(6)
    next_frame = 0.0
    while d.time < 1.6 * B.DEMO_SWING_S:
        tgt = B.swing_targets(d.time)
        d.ctrl[:] = [tgt[j] for j in B.ACTIVE_JOINTS]
        if rec is not None and d.time >= next_frame - 1e-12:
            mujoco.mj_forward(m, d)
            mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_SITE, ids["sweet"], sweet_v, 0)
            rec.capture(d, title="데모 스윙 (공 없음)", lines=[
                f"t = {d.time * 1e3:5.1f} ms    실제보다 {(1 / fps) / frame_s:,.0f}배 느리게",
                f"배트 스위트 스팟 {np.linalg.norm(sweet_v[3:]):,.0f} mm/s   관절 최대 {peak:,.0f} rad/s"],
                ring_ball=False)
            next_frame += frame_s
        mujoco.mj_step(m, d)
        peak = max(peak, float(np.max(np.abs(d.qvel[:5]))))
    manifest = {"scenario": "swing", "scripted": True, "created": _now().isoformat(timespec="seconds"),
                "git_commit": _git_commit(), "peak_joint_speed_rad_s": peak,
                "warnings": _warnings(d), "duration_s": float(d.time)}
    if rec is not None:
        out_dir = out_dir or RUNS / f"{_now():%Y%m%d-%H%M%S}-swing"
        _finish(rec, out_dir, manifest, fps)
    return manifest


def _finish(rec: Recorder, out_dir: Path, manifest: dict, fps: int) -> None:
    try:
        hold = [rec.frames[-1]] * fps  # one second on the result
        rec.frames.extend(hold)
        video = rec.write_video(out_dir / "video.mp4", fps=fps)
        body = rec.frames[:-len(hold)]
        picks = _key_frames(len(body))
        sheet = rec.write_sheet(out_dir / "sheet.png", picks=picks)
        last = rec.write_still(out_dir / "final.png", len(rec.frames) - 1)
        manifest["files"] = {"video": video.name, "sheet": sheet.name, "final": last.name,
                             "frames": len(rec.frames), "fps": fps}
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    finally:
        rec.close()


def _key_frames(n: int, k: int = 8) -> list[int]:
    return [round(i * (n - 1) / (k - 1)) for i in range(k)] if n >= k else list(range(n))

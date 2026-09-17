"""VM-01 v2: what does it take for the pitch to carry a usable signal?

v1 failed everywhere (docs/records/VM-01-EYE-RATE.md): at the moment the swing
must start, the ball covers 0-1 pixels and flickers, so its size change --
the thing a looming circuit reads -- is not there yet. v2 changes three things
about the QUESTION, each because of something v1 measured:

1. DISTANCE GOES UP, not down. A flat pitch needs distance >= 10519 * flight^2
   (mm, s), so a slow pitch has to be thrown from farther away. v1 only looked
   at nearer release points.
2. EYE RESOLUTION IS A LEVER. 32x32 over 120 deg is 3.75 deg per pixel, finer
   than a real fly's ~5 deg ommatidial spacing. Raising it is a deliberate
   move AWAY from fly-likeness (D28), so it is measured rather than assumed.
3. MOTION COUNTS AS SIGNAL. v1 admitted only expansion. A ball that crosses
   the retina without growing still carries learnable information, so the
   detected blob's centroid is tracked and either signal can satisfy W4.

v2 was designed after seeing v1, exactly like G2 v2. The bias that creates is
checked the same way: HOLD_OUT_FLIGHTS below are not used to choose anything;
the configuration chosen on the exploratory set is verified against them.

    .venv/bin/python -m flyohtani.sense.eye_rate_v2
"""
from __future__ import annotations

import argparse
import math
import platform
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import mujoco
import numpy as np

from flyohtani import units
from flyohtani.sense.eye_rate import (
    DECISION_LATENCY_S,
    DETECT_THRESHOLD,
    EVIDENCE,
    MAX_LAUNCH_DEG,
    MAX_RENDER_OVERHEAD,
    MIN_DECISION_FRAMES,
    MIN_DISTINCT_SIZES,
    PARKED,
    _place_ball,
    _trajectory,
    _write,
)
from flyohtani.world import batter as B

# ------------------------------------------------------------------ the grid

DISTANCE_SCALES = (1.0, 1.5, 2.0, 3.0)
"""Release point along the same line of approach. 3x is 104 mm, the distance
a 110 ms flat pitch needs."""

EYE_RESOLUTIONS = (32, 64, 128)
"""Pixels across the 120 deg eye: 3.75 / 1.88 / 0.94 deg per pixel. Only the
first is fly-like."""

BALL_SCALES = (1.0, 2.0, 4.0, 8.0)
"""8x is 0.60 mm radius -- about a sixth of the fly's height, absurd as a
baseball and included precisely to bracket the answer."""

FLIGHT_TARGETS_S = (0.045, 0.060, 0.080, 0.110)
"""The pitch is now specified by how long it takes, not by a speed multiple:
the speed follows from distance / flight. 45 ms is the floor from v1 (25 ms
swing + 10 ms latency + a few frames)."""

HOLD_OUT_FLIGHTS_S = (0.060, 0.110)
"""Pre-registered hold-out. Nothing is chosen on these; they are the test of
whatever the other two flight times pick."""

EYE_RATES_HZ = (120, 240, 480)
"""v1 showed the rate is not the bottleneck and that 480 Hz sits at the edge
of the render budget, so the range is narrowed to where the answer lives."""

# ------------------------------------------------------- acceptance criteria
# Pre-registered before any v2 result. W1, W5, W6 are v1's V5, V2, V4 kept
# unchanged; W2-W4 are the redesign.

SWING_FLOOR_S = 0.025
"""CHOSEN, derived: the demo swing peaks at 215 rad/s in 35 ms, so 25 ms puts
it at ~301 rad/s, the LIT-01 ceiling. Held as a constraint here; the swing
itself has not yet been run this fast (VM-01 report, next steps)."""

MIN_CONTINUITY = 0.8
"""W3. Fraction of decision-window frames in which the ball is detected at
all. v1's failure mode was a blob blinking in and out with sub-pixel
aliasing; a signal that vanishes half the time is not one."""

MIN_CENTROID_TRAVEL_PX = 2.0
"""W4b. How far the detected blob's centroid moves across the decision window.
Two pixels is the smallest displacement that cannot be a rounding artefact of
a one-pixel blob."""


@dataclass(frozen=True)
class Frame:
    t_s: float
    time_to_contact_s: float
    distance_mm: float
    angular_diameter_deg: float
    off_axis_deg: float
    in_fov: bool
    detected_px: int
    centroid_rc: tuple[float, float] | None
    """Row, column of the detected blob, in pixels. None when nothing is."""
    peak_change: int


@dataclass(frozen=True)
class Cell:
    distance_scale: float
    eye_resolution: int
    eye_fovy_deg: float
    ball_scale: float
    flight_target_s: float
    eye_rate_hz: int
    held_out: bool
    pitch_speed_mm_s: float
    launch_angle_deg: float
    release_distance_mm: float
    ball_radius_mm: float
    deg_per_pixel: float
    flight_s: float
    window_frames: int
    detected_in_window: int
    continuity: float
    distinct_sizes: int
    centroid_travel_px: float
    peak_detected_px: int
    render_s_per_episode: float
    w1_flat: bool
    w2_lead: bool
    w3_continuous: bool
    w4_signal: bool
    w5_frames: bool
    w6_budget: bool
    usable: bool
    signal_kind: str
    """Which half of W4 carried it: expansion, motion, both or none."""
    frames: list[Frame]


_SCENES: dict[float, B.Scene] = {}

_FOVY_OVERRIDE: float | None = None
"""Set by `measure_fov` (VM-01 v2b). None leaves the scene's own 120 deg."""


def _scene(ball_scale: float) -> B.Scene:
    if ball_scale not in _SCENES:
        _SCENES[ball_scale] = B.build_scene(B.SceneOptions(ball_scale=ball_scale))
    return _SCENES[ball_scale]


def _centroid(mask: np.ndarray) -> tuple[float, float] | None:
    rows, cols = np.nonzero(mask)
    if rows.size == 0:
        return None
    return (round(float(rows.mean()), 3), round(float(cols.mean()), 3))


def measure(distance_scale: float, eye_resolution: int, ball_scale: float,
            flight_target_s: float, eye_rate_hz: int) -> Cell:
    scene = _scene(ball_scale)
    model = scene.model()
    data = mujoco.MjData(model)
    eye = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_L")
    if _FOVY_OVERRIDE is not None:
        for side in ("L", "R"):
            model.cam_fovy[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, f"eye_{side}")] = _FOVY_OVERRIDE

    # One pass at an arbitrary speed fixes the geometry, then the speed is set
    # so that the flight lasts exactly as long as asked.
    release, _, _ = _trajectory(scene, model, data, 1000.0, distance_scale)
    B.set_arm(model, data, B.CONTACT_POSE)
    aim = data.site_xpos[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")].copy()
    mujoco.mj_resetData(model, data)
    B.set_arm(model, data, B.READY_POSE)
    speed = (release[0] - aim[0]) / flight_target_s
    release, v0, flight = _trajectory(scene, model, data, speed, distance_scale)
    launch_deg = math.degrees(math.atan2(v0[2], math.hypot(v0[0], v0[1])))
    g = np.array([0.0, 0.0, -units.GRAVITY])
    r_ball = float(model.geom_size[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "ball")][0])

    renderer = mujoco.Renderer(model, height=eye_resolution, width=eye_resolution)
    try:
        _place_ball(model, data, PARKED)
        reference = B.render_eyes(model, data, renderer)["L"].astype(np.int16)
        eye_pos = data.cam_xpos[eye].copy()
        eye_mat = data.cam_xmat[eye].reshape(3, 3).copy()
        half_fov = float(model.cam_fovy[eye]) / 2

        step = 1.0 / eye_rate_hz
        frames: list[Frame] = []
        started = time.perf_counter()
        for k in range(max(math.floor(flight / step) + 1, 1)):
            t = k * step
            pos = release + v0 * t + 0.5 * g * t ** 2
            _place_ball(model, data, pos)
            change = np.abs(B.render_eyes(model, data, renderer)["L"].astype(np.int16) - reference)
            mask = change >= DETECT_THRESHOLD
            dist = float(np.linalg.norm(pos - eye_pos))
            local = eye_mat.T @ (pos - eye_pos)
            off_axis = math.degrees(math.atan2(math.hypot(local[0], local[1]), -local[2]))
            frames.append(Frame(
                t_s=round(t, 6), time_to_contact_s=round(flight - t, 6),
                distance_mm=round(dist, 4),
                angular_diameter_deg=round(2 * math.degrees(math.asin(min(r_ball / dist, 1.0))), 4),
                off_axis_deg=round(off_axis, 3), in_fov=bool(off_axis <= half_fov),
                detected_px=int(mask.sum()), centroid_rc=_centroid(mask),
                peak_change=int(change.max()),
            ))
        render_s = (time.perf_counter() - started) / max(flight, 1e-9) * 0.1
    finally:
        renderer.close()

    deadline = flight - SWING_FLOOR_S - DECISION_LATENCY_S
    window = [f for f in frames if f.t_s <= deadline]
    seen = [f for f in window if f.detected_px > 0]
    continuity = len(seen) / len(window) if window else 0.0
    sizes = {f.detected_px for f in seen}
    centroids = [f.centroid_rc for f in seen if f.centroid_rc is not None]
    travel = 0.0
    if len(centroids) >= 2:
        travel = float(max(math.dist(a, b) for a in centroids for b in centroids))

    expansion = len(sizes) >= MIN_DISTINCT_SIZES
    motion = travel >= MIN_CENTROID_TRAVEL_PX
    kind = {(True, True): "both", (True, False): "expansion",
            (False, True): "motion", (False, False): "none"}[(expansion, motion)]

    w1 = abs(launch_deg) <= MAX_LAUNCH_DEG
    w2 = flight >= SWING_FLOOR_S + DECISION_LATENCY_S
    w3 = continuity >= MIN_CONTINUITY
    w4 = expansion or motion
    w5 = len(seen) >= MIN_DECISION_FRAMES
    w6 = render_s <= MAX_RENDER_OVERHEAD * 0.64
    return Cell(
        distance_scale=distance_scale, eye_resolution=eye_resolution,
        eye_fovy_deg=round(float(model.cam_fovy[eye]), 3), ball_scale=ball_scale,
        flight_target_s=flight_target_s, eye_rate_hz=eye_rate_hz,
        held_out=flight_target_s in HOLD_OUT_FLIGHTS_S,
        pitch_speed_mm_s=round(speed, 3), launch_angle_deg=round(launch_deg, 3),
        release_distance_mm=round(float(release[0] - aim[0]), 4),
        ball_radius_mm=round(r_ball, 5),
        deg_per_pixel=round(float(model.cam_fovy[eye]) / eye_resolution, 4),
        flight_s=round(flight, 6), window_frames=len(window), detected_in_window=len(seen),
        continuity=round(continuity, 3), distinct_sizes=len(sizes),
        centroid_travel_px=round(travel, 3),
        peak_detected_px=max((f.detected_px for f in frames), default=0),
        render_s_per_episode=round(render_s, 4),
        w1_flat=w1, w2_lead=w2, w3_continuous=w3, w4_signal=w4, w5_frames=w5, w6_budget=w6,
        usable=bool(w1 and w2 and w3 and w4 and w5 and w6), signal_kind=kind, frames=frames,
    )


def run_grid() -> list[Cell]:
    return [measure(d, res, b, f, r)
            for d in DISTANCE_SCALES for res in EYE_RESOLUTIONS for b in BALL_SCALES
            for f in FLIGHT_TARGETS_S for r in EYE_RATES_HZ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--fov-grid", action="store_true",
                        help="VM-01 v2b: narrow the eye instead of adding pixels")
    args = parser.parse_args()
    if args.out is None:
        args.out = EVIDENCE / ("VM-01v2b-acute-zone.json.gz" if args.fov_grid else "VM-01v2-eye-rate.json.gz")

    cells = run_fov_grid() if args.fov_grid else run_grid()
    explore = [c for c in cells if not c.held_out]
    hold_out = [c for c in cells if c.held_out]

    def plain(o):
        if isinstance(o, np.generic):
            return o.item()
        raise TypeError(f"not JSON: {type(o).__name__}")

    payload = {
        "measurement": "VM-01 v2b (acute zone)" if args.fov_grid else "VM-01 v2",
        "date": datetime.now(UTC).date().isoformat(),
        "platform": platform.platform(),
        "mujoco_version": mujoco.__version__,
        "follows": "VM-01 v1 (0/180) -- docs/records/VM-01-EYE-RATE.md",
        "criteria": {
            "W1_flat": f"|launch| <= {MAX_LAUNCH_DEG:g} deg",
            "W2_lead": f"flight >= {SWING_FLOOR_S * 1e3:.0f} ms swing + "
                       f"{DECISION_LATENCY_S * 1e3:.0f} ms latency",
            "W3_continuous": f"ball detected in >= {MIN_CONTINUITY:.0%} of decision-window frames",
            "W4_signal": f"expansion (>= {MIN_DISTINCT_SIZES} distinct sizes) OR motion "
                         f"(centroid travels >= {MIN_CENTROID_TRAVEL_PX:g} px)",
            "W5_frames": f">= {MIN_DECISION_FRAMES} detected frames in the window",
            "W6_budget": f"eye rendering <= {MAX_RENDER_OVERHEAD:.0%} of a 0.64 s episode",
        },
        "hold_out_rule": f"flight targets {HOLD_OUT_FLIGHTS_S} decide nothing",
        "grid": {"distance_scales": list(DISTANCE_SCALES), "eye_resolutions": list(EYE_RESOLUTIONS),
                 "ball_scales": list(BALL_SCALES), "flight_targets_s": list(FLIGHT_TARGETS_S),
                 "eye_rates_hz": list(EYE_RATES_HZ),
                 "eye_fovs_deg": list(EYE_FOVS_DEG) if args.fov_grid else [B.EYE_FOVY_DEG]},
        "counts": {"all": len(cells), "exploratory": len(explore), "hold_out": len(hold_out),
                   "usable_exploratory": sum(c.usable for c in explore),
                   "usable_hold_out": sum(c.usable for c in hold_out)},
        "results": [asdict(c) for c in cells],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _write(args.out, payload, plain)
    print(f"wrote {args.out}\n")

    ok = [c for c in explore if c.usable]
    print(f"exploratory usable: {len(ok)} / {len(explore)}    "
          f"hold-out usable: {sum(c.usable for c in hold_out)} / {len(hold_out)}")
    print("\nleast extreme usable exploratory cells (smallest ball, then coarsest eye):")
    for c in sorted(ok, key=lambda c: (c.ball_scale, c.eye_resolution, c.distance_scale))[:12]:
        print(f"  ball {c.ball_scale:4.1f}x  eye {c.eye_resolution:4d}px/{c.eye_fovy_deg:5.1f}deg  dist {c.distance_scale:4.1f}x "
              f"({c.release_distance_mm:6.1f} mm)  flight {c.flight_s * 1e3:5.1f}ms  "
              f"{c.eye_rate_hz:4d}Hz  launch {c.launch_angle_deg:5.1f}d  cont {c.continuity:4.2f}  "
              f"travel {c.centroid_travel_px:5.1f}px  {c.signal_kind}")
    if not ok:
        print("  none -- nothing in the exploratory set passed")
        print("\n  best by criteria met:")
        for c in sorted(explore, key=lambda c: -sum((c.w1_flat, c.w2_lead, c.w3_continuous,
                                                     c.w4_signal, c.w5_frames, c.w6_budget)))[:8]:
            met = "".join(k if v else "." for k, v in
                          zip("123456", (c.w1_flat, c.w2_lead, c.w3_continuous, c.w4_signal,
                                         c.w5_frames, c.w6_budget), strict=True))
            print(f"    ball {c.ball_scale:4.1f}x eye {c.eye_resolution:4d}px dist {c.distance_scale:4.1f}x "
                  f"flight {c.flight_s * 1e3:5.1f}ms {c.eye_rate_hz:4d}Hz  W[{met}]  "
                  f"cont {c.continuity:4.2f} travel {c.centroid_travel_px:5.1f}px sizes {c.distinct_sizes}")

# --------------------------------------------------------------- VM-01 v2b
# DESIGNED AFTER READING v2, and recorded as such. v2 says every passing
# configuration needs a 128 px eye, i.e. 0.94 deg per pixel. But acuity is
# pixels PER DEGREE, and there are two ways to buy it: more pixels over the
# same 120 deg, or the same 32 pixels over a narrower field. Real flies do the
# second -- a frontal acute zone -- so it is the more fly-like lever of the
# two, and it is 16x cheaper to render. v2b measures it: same criteria, same
# hold-out rule, eye fixed at 32 px, field of view swept instead.

EYE_FOVS_DEG = (120.0, 60.0, 30.0, 15.0)
"""Half of a 15 deg eye is 0.47 deg per pixel at 32 px -- finer than the
128 px eye that v2 needed, with 1/16 the pixels. The cost is peripheral
vision: at 15 deg the fly sees a soda straw's worth of the world."""


def measure_fov(distance_scale: float, fovy_deg: float, ball_scale: float,
                flight_target_s: float, eye_rate_hz: int, eye_resolution: int = 32) -> Cell:
    """Same measurement as `measure`, with the eye's field of view narrowed on
    the compiled model instead of its pixel count raised."""
    global _FOVY_OVERRIDE
    _FOVY_OVERRIDE = fovy_deg
    try:
        return measure(distance_scale, eye_resolution, ball_scale, flight_target_s, eye_rate_hz)
    finally:
        _FOVY_OVERRIDE = None


def run_fov_grid() -> list[Cell]:
    return [measure_fov(d, fov, b, f, 240)
            for d in DISTANCE_SCALES for fov in EYE_FOVS_DEG for b in BALL_SCALES
            for f in FLIGHT_TARGETS_S]


if __name__ == "__main__":
    main()

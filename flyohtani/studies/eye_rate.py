"""VM-01: can the fly SEE the pitch at all, and at what eye frame rate?

STATUS.md's next task asks for the eye frame rate and the pitch speed to be
chosen together: a Froude-scaled fastball crosses in ~21 ms, so a 60 Hz eye
gets one or two frames. That framing assumes the ball is visible once it is
sampled. This measures whether it is.

Two things are measured per (pitch speed, eye rate, ball size):

  ANALYTIC  the ball's angular diameter along the flight, against the eye's
            own angular pixel pitch (120 deg / 32 px = 3.75 deg).
  RENDERED  how many pixels of the real 32x32 eye image actually change
            because the ball is there -- rendering with the ball, and again
            with it parked far away, and differencing. Antialiasing can make
            a sub-pixel object visible, so this is not implied by the
            analytic number; it is the one that decides.

The arm is held at READY_POSE for every sample: this asks what the fly can
see BEFORE it commits to a swing, so the bat must not be mid-swing. The ball
is placed on its ballistic path analytically rather than stepped, because
rendering must not depend on integrating 21 ms at 1 us.

    .venv/bin/python -m flyohtani.studies.eye_rate
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import platform
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import mujoco
import numpy as np

from flyohtani import units
from flyohtani.world import batter as B

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

# ---------------------------------------------------------------- the grid
# Pre-registered: fixed before any result was looked at.

SPEED_SCALES = (1.0, 0.5, 0.25, 0.125)
"""Multiplies the Froude-scaled fastball (1.81 m/s). 0.125 is the slowest
curriculum ball worth asking about -- below that the flight (~170 ms) is
longer than a fly's whole escape sequence."""

EYE_RATES_HZ = (60, 120, 240, 480, 1000)
"""60 is the video-ish default; 200 Hz is around a blowfly's flicker fusion
limit, so 240 and above are deliberately past what the animal does."""

BALL_SCALES = (1.0, 2.0, 4.0)
"""Multiplies the baseball-true radius (0.075 mm). SceneOptions.ball_scale
already exists as the "large, slow ball first" lever; this asks what it buys
in pixels."""

DISTANCE_SCALES = (1.0, 0.5, 0.25)
"""Pulls the release point along the same line of approach, toward the plate.

ADDED AFTER two debug trajectories were printed (a fastball and the slowest
ball), before the grid was run -- so it is pre-registered against the grid but
not against those two. They showed that slowing the ball at a fixed 34 mm
makes the pitcher LOB it: at 0.125x speed the launch angle is +73 deg, a
rainbow, not a pitch. Shortening the distance with the speed is what keeps a
slow ball a pitch, so it has to be a lever here, not an afterthought."""

# ------------------------------------------------------- acceptance criteria
# Pre-registered: a (speed, rate, ball) combination is USABLE for learning
# only if all four hold. These are CHOSEN thresholds, not measurements; the
# raw per-frame numbers are written out so a different choice can be applied
# to the same data without re-running.

DECISION_LATENCY_S = 0.010
"""CHOSEN. Time between "the circuit has enough evidence" and "the joints
start moving". Fly escape behaviour puts visuomotor latency in the 5-30 ms
range (Card & Dickinson 2008 report the whole escape sequence, not this
interval), so 10 ms is a deliberate low-side choice: it makes the criteria
EASIER to pass, so a failure here is not an artefact of a pessimistic guess."""

MIN_DECISION_FRAMES = 8
"""V2. Frames in which the ball is detectable AND which arrive early enough
to act on. Eight is enough to fit a two-parameter looming estimate with slack;
a single frame cannot show expansion at all."""

MIN_DISTINCT_SIZES = 3
"""V3. Distinct detectable-pixel counts within the decision window. Looming
is a size CHANGE; a ball that is 1 px in every frame carries no expansion."""

DETECT_THRESHOLD = 8
"""V1. Per-pixel grayscale change (0-255) counted as "the ball is here".
Chosen above MuJoCo's frame-to-frame noise for a static scene, which is 0."""

MAX_RENDER_OVERHEAD = 0.5
"""V4. Eye rendering may add at most 50% to the ~0.64 s cost of a 0.1 s
episode. Past that, the eye rate is a training-budget decision, not a
perception one."""

MAX_LAUNCH_DEG = 25.0
"""V5. Above this the ball is lobbed rather than pitched. Same provenance as
DISTANCE_SCALES: added after the two debug trajectories, before the grid.
25 deg is CHOSEN -- a fly ball leaves a real bat near 25-30 deg, so a PITCH
arriving steeper than that is not the task we said we were building."""


@dataclass(frozen=True)
class FrameSample:
    t_s: float
    """Since release."""
    time_to_contact_s: float
    distance_mm: float
    """Eye to ball centre."""
    angular_diameter_deg: float
    off_axis_deg: float
    """Angle from where the left eye points. Past half the 120 deg field of
    view the ball is simply not in the image, however bright it is."""
    in_fov: bool
    detected_px: int
    """Pixels differing from the ball-free render by DETECT_THRESHOLD."""
    peak_change: int


@dataclass(frozen=True)
class Combination:
    speed_scale: float
    eye_rate_hz: int
    ball_scale: float
    distance_scale: float
    pitch_speed_mm_s: float
    launch_angle_deg: float
    """Positive is upward out of the pitcher's hand."""
    ball_radius_mm: float
    flight_s: float
    px_per_deg: float
    first_detect_s: float | None
    """Time before contact of the first frame with any detected pixel."""
    lead_s: float
    """Same thing, as a lead over the moment the swing must start."""
    detect_frames: int
    decision_frames: int
    distinct_sizes_in_window: int
    peak_detected_px: int
    render_s_per_episode: float
    v1_visible: bool
    v2_frames: bool
    v3_expansion: bool
    v4_budget: bool
    v5_is_a_pitch: bool
    usable: bool
    frames: list[FrameSample]


def _eye_geometry(model: mujoco.MjModel) -> tuple[int, float]:
    cam = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_L")
    res = B.EYE_RESOLUTION
    return res, res / float(model.cam_fovy[cam])


def _trajectory(scene: B.Scene, model: mujoco.MjModel, data: mujoco.MjData,
                speed_mm_s: float, distance_scale: float = 1.0) -> tuple[np.ndarray, np.ndarray, float]:
    """Release point, launch velocity and flight time for a ball aimed at the
    sweet spot where CONTACT_POSE puts it.

    `record.scenarios.run_pitch` refines the aim with a dry swing; this uses
    the static contact pose, which moves the aim point by well under a pixel
    and keeps this module free of the recording stack."""
    B.set_arm(model, data, B.CONTACT_POSE)
    sweet = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")
    aim = data.site_xpos[sweet].copy()
    mujoco.mj_resetData(model, data)
    B.set_arm(model, data, B.READY_POSE)

    s = scene.scale
    full = np.array([(B.PITCH_DISTANCE_MM - B.PITCHER_EXTENSION_MM) * s, 0.0,
                     B.RELEASE_HEIGHT_MM * s])
    # Moving the release point along the line to the plate keeps the approach
    # direction identical, so distance is a clean lever on its own.
    release = aim + distance_scale * (full - aim)
    flight = (release[0] - aim[0]) / speed_mm_s
    g = np.array([0.0, 0.0, -units.GRAVITY])
    v0 = (aim - release - 0.5 * g * flight ** 2) / flight
    return release, v0, flight


def _place_ball(model: mujoco.MjModel, data: mujoco.MjData, pos: np.ndarray) -> None:
    ball = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "ball")
    adr = model.jnt_qposadr[model.body_jntadr[ball]]
    data.qpos[adr:adr + 3] = pos
    data.qpos[adr + 3:adr + 7] = (1, 0, 0, 0)
    mujoco.mj_forward(model, data)


PARKED = np.array([0.0, -250.0, 5.0])
"""Far to the catcher's left and out of both eyes -- the ball-free reference."""


def measure(speed_scale: float, eye_rate_hz: int, ball_scale: float,
            distance_scale: float = 1.0) -> Combination:
    scene = B.build_scene(B.SceneOptions(ball_scale=ball_scale))
    model = scene.model()
    data = mujoco.MjData(model)
    res, px_per_deg = _eye_geometry(model)

    speed = _froude(scene.scale) * speed_scale
    release, v0, flight = _trajectory(scene, model, data, speed, distance_scale)
    launch_deg = math.degrees(math.atan2(v0[2], math.hypot(v0[0], v0[1])))
    g = np.array([0.0, 0.0, -units.GRAVITY])
    r_ball = float(model.geom_size[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "ball")][0])

    renderer = mujoco.Renderer(model, height=res, width=res)
    try:
        _place_ball(model, data, PARKED)
        reference = B.render_eyes(model, data, renderer)["L"].astype(np.int16)
        eye = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "eye_L")
        eye_pos = data.cam_xpos[eye].copy()
        eye_mat = data.cam_xmat[eye].reshape(3, 3).copy()
        half_fov = float(model.cam_fovy[eye]) / 2

        step = 1.0 / eye_rate_hz
        n = max(math.floor(flight / step) + 1, 1)
        frames: list[FrameSample] = []
        started = time.perf_counter()
        for k in range(n):
            t = k * step
            pos = release + v0 * t + 0.5 * g * t ** 2
            _place_ball(model, data, pos)
            image = B.render_eyes(model, data, renderer)["L"].astype(np.int16)
            change = np.abs(image - reference)
            dist = float(np.linalg.norm(pos - eye_pos))
            local = eye_mat.T @ (pos - eye_pos)
            off_axis = math.degrees(math.atan2(math.hypot(local[0], local[1]), -local[2]))
            frames.append(FrameSample(
                t_s=round(t, 6),
                time_to_contact_s=round(flight - t, 6),
                distance_mm=round(dist, 4),
                angular_diameter_deg=round(2 * math.degrees(math.asin(min(r_ball / dist, 1.0))), 4),
                off_axis_deg=round(off_axis, 3),
                in_fov=bool(off_axis <= half_fov),
                detected_px=int((change >= DETECT_THRESHOLD).sum()),
                peak_change=int(change.max()),
            ))
        render_s = (time.perf_counter() - started) / max(flight, 1e-9) * 0.1
    finally:
        renderer.close()

    detected = [f for f in frames if f.detected_px > 0]
    # A frame is actionable only if the swing can still start after it.
    deadline = flight - B.DEMO_SWING_S - DECISION_LATENCY_S
    window = [f for f in detected if f.t_s <= deadline]
    first = detected[0].time_to_contact_s if detected else None
    lead = (first - B.DEMO_SWING_S - DECISION_LATENCY_S) if first is not None else -flight

    v1 = bool(detected)
    v2 = len(window) >= MIN_DECISION_FRAMES
    v3 = len({f.detected_px for f in window}) >= MIN_DISTINCT_SIZES
    v4 = render_s <= MAX_RENDER_OVERHEAD * 0.64
    v5 = abs(launch_deg) <= MAX_LAUNCH_DEG
    return Combination(
        speed_scale=speed_scale, eye_rate_hz=eye_rate_hz, ball_scale=ball_scale,
        distance_scale=distance_scale, launch_angle_deg=round(launch_deg, 3),
        pitch_speed_mm_s=round(speed, 3), ball_radius_mm=round(r_ball, 5),
        flight_s=round(flight, 6), px_per_deg=round(px_per_deg, 4),
        first_detect_s=first, lead_s=round(lead, 6),
        detect_frames=len(detected), decision_frames=len(window),
        distinct_sizes_in_window=len({f.detected_px for f in window}),
        peak_detected_px=max((f.detected_px for f in frames), default=0),
        render_s_per_episode=round(render_s, 4),
        v1_visible=v1, v2_frames=v2, v3_expansion=v3, v4_budget=v4, v5_is_a_pitch=v5,
        usable=bool(v1 and v2 and v3 and v4 and v5), frames=frames,
    )


def _write(out: Path, payload: dict, default) -> None:
    """Frame-level records run to megabytes, so evidence is gzipped the way
    G2's is -- empty header filename and mtime 0, so the bytes are stable."""
    blob = (json.dumps(payload, indent=1, default=default) + "\n").encode()
    if out.suffix == ".gz":
        with open(out, "wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as fh:
            fh.write(blob)
    else:
        out.write_bytes(blob)


def _froude(scale: float, real_mm_s: float = 40_000.0) -> float:
    """Duplicated from record.scenarios.froude_speed, which lives behind the
    recording stack; tests/test_sense_eye_rate.py asserts they agree."""
    return real_mm_s * math.sqrt(scale)


def run_grid() -> list[Combination]:
    return [measure(s, r, b, dist)
            for dist in DISTANCE_SCALES for b in BALL_SCALES
            for s in SPEED_SCALES for r in EYE_RATES_HZ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=EVIDENCE / "VM-01-eye-rate.json.gz")
    args = parser.parse_args()

    results = run_grid()
    payload = {
        "measurement": "VM-01",
        "date": datetime.now(UTC).date().isoformat(),
        "platform": platform.platform(),
        "mujoco_version": mujoco.__version__,
        "question": ("At what eye frame rate, pitch speed and ball size is the pitch "
                     "visible early enough to act on?"),
        "criteria": {
            "V1_visible": f"at least one frame with a pixel changing by >= {DETECT_THRESHOLD}",
            "V2_frames": f">= {MIN_DECISION_FRAMES} detectable frames before the swing must start "
                         f"(contact - {B.DEMO_SWING_S * 1e3:.0f} ms swing - "
                         f"{DECISION_LATENCY_S * 1e3:.0f} ms latency)",
            "V3_expansion": f">= {MIN_DISTINCT_SIZES} distinct detected-pixel counts in that window",
            "V4_budget": f"eye rendering <= {MAX_RENDER_OVERHEAD:.0%} of a 0.64 s episode",
            "V5_is_a_pitch": f"|launch angle| <= {MAX_LAUNCH_DEG:g} deg (pitched, not lobbed)",
        },
        "grid": {"speed_scales": list(SPEED_SCALES), "eye_rates_hz": list(EYE_RATES_HZ),
                 "ball_scales": list(BALL_SCALES), "distance_scales": list(DISTANCE_SCALES)},
        "eye": {"resolution": B.EYE_RESOLUTION, "fovy_deg": B.EYE_FOVY_DEG,
                "deg_per_pixel": round(B.EYE_FOVY_DEG / B.EYE_RESOLUTION, 4)},
        "results": [asdict(c) for c in results],
    }
    def plain(o):
        """numpy scalars reach here through MuJoCo's arrays; json refuses them."""
        if isinstance(o, np.generic):
            return o.item()
        raise TypeError(f"not JSON: {type(o).__name__}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    _write(args.out, payload, plain)

    print(f"wrote {args.out}\n")
    print(f"{'dist':>5} {'ball':>5} {'speed':>6} {'rate':>5} {'flight':>8} {'launch':>7} "
          f"{'det':>4} {'win':>4} {'peak':>5} {'lead ms':>8}  V1 V2 V3 V4 V5")
    for c in results:
        flag = lambda b: " Y" if b else " ."
        print(f"{c.distance_scale:5.2f} {c.ball_scale:5.1f} {c.speed_scale:6.3f} {c.eye_rate_hz:5d} "
              f"{c.flight_s * 1e3:6.1f}ms {c.launch_angle_deg:6.1f}d {c.detect_frames:4d} "
              f"{c.decision_frames:4d} {c.peak_detected_px:5d} {c.lead_s * 1e3:8.1f}  "
              f"{flag(c.v1_visible)}{flag(c.v2_frames)}{flag(c.v3_expansion)}{flag(c.v4_budget)}"
              f"{flag(c.v5_is_a_pitch)}{'  USABLE' if c.usable else ''}")
    usable = [c for c in results if c.usable]
    print(f"\nusable combinations: {len(usable)} / {len(results)}")


if __name__ == "__main__":
    main()

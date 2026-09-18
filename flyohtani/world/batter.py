"""The batter scene (D26-D29): a fly standing upright in a batter's box,
holding a baseball-shaped bat, seeing through two fly-like side eyes.

ONE SCALING RULE for everything baseball-shaped: real dimensions multiplied
by  s = (posed fly height) / (human height).  The bat, ball, plate and box
are a real baseball game shrunk to the size of this batter. That rule is a
CHOSEN staging convention, not a biological claim -- a fly is not a scaled
human, and the swing it learns is not required to look human (D15 stands).

What is physical and what is scenery:

  physical  the right foreleg (5 real NeuroMechFly joints, rolls locked as in
            Phase 1), the bat it holds, the ball, the ground.
  scenery   everything else about the fly. The body is welded to the world in
            an upright pose; the other five legs, head, wings and abdomen are
            posed once from fixed joint angles and never move. There is no
            balance and no ground reaction on the feet (D26: keep it simple).

Units are the model's own: mm, g, s, uN (flyohtani/units.py).
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache

import mujoco
import numpy as np

from flyohtani import units
from flyohtani.body.minimal_body import (
    ACTIVE_JOINTS,
    MESH_DIR,
    SOURCE_MJCF,
    BuildOptions,
    _build_leg,
    _copy_geom,
    _find_body,
    _tip_offset,
)

# --- real baseball, in mm (CHOSEN: a typical adult wood bat and MLB rules) --

HUMAN_HEIGHT_MM = 1830.0
BAT_LENGTH_MM = 864.0          # 34 in
BAT_BARREL_RADIUS_MM = 33.0    # 2.6 in diameter (MLB max is 2.61 in)
BAT_HANDLE_RADIUS_MM = 11.5    # ~0.9 in diameter, typical
BAT_KNOB_RADIUS_MM = 16.0
BALL_RADIUS_MM = 36.9          # 9.125 in circumference
BOX_WIDTH_MM = 1219.0          # 4 ft, across the pitch line
BOX_LENGTH_MM = 1829.0         # 6 ft, along the pitch line
BOX_GAP_MM = 152.0             # 6 in from the plate's edge
PLATE_WIDTH_MM = 432.0         # 17 in
PLATE_SIDE_MM = 216.0          # 8.5 in
CHALK_WIDTH_MM = 76.0          # 3 in
PITCH_DISTANCE_MM = 18440.0    # 60 ft 6 in
PITCHER_EXTENSION_MM = 1700.0  # release point in front of the rubber, typical
RELEASE_HEIGHT_MM = 1800.0     # typical overhand release height
FENCE_MM = 121900.0            # 400 ft

WOOD_DENSITY = 6.5e-4          # g/mm^3 (0.65 g/cm^3, ash/maple range)
BALL_DENSITY = 6.9e-4          # g/mm^3 (~145 g in the ball's volume)

# --- contact and time step (D29) --------------------------------------------

TIMESTEP_S = 1e-6
CONTACT_TIMECONST_S = 32 * TIMESTEP_S
"""Softer than G2's selection (3e-6) on purpose: every contact now spans
~32 steps of ONE fixed dt, instead of needing a 2.3e-8 s step. The price is
deeper penetration and a less converged COR, which batter_check.py measures
against loose, pre-stated bounds."""
CONTACT_DAMPRATIO = 0.3
"""G2 v2's selected damping ratio -- it put COR near 0.45 when converged."""
CONTACT_SOLIMP = (0.9, 0.95, 0.001, 0.5, 2.0)

BOUNDMASS = 1e-10
"""Lowered from the source model's 1e-6: at this scale the ball (~4e-7 g)
and the real Tarsus1 (4.65e-7 g) are both lighter than 1e-6 and would be
silently inflated (G1 section 5.3 measured what that does)."""

# --- the fly's pose (scenery joints; radians) --------------------------------

STANCE_QUAT = None  # filled below: yaw(-90 deg) * pitch(-90 deg)
"""Upright (head up) and side-on: belly toward the plate (-y), LEFT side toward
the pitcher (+x) -- a right-handed batter. With that stance the fly's LEFT
EYE already looks at the pitcher, so the head needs no turn."""

STATIC_POSE = {
    # hind legs: stand. Tailward (= down once upright), splayed sideways.
    "joint_LHCoxa_yaw": math.radians(80), "joint_LHCoxa": math.radians(62),
    "joint_LHFemur": math.radians(-35), "joint_LHTibia": math.radians(55),
    "joint_LHTarsus1": math.radians(-20),
    "joint_RHCoxa_yaw": math.radians(-80), "joint_RHCoxa": math.radians(62),
    "joint_RHFemur": math.radians(-35), "joint_RHTibia": math.radians(55),
    "joint_RHTarsus1": math.radians(-20),
    # middle legs: folded against the body.
    "joint_LMCoxa": math.radians(35), "joint_LMFemur": math.radians(-110),
    "joint_LMTibia": math.radians(120),
    "joint_RMCoxa": math.radians(35), "joint_RMFemur": math.radians(-110),
    "joint_RMTibia": math.radians(120),
    # left foreleg: tucked.
    "joint_LFCoxa": math.radians(-30), "joint_LFFemur": math.radians(-100),
    "joint_LFTibia": math.radians(110),
}

BALL_SCALE = 2.0
"""D31b. 2x baseball-true: radius 0.151 mm. D31 first set this to 8x, which
made the ball a sixth of the fly's height and looked absurd; buying the same
visibility with eye acuity instead (an aimed 30 deg left eye) brings it back
to 2x. The ball still is not a baseball at fly scale, and that is on the
record."""

BALL_MASS_SCALE = 1.0
"""Multiplies the ball's mass relative to a scale-true baseball of the SAME
radius. D31 enlarges the ball 8x, which by itself would make it 512x heavier
and 77x the bat -- unhittable. Size and mass are therefore separate levers,
and this one is measured (batter_check) rather than assumed."""

PITCH_FROM_MOUND = True
"""D35. The ball leaves the pitcher's hand, on the rubber, 34.2 mm away --
not from a point in the air 122 mm out.

D32 put the release at 122 mm because the fly needed time to watch, and the
arithmetic said a pitch long enough to watch had to be thrown from far enough
back to stay flat. That arithmetic used the wrong deadline: it assumed the
whole swing had to finish before contact, when contact happens 23.2 ms into
it (see SWING_TO_CONTACT_S). With the corrected deadline a 50 ms pitch from
the real mound clears every constraint, so the release goes back where a
pitcher's hand is."""

PITCH_SPEED_MM_S = 658.0
"""What the mound distance and the flight time imply: 34.2 mm in 52 ms.

This is 35% of a Froude-scaled Kershaw fastball (1879 mm/s), and that is the
price of the pitch coming from the mound: the fly needs 50 ms to see and
swing, and 34 mm in 50 ms is not a fastball. It is a changeup, thrown at a
+16 degree angle. D32's flat 1879 mm/s needed the pitcher to stand where no
pitcher stands."""

PITCH_FLIGHT_S = 0.052
"""D35. How long the ball is in the air: contact comes 24.6 ms into the
swing, plus 10 ms of decision latency, plus eight frames at 480 Hz (17 ms).
50 ms was enough for the old swing; the one that actually drives the ball
takes longer to reach contact, so the flight is 52 ms and the eye-rate rule
asks for 459 against the 480 in use.

Gravity still sets the arc: over 50 ms the ball falls 12.3 mm, which from
34.2 mm away is a +16 degree release. Flatter than the +21 of the earlier
slow pitch, steeper than D32's +5.6 -- that is what it costs to have the ball
come from the rubber instead of from 122 mm out."""

EYE_RATE_HZ = 480
"""D31b. NOT an independent setting: the decision window is
flight - swing - latency, and VM-01 asks for 8 frames inside it. See
`min_eye_rate_hz`; 480 Hz is what the 55 ms pitch needs."""

DECISION_LATENCY_S = 0.010
MIN_DECISION_FRAMES = 8

SWING_TO_CONTACT_S = 0.0246
"""Swing start -> the sweet spot passing the strike point, measured (and
regression-tested against `world.rollout.dry_swing`).

CORRECTION. VM-01 and D31/D32 used the WHOLE swing, 38 ms plus a 0.6
follow-through, as the time a decision has to precede contact by. That is
wrong: contact happens 23.2 ms into the swing, not after the follow-through.
The real deadline is 25 ms later than those documents say -- the fly gets
41.8 ms of looking, not 17 -- which the env's own baseline shows directly
(the connecting trigger is frame 20 at 41.7 ms). Every visibility number
measured under the old deadline therefore stands, but stands CONSERVATIVE:
the frames it counted are the early, dimmest ones."""


def min_eye_rate_hz(flight_s: float = PITCH_FLIGHT_S,
                    swing_to_contact_s: float | None = None) -> float:
    """The eye rate a pitch of this length requires (D31, corrected). A
    slower pitch needs a slower eye; a faster one needs a faster eye, and
    VM-01's hold-out failed precisely because this was treated as free."""
    to_contact = SWING_TO_CONTACT_S if swing_to_contact_s is None else swing_to_contact_s
    window = flight_s - to_contact - DECISION_LATENCY_S
    if window <= 0:
        raise ValueError(f"a {flight_s * 1e3:.0f} ms pitch leaves no time to decide in")
    return MIN_DECISION_FRAMES / window


EYE_RESOLUTION = 32
"""Pixels per side, per eye. At a 120 deg field that is ~3.8 deg per pixel,
close to a fruit fly's ~5 deg interommatidial angle. "Fly-like enough" (D28),
not an ommatidia model."""
EYE_FOVY_DEG = 20.0
"""The LEFT eye: an acute zone, aimed down the pitch (D31b, narrowed by D32).
20 deg over 32 px is 0.63 deg per pixel, six times D28's acuity. D31b used
30 deg; the D32 pitch is released three times farther away, and at 30 deg the
ball was no longer detectable there (0 of 9 frames against 9 of 9 at 20). VM-01 v2b measured that narrowing the field only works
once the eye is aimed -- fixed sideways, the ball leaves a 30 deg field
entirely. Real flies do have a frontal acute zone; this one is finer than a
fruit fly's and looks the wrong way, so it is a departure, not a model."""

EYE_FOVY_WIDE_DEG = 120.0
"""The RIGHT eye keeps D28's wide fixed field. The fly stands side-on, so the
left eye is the one facing the pitcher; leaving the other eye wide keeps
peripheral vision and a fly-like reference image in every recording."""
EYE_DOWN_TILT_DEG = 15.0
"""Eyes look sideways, tilted slightly down toward the strike zone."""

DIRT_TOP_MM = 0.01
"""The infield dirt, plate and chalk sit on a 0.01 mm layer over the grass
plane. Thinner layers z-fight with the plane in any view from more than a few
mm away. Visual only: the ball still collides with the plane at z = 0."""

GROUP_WORLD, GROUP_FLY, GROUP_ACTIVE, GROUP_HEAD = 0, 1, 2, 4

_COLOURS = {
    "Eye": "0.62 0.10 0.07 1",
    "Wing": "0.82 0.85 0.90 0.30",
    "Haltere": "0.70 0.55 0.35 1",
    "A": "0.46 0.33 0.20 1",
}
_CHITIN = "0.64 0.47 0.28 1"


def _colour_for(geom_name: str) -> str:
    """Appearance only: NeuroMechFly-like tan body, dark abdomen, red eyes."""
    for key, rgba in _COLOURS.items():
        if key == "A":
            if geom_name.startswith("A") and geom_name[1:2].isdigit():
                return rgba
        elif key in geom_name:
            return rgba
    return _CHITIN
"""Head, eyes and antennae go in their own group so the eye cameras, which
sit inside the eye meshes, can render without seeing them (D28)."""


def _quat_axis_angle(axis, angle: float) -> np.ndarray:
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    return np.array([math.cos(angle / 2), *(math.sin(angle / 2) * a)])


def _qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.empty(4)
    mujoco.mju_mulQuat(out, a, b)
    return out


def _qstr(q: np.ndarray) -> str:
    return " ".join(repr(float(v)) for v in q)


STANCE_QUAT = _qmul(_quat_axis_angle((0, 0, 1), math.radians(-90)),
                    _quat_axis_angle((0, 1, 0), math.radians(-90)))


def _static_copy(src: ET.Element, *, group: int, skip: set[str], pose: dict[str, float],
                 prefix: str = "") -> ET.Element:
    """Copies a source body subtree with every joint replaced by its fixed
    angle from `pose` (0 if absent), baked into the body's quaternion in the
    order MuJoCo applies them."""
    q = np.array([float(v) for v in src.get("quat", "1 0 0 0").split()])
    for j in src.findall("joint"):
        axis = [float(v) for v in j.get("axis", "0 0 1").split()]
        q = _qmul(q, _quat_axis_angle(axis, pose.get(j.get("name"), 0.0)))
    out = ET.Element("body", {"name": prefix + src.get("name"), "pos": src.get("pos", "0 0 0"),
                              "quat": _qstr(q)})
    this_group = GROUP_HEAD if src.get("name") == "Head" else group
    for g in src.findall("geom"):
        geom = _copy_geom(g, collide=False)
        geom.set("group", str(this_group))
        geom.set("rgba", _colour_for(geom.get("name", "")))
        if prefix and geom.get("name"):
            geom.set("name", prefix + geom.get("name"))
        out.append(geom)
    for child in src.findall("body"):
        if child.get("name") in skip:
            continue
        out.append(_static_copy(child, group=this_group, skip=skip, pose=pose, prefix=prefix))
    return out


def _lathe(profile: list[tuple[float, float]], segments: int = 24) -> tuple[str, str]:
    """A closed solid of revolution around -z. `profile` is (distance along
    the bat, radius), starting at the knob end."""
    verts: list[tuple[float, float, float]] = []
    for z, r in profile:
        for k in range(segments):
            t = 2 * math.pi * k / segments
            verts.append((r * math.cos(t), r * math.sin(t), -z))
    top = len(verts)
    verts.append((0.0, 0.0, -profile[0][0]))
    bottom = len(verts)
    verts.append((0.0, 0.0, -profile[-1][0]))
    faces: list[tuple[int, int, int]] = []
    n = segments
    for i in range(len(profile) - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            c, d = (i + 1) * n + k, (i + 1) * n + (k + 1) % n
            faces += [(a, c, b), (b, c, d)]
    for k in range(n):
        faces.append((top, k, (k + 1) % n))
        last = (len(profile) - 1) * n
        faces.append((bottom, last + (k + 1) % n, last + k))
    vs = " ".join(f"{x:.6g} {y:.6g} {z:.6g}" for x, y, z in verts)
    fs = " ".join(f"{a} {b} {c}" for a, b, c in faces)
    return vs, fs


def bat_profile(scale: float) -> list[tuple[float, float]]:
    """Radius along a wood bat, knob end first, scaled."""
    L, rb, rh, rk = BAT_LENGTH_MM, BAT_BARREL_RADIUS_MM, BAT_HANDLE_RADIUS_MM, BAT_KNOB_RADIUS_MM
    pts = [(0.0, 0.7 * rk), (2.0, rk), (9.0, rk), (13.0, rh), (330.0, rh)]
    for i in range(1, 12):
        u = i / 12
        ease = 0.5 - 0.5 * math.cos(math.pi * u)
        pts.append((330.0 + u * (600.0 - 330.0), rh + ease * (rb - rh)))
    pts += [(600.0, rb), (845.0, rb), (856.0, 0.93 * rb), (L, 0.55 * rb)]
    return [(z * scale, r * scale) for z, r in pts]


@dataclass(frozen=True)
class SceneOptions:
    with_ball: bool = True
    ball_scale: float = BALL_SCALE
    ball_mass_scale: float = BALL_MASS_SCALE
    """Multiplies the ball's scaled radius. 1.0 is baseball-true; D31 uses 8,
    because VM-01 measured that a baseball-true ball subtends 0.25 deg and is
    simply not visible to this eye."""
    timestep_s: float = TIMESTEP_S
    contact_timeconst_s: float = CONTACT_TIMECONST_S
    eye_resolution: int = EYE_RESOLUTION
    pitcher: bool = True
    """A second fly on the rubber (D35). Visual only."""
    ballpark: bool = True
    """The park around the plate (D31c): foul lines, bases, mound, outfield
    fence, stands, foul poles, and the dark batter's eye in centre field.
    Visual only. False strips it back to the bare plate and dirt, which is
    how its effect on what the fly can see was measured."""
    aim_eyes: bool = True
    """D31b. False restores D28's fixed sideways eyes -- kept so the change
    can be measured against what it replaced."""


@dataclass
class Scene:
    xml: str
    scale: float
    fly_height_mm: float
    bat_length_mm: float
    ball_radius_mm: float
    ready_qpos: dict[str, float] = field(default_factory=dict)

    def model(self) -> mujoco.MjModel:
        return mujoco.MjModel.from_xml_string(self.xml)


def _fly_subtree(src_root: ET.Element) -> ET.Element:
    """Upright fly: welded root, static scenery, one physical foreleg."""
    fly = ET.Element("body", {"name": "FlyBody", "pos": "0 0 0", "quat": _qstr(STANCE_QUAT)})
    thorax_src = _find_body(src_root, "Thorax")
    thorax = ET.SubElement(fly, "body", {"name": "Thorax", "pos": thorax_src.get("pos")})
    for g in thorax_src.findall("geom"):
        geom = _copy_geom(g, collide=False)
        geom.set("group", str(GROUP_FLY))
        geom.set("rgba", _CHITIN)
        thorax.append(geom)
    for child in thorax_src.findall("body"):
        if child.get("name") == "RFCoxa":
            continue
        thorax.append(_static_copy(child, group=GROUP_FLY, skip=set(), pose=STATIC_POSE))
    leg = _build_leg(src_root, BuildOptions(), bat=None)
    for g in leg.iter("geom"):
        g.set("group", str(GROUP_ACTIVE))
        g.set("rgba", "0.72 0.52 0.30 1")
    thorax.append(leg)
    return fly


def _look_at(forward: np.ndarray, up: np.ndarray) -> str:
    """MJCF `xyaxes` for a camera whose optical axis is `forward` (cameras
    look along -z), with `up` as image up."""
    z = -forward / np.linalg.norm(forward)
    y = up - (up @ z) * z
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    return " ".join(f"{v:.6g}" for v in (*x, *y))


def _eye_cameras(model_probe: mujoco.MjModel, data_probe: mujoco.MjData,
                 aim_world: np.ndarray | None = None) -> dict[str, tuple[np.ndarray, str]]:
    """Camera placement for each eye, in the Head body's frame: the eye
    mesh's own centroid, aimed at `aim_world` (D31b) or, without one, out
    sideways and a little down as D28 first had it.

    D31b aims the LEFT eye at the point where the ball is when the fly must
    decide; the right eye stays as D28 built it. VM-01 v2b measured why:
    with the eye fixed sideways the ball drifts from 16 to 86 degrees
    off-axis, so a narrow (high-acuity) eye loses it entirely. Aimed this way
    the whole pre-decision corridor sits within about 7 degrees of the axis,
    and 30 degrees of field is enough."""
    head = mujoco.mj_name2id(model_probe, mujoco.mjtObj.mjOBJ_BODY, "Head")
    hpos, hmat = data_probe.xpos[head], data_probe.xmat[head].reshape(3, 3)
    up_world = np.array([0.0, 0.0, 1.0])
    t = math.radians(EYE_DOWN_TILT_DEG)
    c, st = math.cos(t), math.sin(t)
    out = {}
    for side, sign in (("L", 1.0), ("R", -1.0)):
        g = mujoco.mj_name2id(model_probe, mujoco.mjtObj.mjOBJ_GEOM, f"{side}Eye")
        eye_world = data_probe.geom_xpos[g]
        local = hmat.T @ (eye_world - hpos)
        if aim_world is None or side != "L":
            xaxis = np.array([0.0, 0.0, -1.0 * sign])
            yaxis = np.array([c, sign * st, 0.0])
            out[side] = (local, " ".join(f"{v:.6g}" for v in (*xaxis, *yaxis)))
            continue
        # The right eye gets the mirror image of the left eye's aim, so the
        # two stay symmetric about the fly's midline instead of both
        # staring at the pitcher.
        forward = hmat.T @ (np.array(aim_world, dtype=float) - eye_world)
        out[side] = (local, _look_at(forward, hmat.T @ up_world))
    return out


def pitch_geometry(strike: np.ndarray, scale: float, distance_scale: float | None = None,
                   flight_s: float | None = None,
                   release_reference: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """Release point, launch velocity and flight time for the nominal pitch:
    a ball thrown down the same line of approach as a real pitch, arriving at
    `strike` after `flight_s`.

    `release_reference` is where the release point is computed FROM, and it
    defaults to `strike` only for a single-zone pitch. With strike zones it
    must be passed, and must not depend on the zone -- the release point is
    the pitcher's hand, and a pitcher does not move when aiming higher.

    That was a real bug: deriving the release from the strike point meant
    aiming 0.45 mm higher dropped the hand 1.16 mm (the line pivots, and the
    release is 3.6 times farther out than the plate). A high pitch then
    appeared LOWER in the eye than a low one, which is the opposite of the
    thing the fly is supposed to read."""
    flight = PITCH_FLIGHT_S if flight_s is None else flight_s
    full = np.array([(PITCH_DISTANCE_MM - PITCHER_EXTENSION_MM) * scale, 0.0,
                     RELEASE_HEIGHT_MM * scale])
    # Without an explicit distance, the release point is wherever a fastball
    # at PITCH_SPEED_MM_S has to start to arrive after `flight` (D32).
    origin = strike if release_reference is None else np.asarray(release_reference, dtype=float)
    # Default: the pitcher's own release point (D35). A distance_scale is
    # still honoured, for measurements that need the ball farther out.
    dscale = 1.0 if distance_scale is None else distance_scale
    release = origin + dscale * (full - origin)
    g = np.array([0.0, 0.0, -units.GRAVITY])
    v0 = (strike - release - 0.5 * g * flight ** 2) / flight
    return release, v0, flight


def decision_point(strike: np.ndarray, scale: float, swing_s: float | None = None) -> np.ndarray:
    """Where the ball is at the last instant a swing can still start. The
    eyes are aimed here (D31b): it is the middle of what the fly has to see,
    and aiming at the strike point instead would put the useful part of the
    flight at the edge of a narrow field."""
    release, v0, flight = pitch_geometry(strike, scale)
    swing = DEMO_SWING_S if swing_s is None else swing_s
    t = max(flight - swing - DECISION_LATENCY_S, 0.0)
    g = np.array([0.0, 0.0, -units.GRAVITY])
    return release + v0 * t + 0.5 * g * t ** 2


DEFAULT_SCENE = SceneOptions()


@lru_cache(maxsize=8)
def build_scene(opts: SceneOptions = DEFAULT_SCENE) -> Scene:
    src_root = ET.parse(SOURCE_MJCF).getroot()
    src_asset = src_root.find("asset")
    assert src_asset is not None

    def mjcf(worldbody_children: list[ET.Element], extra_assets: list[ET.Element],
             cameras: dict | None = None) -> ET.Element:
        root = ET.Element("mujoco", {"model": "flyohtani_batter"})
        ET.SubElement(root, "compiler", {"angle": "radian", "autolimits": "true",
                                         "boundmass": repr(BOUNDMASS), "boundinertia": "1e-14",
                                         "meshdir": str(MESH_DIR)})
        ET.SubElement(root, "option", {"timestep": repr(opts.timestep_s), "gravity": "0 0 -9810",
                                       "integrator": "Euler", "solver": "Newton",
                                       "iterations": "100", "tolerance": "1e-10"})
        vis = ET.SubElement(root, "visual")
        ET.SubElement(vis, "global", {"offwidth": "1600", "offheight": "1000"})
        ET.SubElement(vis, "map", {"znear": "0.0005"})
        ET.SubElement(vis, "headlight", {"ambient": "0.42 0.42 0.42", "diffuse": "0.5 0.5 0.5",
                                         "specular": "0.05 0.05 0.05"})
        ET.SubElement(vis, "quality", {"shadowsize": "0"})
        default = ET.SubElement(root, "default")
        ET.SubElement(default, "geom", {
            "solref": f"{opts.contact_timeconst_s!r} {CONTACT_DAMPRATIO!r}",
            "solimp": " ".join(repr(v) for v in CONTACT_SOLIMP),
            "condim": "1", "friction": "0 0 0"})
        asset = ET.SubElement(root, "asset")
        for m in src_asset.findall("mesh"):
            ET.SubElement(asset, "mesh", {"name": m.get("name"), "file": m.get("file").split("/")[-1],
                                          "scale": m.get("scale", "1 1 1")})
        for a in extra_assets:
            asset.append(a)
        wb = ET.SubElement(root, "worldbody")
        for c in worldbody_children:
            wb.append(c)
        if cameras:
            head = next(b for b in wb.iter("body") if b.get("name") == "Head")
            for side, (pos, xy) in cameras.items():
                ET.SubElement(head, "camera", {"name": f"eye_{side}", "pos": " ".join(f"{v:.6g}" for v in pos),
                                               "xyaxes": xy, "fovy": repr(EYE_FOVY_DEG)})
        actuator = ET.SubElement(root, "actuator")
        lo, hi = units.POSITION_CONTROL_FORCERANGE
        for j in ACTIVE_JOINTS:
            ET.SubElement(actuator, "position", {"name": f"act_{j}", "joint": j,
                                                 "kp": repr(units.POSITION_CONTROL_KP),
                                                 "forcerange": f"{lo} {hi}", "ctrlrange": "-1e6 1e6"})
        return root

    # pass 1: the fly alone, to measure its posed height and find its feet.
    probe_root = mjcf([_fly_subtree(src_root)], [])
    probe = mujoco.MjModel.from_xml_string(ET.tostring(probe_root, encoding="unicode"))
    pdata = mujoco.MjData(probe)
    mujoco.mj_forward(probe, pdata)
    zs_top, zs_bottom = [], []
    for g in range(probe.ngeom):
        if probe.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        name = mujoco.mj_id2name(probe, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        mid = probe.geom_dataid[g]
        adr, num = probe.mesh_vertadr[mid], probe.mesh_vertnum[mid]
        verts = probe.mesh_vert[adr:adr + num]
        world = pdata.geom_xpos[g] + verts @ pdata.geom_xmat[g].reshape(3, 3).T
        zs_top.append(world[:, 2].max())
        if "HTarsus" in name:
            zs_bottom.append(world[:, 2].min())
    foot_z = min(zs_bottom)
    height = max(zs_top) - foot_z
    thorax_xy = pdata.xpos[mujoco.mj_name2id(probe, mujoco.mjtObj.mjOBJ_BODY, "Thorax")][:2].copy()
    scale = height / HUMAN_HEIGHT_MM
    cams = _eye_cameras(probe, pdata)

    # pass 2: the scene.
    bat_len = BAT_LENGTH_MM * scale
    ball_r = BALL_RADIUS_MM * scale * opts.ball_scale
    # Mass is specified relative to a scale-true baseball of this same radius,
    # so enlarging the ball does not silently make it 512x heavier.
    ball_density = BALL_DENSITY * opts.ball_mass_scale / max(opts.ball_scale ** 3, 1e-12)
    rb, rh = BAT_BARREL_RADIUS_MM * scale, BAT_HANDLE_RADIUS_MM * scale

    extra = []
    tex = ET.Element("texture", {"name": "sky", "type": "skybox", "builtin": "gradient",
                                 "rgb1": "0.78 0.86 0.95", "rgb2": "0.97 0.98 0.99", "width": "64", "height": "64"})
    grass = ET.Element("texture", {"name": "grass", "type": "2d", "builtin": "checker",
                                   "rgb1": "0.33 0.52 0.27", "rgb2": "0.30 0.49 0.25", "width": "64", "height": "64"})
    extra += [tex, grass,
              ET.Element("material", {"name": "grass", "texture": "grass", "texrepeat": "0.25 0.25", "texuniform": "true"}),
              ET.Element("material", {"name": "dirt", "rgba": "0.66 0.47 0.31 1"}),
              ET.Element("material", {"name": "chalk", "rgba": "0.96 0.96 0.94 1"}),
              ET.Element("material", {"name": "wood", "rgba": "0.84 0.66 0.42 1", "specular": "0.3", "shininess": "0.4"})]
    vs, fs = _lathe(bat_profile(scale))
    # "exact": MuJoCo's default (legacy) volume is only right for convex meshes,
    # and a bat is not convex -- legacy overstated its mass by ~8%.
    extra.append(ET.Element("mesh", {"name": "bat", "vertex": vs, "face": fs, "inertia": "exact"}))
    w, side = PLATE_WIDTH_MM * scale / 2, PLATE_SIDE_MM * scale
    plate = [(-w, 0), (w, 0), (w, side), (0, 2 * side), (-w, side)]
    pvs = []
    for zz in (0.0, 0.002):
        pvs += [f"{-b:.6g} {a:.6g} {zz}" for a, b in plate]
    extra.append(ET.Element("mesh", {"name": "plate", "vertex": " ".join(pvs)}))

    world = []
    # infinite (size 0): a finite plane leaves a gap before the horizon where
    # the skybox's dark lower half shows through, and a batted ball needs
    # room anyway (a scaled 400 ft fence is ~250 mm out).
    ground = ET.Element("geom", {"name": "ground", "type": "plane", "size": "0 0 0.1",
                                 "material": "grass", "group": str(GROUP_WORLD)})
    world.append(ground)
    dirt = ET.Element("geom", {"name": "dirt", "type": "cylinder", "size": f"{4200 * scale} {DIRT_TOP_MM / 2}",
                               "pos": f"0 0 {DIRT_TOP_MM / 2}", "material": "dirt", "contype": "0", "conaffinity": "0",
                               "group": str(GROUP_WORLD)})
    world.append(dirt)
    world.append(ET.Element("geom", {"name": "plate", "type": "mesh", "mesh": "plate", "material": "chalk",
                                     "pos": f"0 0 {DIRT_TOP_MM}", "contype": "0", "conaffinity": "0",
                                     "group": str(GROUP_WORLD)}))
    # right-handed batter's box: third-base side of the plate (+y).
    box_y0 = w + BOX_GAP_MM * scale
    box_y1 = box_y0 + BOX_WIDTH_MM * scale
    box_x = BOX_LENGTH_MM * scale / 2
    box_cx = -side  # the plate's middle
    cw = CHALK_WIDTH_MM * scale / 2
    box_cy = (box_y0 + box_y1) / 2
    lines = [((box_cx, box_y0), (box_x, cw)), ((box_cx, box_y1), (box_x, cw)),
             ((box_cx - box_x, box_cy), (cw, (box_y1 - box_y0) / 2 + cw)),
             ((box_cx + box_x, box_cy), (cw, (box_y1 - box_y0) / 2 + cw))]
    for i, ((cx, cy), (hx, hy)) in enumerate(lines):
        world.append(ET.Element("geom", {"name": f"box_line{i}", "type": "box",
                                         "size": f"{hx:.6g} {hy:.6g} 0.001",
                                         "pos": f"{cx:.6g} {cy:.6g} {DIRT_TOP_MM + 0.001}", "material": "chalk",
                                         "contype": "0", "conaffinity": "0", "group": str(GROUP_WORLD)}))
    # Imported here, not at the top: park.py reads this module's dimensions,
    # so a module-level import either way is circular. The park is only ever
    # needed while a scene is being built.
    from flyohtani.world.park import ballpark_geoms, pitcher_subtree

    if opts.ballpark:
        world += ballpark_geoms(scale)
    if opts.pitcher:
        world.append(pitcher_subtree(src_root, scale, foot_z))

    # directional ("sun"): MuJoCo's default light is a spotlight, whose cone
    # leaves the far field dark.
    world.append(ET.Element("light", {"pos": "3 -6 12", "dir": "-0.2 0.4 -1", "diffuse": "0.55 0.55 0.52",
                                      "directional": "true", "castshadow": "false"}))

    fly = _fly_subtree(src_root)
    # feet on the ground, standing in the middle of the box.
    # the source model's thorax sits ~1.3 mm off the root once upright; place
    # the root so the THORAX is centred in the box.
    fly.set("pos", f"{box_cx - thorax_xy[0]:.6g} {box_cy - thorax_xy[1]:.6g} {-foot_z + DIRT_TOP_MM + 0.002:.6g}")
    tarsus = next(b for b in fly.iter("body") if b.get("name") == "RFTarsus1")
    ox, oy, oz = _tip_offset(src_root)
    bat = ET.SubElement(tarsus, "body", {"name": "bat", "pos": f"{ox} {oy} {oz}"})
    ET.SubElement(bat, "geom", {"name": "bat_visual", "type": "mesh", "mesh": "bat", "material": "wood",
                                "density": repr(WOOD_DENSITY), "contype": "0", "conaffinity": "0",
                                "group": str(GROUP_ACTIVE)})
    # collision stand-ins along the same axis (a mesh collides as its convex
    # hull, which would fatten the handle). Massless: inertia comes from the
    # visual solid above.
    prof = bat_profile(scale)
    coll = [(13 * scale, 330 * scale, rh), (330 * scale, 420 * scale, rh + 0.2 * (rb - rh)),
            (420 * scale, 510 * scale, rh + 0.55 * (rb - rh)), (510 * scale, 600 * scale, rh + 0.9 * (rb - rh)),
            (600 * scale, prof[-2][0], rb)]
    for i, (z0, z1, r) in enumerate(coll):
        ET.SubElement(bat, "geom", {"name": f"bat_c{i}", "type": "capsule", "size": f"{r:.6g}",
                                    "fromto": f"0 0 {-(z0 + r):.6g} 0 0 {-(z1 - r):.6g}",
                                    "mass": "0", "rgba": "0 0 0 0", "group": "5"})
    ET.SubElement(bat, "site", {"name": "bat_sweet", "pos": f"0 0 {-(730 * scale):.6g}", "size": f"{rb:.6g}",
                                "rgba": "0 0 0 0"})
    ET.SubElement(bat, "site", {"name": "bat_tip", "pos": f"0 0 {-bat_len:.6g}", "size": "0.005",
                                "rgba": "0 0 0 0"})
    world.append(fly)

    if opts.with_ball:
        ball = ET.Element("body", {"name": "ball", "pos": f"{PITCH_DISTANCE_MM * scale:.6g} 0 1.0"})
        ET.SubElement(ball, "freejoint", {"name": "ball"})
        ET.SubElement(ball, "geom", {"name": "ball", "type": "sphere", "size": f"{ball_r:.6g}",
                                     "density": repr(ball_density), "rgba": "0.97 0.97 0.95 1",
                                     "group": str(GROUP_WORLD)})
        world.append(ball)

    root = mjcf(world, extra, cameras=cams)

    # pass 3: aim the eyes (D31b). Where to look depends on where the ball is
    # when the fly must decide, and that needs the bat's sweet spot, which
    # only exists once the scene is assembled -- hence a third pass over a
    # throwaway compile of what we just built.
    if opts.aim_eyes:
        probe2 = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
        pdata2 = mujoco.MjData(probe2)
        set_arm(probe2, pdata2, CONTACT_POSE)
        strike = pdata2.site_xpos[mujoco.mj_name2id(probe2, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")].copy()
        mujoco.mj_resetData(probe2, pdata2)
        set_arm(probe2, pdata2, READY_POSE)
        mujoco.mj_forward(probe2, pdata2)
        for side, (pos, xy) in _eye_cameras(probe2, pdata2, aim_world=decision_point(strike, scale)).items():
            cam = next(c for c in root.iter("camera") if c.get("name") == f"eye_{side}")
            cam.set("pos", " ".join(f"{v:.6g}" for v in pos))
            cam.set("xyaxes", xy)
        for cam in root.iter("camera"):
            if cam.get("name") == "eye_L":
                cam.set("fovy", repr(EYE_FOVY_DEG))
            elif cam.get("name") == "eye_R":
                cam.set("fovy", repr(EYE_FOVY_WIDE_DEG))

    ET.indent(root, space=" ")
    return Scene(xml=ET.tostring(root, encoding="unicode"), scale=scale, fly_height_mm=height,
                 bat_length_mm=bat_len, ball_radius_mm=ball_r)


READY_POSE = dict(zip(ACTIVE_JOINTS, map(math.radians, (-255.19, 87.79, 74.02, -19.58, -113.13)), strict=True))
"""Where the fly waits. FOUND by `world.poses.find_ready_pose`, scored on
what the swing out of it does at the moment of contact rather than on how it
looks standing still.

The pose it replaced was chosen for its appearance -- bat up and back over
the shoulder -- and the swing out of it met the ball moving DOWNWARD at -18
degrees, chasing a pitch that already falls at -23. Everything solid went
into the dirt: launch angles of -30 to -78 and carries under 2 mm.

This one meets the ball moving forward and slightly up (+7 to +11.5 degrees
across the three zones) at 539-557 mm/s, against 390 before, with the speed
pointed at the ball instead of across it: the velocity at contact went from
(251, 273, -121) to about (538, 1, 95). Measured consequence, same contact
poses and same pitch: carry 0.30 mm -> 66 mm in the middle zone.

ONE pose for all three zones, deliberately. The fly does not know where the
pitch is going until it sees it, so a stance per zone would put the answer in
the body before the question was asked. The search scores the WORST zone.

Peak joint speed is 298-299 rad/s -- LIT-01's ceiling is 300, and the search
stops exactly there, which is worth saying plainly: this swing is limited by
the animal, not by the search."""

CONTACT_POSE_ANGLES_DEG = (5.4, 99.1, 15.2, -77.7, -34.3)
CONTACT_POSE = dict(zip(ACTIVE_JOINTS, map(math.radians, CONTACT_POSE_ANGLES_DEG), strict=True))
"""Bat level-ish across the plate. CHOSEN: the same search, asking for the
sweet spot over the middle of the plate at 1.2 mm and the bat pointing across
it. Achieved: sweet spot within 0.002 mm of the plate's middle, at 1.197 mm.
A reference pose for tests and demos -- NOT the swing the fly must learn.

Coxa stays at +99.1 deg, 251 deg from READY, even though -260.9 is the same
configuration and only 109 deg away. The short way was tried: interpolating
along it swings the bat THROUGH THE GROUND, and the impact spiked the joints
past 400 rad/s. The long way keeps the bat at least 0.9 mm above the ground.

Both poses use joint angles well outside anything in the vendored walking
recording (whose largest range of motion is 1.76 rad). That is the staging
of D26, a derived engineering pose -- not a claim that a fly's foreleg bends
this way."""


STRIKE_ZONES: tuple[str, ...] = ("high", "middle", "low")
ZONE_OFFSET_MM = {"high": 0.45, "middle": 0.0, "low": -0.35}
"""Where each zone's contact point sits, relative to the middle one. The
spread is 0.80 mm, 2.7 ball diameters, so swinging at the wrong zone misses
-- which is the point: a pitch that can arrive high or low only makes the
task harder if the fly has to swing somewhere different."""

CONTACT_POSES = {
    "high": dict(zip(ACTIVE_JOINTS, map(math.radians, (5.4, 100.7, 15.7, -91.5, -34.2)), strict=True)),
    "middle": CONTACT_POSE,
    "low": dict(zip(ACTIVE_JOINTS, map(math.radians, (5.4, 94.6, 15.2, -64.9, -33.6)), strict=True)),
}
"""One contact pose per zone, found by `world.poses.find_contact_pose` and
cached here the way READY_POSE and CONTACT_POSE always were -- with the
difference that the search is now in the repo and a test reproduces these.

They are deliberately a FAMILY rather than three separate solutions: five
joints reaching for one point is redundant, so the search is pulled toward
the middle pose. What comes out differs mostly in one joint (the tibia, by
about 13 degrees), which is what "swing higher" should look like."""

DEMO_SWING_S = 0.040
DEMO_SWING_FOLLOW = 0.6
"""Demo swing: 40 ms with a 0.6 follow-through.

38 ms was the fastest the commanded swing could be inside LIT-01's 300 rad/s
ceiling -- 299 rad/s -- but that left nothing for the COLLISION, which adds
joint speed of its own: a recorded episode came out at 301.9. 40 ms brings
the command to 283-285 and the impact fits underneath. The bat gives up 5%
of its speed for it (512-526 mm/s against 539-557).

The point is where the peak lands. The old 27 ms / 0.1 swing peaked at
590 mm/s in mid-swing and was already SLOWING at the contact point, arriving
there at 224 mm/s. Carrying the swing further past contact moves the peak
onto the ball: 390 mm/s at contact, 287 rad/s peak joint speed, lowest point
0.985 mm, still clear of the ground. A 20-swing sweep of durations and
follow-throughs is what picked it; everything faster broke the ceiling.

That is a fly's Ohtani, not a human's: Ohtani's bat speed Froude-scales to
1535 mm/s, and this arm reaches a quarter of it. The batted ball does better
than that ratio suggests, because a 1879 mm/s fastball brings its own
momentum back off the bat."""


def swing_targets(t_s: float, duration_s: float = DEMO_SWING_S,
                  follow: float = DEMO_SWING_FOLLOW, zone: str = "middle") -> dict[str, float]:
    """Demo swing: a cosine-eased path READY -> CONTACT, carried `follow`
    past CONTACT. Used for rendering and for sizing contact speeds -- the
    learned policy is free to do something else (D15)."""
    u = min(max(t_s / duration_s, 0.0), 1.0)
    e = (0.5 - 0.5 * math.cos(math.pi * u)) * (1.0 + follow)
    contact = CONTACT_POSES[zone]
    return {j: READY_POSE[j] + e * (contact[j] - READY_POSE[j]) for j in ACTIVE_JOINTS}


def joint_qpos_addr(model: mujoco.MjModel) -> dict[str, int]:
    return {j: model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j)] for j in ACTIVE_JOINTS}


def set_arm(model: mujoco.MjModel, data: mujoco.MjData, angles: dict[str, float]) -> None:
    """Puts the swinging foreleg at `angles` and holds it there."""
    adr = joint_qpos_addr(model)
    for i, j in enumerate(ACTIVE_JOINTS):
        data.qpos[adr[j]] = angles.get(j, 0.0)
        data.ctrl[i] = angles.get(j, 0.0)
    mujoco.mj_forward(model, data)


EYE_SUPERSAMPLE = 4
"""Each pixel integrates light over its own solid angle, the way an
ommatidium does, instead of point-sampling the scene. Measured reason
(VM-01): a point-sampled ball smaller than a pixel blinks in and out as it
crosses the pixel grid, so detection came and went with the aliasing rather
than with the distance. Rendering 4x and box-filtering makes a sub-pixel ball
a steady dim spot. It is a coarse stand-in for a photoreceptor's Gaussian
acceptance function, not a model of one."""


def render_eyes(model: mujoco.MjModel, data: mujoco.MjData,
                renderer: mujoco.Renderer | None = None, *,
                resolution: int = EYE_RESOLUTION,
                supersample: int = EYE_SUPERSAMPLE) -> dict[str, np.ndarray]:
    """Both eye images, grayscale, with the fly's own head hidden (the
    cameras sit inside the eye meshes).

    `renderer` is optional. One sized `resolution * supersample` is
    downsampled like an owned one; one sized `resolution` is point-sampled,
    which is what VM-01 v1/v2 measured and is kept only for comparison."""
    opt = mujoco.MjvOption()
    opt.geomgroup[GROUP_HEAD] = 0
    gray = np.array([0.299, 0.587, 0.114])
    own = renderer is None
    if own:
        side_px = resolution * supersample
        renderer = mujoco.Renderer(model, height=side_px, width=side_px)
    try:
        out = {}
        for side in ("L", "R"):
            renderer.update_scene(data, camera=f"eye_{side}", scene_option=opt)
            img = renderer.render() @ gray
            n = img.shape[0] // resolution
            if n > 1:
                img = img.reshape(resolution, n, resolution, n).mean(axis=(1, 3))
            out[side] = img.astype(np.uint8)
        return out
    finally:
        if own:
            renderer.close()

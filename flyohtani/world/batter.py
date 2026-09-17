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

EYE_RESOLUTION = 32
"""Pixels per side, per eye. At a 120 deg field that is ~3.8 deg per pixel,
close to a fruit fly's ~5 deg interommatidial angle. "Fly-like enough" (D28),
not an ommatidia model."""
EYE_FOVY_DEG = 120.0
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


def _static_copy(src: ET.Element, *, group: int, skip: set[str], pose: dict[str, float]) -> ET.Element:
    """Copies a source body subtree with every joint replaced by its fixed
    angle from `pose` (0 if absent), baked into the body's quaternion in the
    order MuJoCo applies them."""
    q = np.array([float(v) for v in src.get("quat", "1 0 0 0").split()])
    for j in src.findall("joint"):
        axis = [float(v) for v in j.get("axis", "0 0 1").split()]
        q = _qmul(q, _quat_axis_angle(axis, pose.get(j.get("name"), 0.0)))
    out = ET.Element("body", {"name": src.get("name"), "pos": src.get("pos", "0 0 0"), "quat": _qstr(q)})
    this_group = GROUP_HEAD if src.get("name") == "Head" else group
    for g in src.findall("geom"):
        geom = _copy_geom(g, collide=False)
        geom.set("group", str(this_group))
        geom.set("rgba", _colour_for(geom.get("name", "")))
        out.append(geom)
    for child in src.findall("body"):
        if child.get("name") in skip:
            continue
        out.append(_static_copy(child, group=this_group, skip=skip, pose=pose))
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
    ball_scale: float = 1.0
    """Multiplies the ball's scaled radius. 1.0 is baseball-true. A bigger
    ball is the "large, slow ball first" curriculum lever (VM-01)."""
    timestep_s: float = TIMESTEP_S
    contact_timeconst_s: float = CONTACT_TIMECONST_S
    eye_resolution: int = EYE_RESOLUTION


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


def _eye_cameras(model_probe: mujoco.MjModel, data_probe: mujoco.MjData) -> dict[str, tuple[np.ndarray, str]]:
    """Camera placement for each eye, in the Head body's frame: the eye
    mesh's own centroid, looking out sideways and a little down."""
    head = mujoco.mj_name2id(model_probe, mujoco.mjtObj.mjOBJ_BODY, "Head")
    hpos, hmat = data_probe.xpos[head], data_probe.xmat[head].reshape(3, 3)
    t = math.radians(EYE_DOWN_TILT_DEG)
    c, s = math.cos(t), math.sin(t)
    out = {}
    for side, sign in (("L", 1.0), ("R", -1.0)):
        g = mujoco.mj_name2id(model_probe, mujoco.mjtObj.mjOBJ_GEOM, f"{side}Eye")
        local = hmat.T @ (data_probe.geom_xpos[g] - hpos)
        # look sideways (+/-y), tilted toward -x (down, once upright);
        # image up is +x (world up, once upright).
        xaxis = np.array([0.0, 0.0, -1.0 * sign])
        yaxis = np.array([c, sign * s, 0.0])
        out[side] = (local, " ".join(f"{v:.6g}" for v in (*xaxis, *yaxis)))
    return out


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
    rb, rh = BAT_BARREL_RADIUS_MM * scale, BAT_HANDLE_RADIUS_MM * scale

    extra = []
    tex = ET.Element("texture", {"name": "sky", "type": "skybox", "builtin": "gradient",
                                 "rgb1": "0.78 0.86 0.95", "rgb2": "0.97 0.98 0.99", "width": "64", "height": "64"})
    grass = ET.Element("texture", {"name": "grass", "type": "2d", "builtin": "checker",
                                   "rgb1": "0.33 0.52 0.27", "rgb2": "0.30 0.49 0.25", "width": "64", "height": "64"})
    extra += [tex, grass,
              ET.Element("material", {"name": "grass", "texture": "grass", "texrepeat": "40 40"}),
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
    ground = ET.Element("geom", {"name": "ground", "type": "plane", "size": "60 60 0.1",
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
    world.append(ET.Element("light", {"pos": "3 -6 12", "dir": "-0.2 0.4 -1", "diffuse": "0.55 0.55 0.52",
                                      "castshadow": "false"}))

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
                                     "density": repr(BALL_DENSITY), "rgba": "0.97 0.97 0.95 1",
                                     "group": str(GROUP_WORLD)})
        world.append(ball)

    root = mjcf(world, extra, cameras=cams)
    ET.indent(root, space=" ")
    return Scene(xml=ET.tostring(root, encoding="unicode"), scale=scale, fly_height_mm=height,
                 bat_length_mm=bat_len, ball_radius_mm=ball_r)


READY_POSE = dict(zip(ACTIVE_JOINTS, map(math.radians, (-135.0, -151.9, 128.8, -36.2, -4.4)), strict=True))
"""Bat up and back over the shoulder. CHOSEN: found by a random search that
asked for a grip above the thorax and a bat direction of about
(-0.35, 0.35, 1) -- back, away from the plate, up. Achieved (-0.31, 0.31, 0.90)."""

CONTACT_POSE = dict(zip(ACTIVE_JOINTS, map(math.radians, (5.4, 99.1, 15.2, -77.7, -34.3)), strict=True))
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


DEMO_SWING_S = 0.035
"""Demo swing duration. With the long-way path this peaks at ~215 rad/s and
never touches the ground."""


def swing_targets(t_s: float, duration_s: float = DEMO_SWING_S, follow: float = 0.1) -> dict[str, float]:
    """Demo swing: a cosine-eased path READY -> CONTACT, carried `follow`
    past CONTACT. Used for rendering and for sizing contact speeds -- the
    learned policy is free to do something else (D15)."""
    u = min(max(t_s / duration_s, 0.0), 1.0)
    e = (0.5 - 0.5 * math.cos(math.pi * u)) * (1.0 + follow)
    return {j: READY_POSE[j] + e * (CONTACT_POSE[j] - READY_POSE[j]) for j in ACTIVE_JOINTS}


def joint_qpos_addr(model: mujoco.MjModel) -> dict[str, int]:
    return {j: model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j)] for j in ACTIVE_JOINTS}


def set_arm(model: mujoco.MjModel, data: mujoco.MjData, angles: dict[str, float]) -> None:
    """Puts the swinging foreleg at `angles` and holds it there."""
    adr = joint_qpos_addr(model)
    for i, j in enumerate(ACTIVE_JOINTS):
        data.qpos[adr[j]] = angles.get(j, 0.0)
        data.ctrl[i] = angles.get(j, 0.0)
    mujoco.mj_forward(model, data)


def render_eyes(model: mujoco.MjModel, data: mujoco.MjData, renderer: mujoco.Renderer) -> dict[str, np.ndarray]:
    """Both eye images, grayscale, with the fly's own head hidden (the
    cameras sit inside the eye meshes)."""
    opt = mujoco.MjvOption()
    opt.geomgroup[GROUP_HEAD] = 0
    out = {}
    for side in ("L", "R"):
        renderer.update_scene(data, camera=f"eye_{side}", scene_option=opt)
        rgb = renderer.render()
        out[side] = (rgb @ np.array([0.299, 0.587, 0.114])).astype(np.uint8)
    return out

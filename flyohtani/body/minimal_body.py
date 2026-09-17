"""Phase 1 (docs/PLAN.md, D22): the minimal body that actually uses the fly's
own foreleg joints.

This builds an MJCF from the vendored NeuroMechFly source
(flyohtani/assets/mjcf_neuromechfly/), keeping the real joint axes, segment
positions, masses and meshes, and throwing away everything the batting task
does not need. It does NOT invent a body -- every number that describes the
fly comes from that file.

WHAT THIS MODEL IS, stated plainly, because each of these is a choice that
makes the model easier than reality and must not be quietly forgotten:

  1. THE THORAX IS WELDED TO THE WORLD. There is no free joint, no balance,
     no ground reaction. "Supported thorax" per D17. A real fly hitting a
     ball would be pushed back by it; this one cannot be.

  2. THE HEAD IS STATIC. The source model has three real neck joints
     (joint_Head_yaw / _Head / _Head_roll). They are dropped here, so the
     eye camera cannot stabilise independently of the thorax. Phase 3
     decides whether to actuate the neck.

  3. THE ACTIVE CHAIN STOPS AT TARSUS1, and the bat is welded there.
     Tarsus2-5 exist in the source model as passive, spring-loaded segments
     (flygym does not actuate them either) and are pruned here.

     This makes G1 an OPTIMISTIC measurement, deliberately: a rigid wrist
     transmits everything the actuators produce. If the foreleg cannot
     reach a useful bat-tip speed even with a rigid wrist, adding the real
     compliance back cannot rescue it, so a G1 failure is conclusive. A G1
     pass is NOT conclusive -- Phase 2 must re-measure with the compliant
     tarsus before any speed number is used for task design.

  4. ONE FORELEG, not two. A two-legged grip is a closed kinematic chain
     and an unnecessary first bottleneck (B1's own recommendation). The
     other legs are kept as static visual geometry only.

Units are the model's own: mm, g, uN (flyohtani/units.py).
"""
from __future__ import annotations

import itertools
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from flyohtani import units

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
SOURCE_MJCF = ASSET_DIR / "mjcf_neuromechfly" / "neuromechfly_seqik_kinorder_ypr.xml"
MESH_DIR = ASSET_DIR / "mesh_neuromechfly"

SWING_LEG = "RF"
"""Right foreleg. Left is the mirror; nothing in the task depends on which."""

LOCKED_DOFS: tuple[str, ...] = ("Coxa_roll", "Femur_roll")
"""The two DOFs that rotate a limb segment about its OWN long axis.

Measured in the unmodified published model (not in our pruned copy -- the
numbers are the same either way, which is how we know this is not our doing):

    joint_RFCoxa_yaw    2.808e-05 g*mm^2
    joint_RFCoxa        2.808e-05
    joint_RFCoxa_roll   2.914e-08   <-- ~1000x lighter
    joint_RFFemur       1.683e-05
    joint_RFFemur_roll  1.784e-08   <-- ~1000x lighter
    joint_RFTibia       4.770e-06
    joint_RFTarsus1     1.026e-06

A limb rotating about its own axis has almost no moment of inertia, so the
model's own +/-65 uN*mm actuator implies ~4e9 rad/s^2 on these two DOFs.
That needs dt < 4e-5 s to integrate at all, while flygym's own default is
dt = 1e-4 -- its published settings cannot drive its own roll joints under a
saturating command. flygym never hits this because it replays smooth,
non-saturating walking trajectories.

So Phase 1 LOCKS them (built rigid, not actuated). A planar swing does not
need limb-axis roll, and leaving them free would report a whipping artifact
as bat speed. The body still has 5 real, fly-derived DOFs; it does not have
7. Phase 2 revisits this if the task ever needs roll (adding `armature`
would be the standard fix, but that is inventing a number and is not done
here).
"""

def active_joints(lock_roll_dofs: bool = True) -> tuple[str, ...]:
    """Joint names the build will actuate. `lock_roll_dofs=False` exists so a
    test can measure the degeneracy that justifies locking them, rather than
    taking this module's word for it."""
    skip = set(LOCKED_DOFS) if lock_roll_dofs else set()
    return tuple(f"joint_{SWING_LEG}{dof}" for dof in units.ACTIVE_FORELEG_JOINTS if dof not in skip)


ACTIVE_JOINTS: tuple[str, ...] = active_joints()

_ACTIVE_BODIES = tuple(f"{SWING_LEG}{seg}" for seg in ("Coxa", "Femur", "Tibia", "Tarsus1"))
_TIP_BODY = f"{SWING_LEG}Tarsus1"

# Bodies kept purely so the fly looks like a fly in the viewer. They carry no
# joints, so MuJoCo fuses them into the (world-welded) thorax and they cost
# nothing dynamically.
_VISUAL_BODIES = (
    "Thorax", "Head", "A1A2", "A3", "A4", "A5", "A6", "LEye", "REye",
    "Rostrum", "Haustellum", "LWing", "RWing", "LHaltere", "RHaltere",
    "LPedicel", "RPedicel", "LFuniculus", "RFuniculus", "LArista", "RArista",
    "LFCoxa", "LFFemur", "LFTibia", "LFTarsus1",
    "LMCoxa", "LMFemur", "LMTibia", "LMTarsus1",
    "RMCoxa", "RMFemur", "RMTibia", "RMTarsus1",
    "LHCoxa", "LHFemur", "LHTibia", "LHTarsus1",
    "RHCoxa", "RHFemur", "RHTibia", "RHTarsus1",
)


@dataclass(frozen=True)
class BatSpec:
    """The tool welded to the tarsus. None of these three numbers is a
    measured fly fact -- they are the engineering parameters G1 sweeps.

    `radius_mm` has a hard constraint waiting for it in Phase 2: the bat must
    be THICKER than the ball's diameter along the penetration direction, or
    the contact normal flips sign mid-collision. That is the geometry bug
    docs/records/PRIOR-FINDINGS.md section 3 already diagnosed once.
    """

    mass_g: float
    length_mm: float
    radius_mm: float = 0.02

    def __post_init__(self) -> None:
        for name in ("mass_g", "length_mm", "radius_mm"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0, got {getattr(self, name)}")


@dataclass(frozen=True)
class BuildOptions:
    """Solver settings. Defaults are the SOURCE MODEL's own, not this
    project's preferences -- changing them is a decision that belongs in a
    validation run, not a default."""

    timestep: float = 1e-4
    integrator: str = "Euler"
    include_visual_body: bool = True
    boundmass: float = 1e-6
    """MuJoCo raises any body lighter than this UP to it. The source model
    ships 1e-6, which silently more than doubles Tarsus1 (really 4.65e-7)
    and would clamp a light bat too -- and 1e-6 g sits in the middle of the
    bat masses worth sweeping. Kept at the source value by default so the
    model matches the published fly; G1 measures whether it changes the
    answer rather than assuming it does not."""
    actuator_kp: float = units.POSITION_CONTROL_KP
    actuator_forcerange: tuple[float, float] = units.POSITION_CONTROL_FORCERANGE
    joint_damping: float = units.JOINT_DAMPING
    joint_stiffness: float = units.JOINT_STIFFNESS
    lock_roll_dofs: bool = True
    """See LOCKED_DOFS. False builds all 7 real DOFs and is only useful for
    measuring why they are locked -- a saturating command will diverge."""


def _source_tree() -> ET.ElementTree:
    if not SOURCE_MJCF.exists():  # pragma: no cover - packaging failure
        raise FileNotFoundError(f"vendored NeuroMechFly MJCF missing: {SOURCE_MJCF}")
    return ET.parse(SOURCE_MJCF)


def _find_body(root: ET.Element, name: str) -> ET.Element:
    for body in root.iter("body"):
        if body.get("name") == name:
            return body
    raise KeyError(f"body {name!r} not found in the source MJCF")


def _copy_geom(geom: ET.Element, *, collide: bool) -> ET.Element:
    """Copies a source geom. The source disables collision on EVERY geom
    (contype=0 conaffinity=0) -- flygym re-enables it selectively at load
    time. We do the same, explicitly, per geom."""
    out = ET.Element("geom", dict(geom.attrib))
    out.attrib.pop("class", None)
    out.set("contype", "1" if collide else "0")
    out.set("conaffinity", "1" if collide else "0")
    return out


def _tip_offset(source_root: ET.Element) -> tuple[float, float, float]:
    """Where Tarsus1 ends, in its own frame: the position its next segment
    (Tarsus2) sits at in the source model. Read, not assumed."""
    tarsus1 = _find_body(source_root, _TIP_BODY)
    tarsus2 = tarsus1.find("body")
    if tarsus2 is None:  # pragma: no cover - source model is fixed
        raise KeyError(f"{_TIP_BODY} has no child segment in the source MJCF")
    return tuple(float(v) for v in tarsus2.get("pos").split())  # type: ignore[return-value]


def _build_leg(source_root: ET.Element, opts: BuildOptions, bat: BatSpec | None) -> ET.Element:
    """Rebuilds the foreleg chain, pruning everything past Tarsus1."""
    out_by_name: dict[str, ET.Element] = {}
    root_out: ET.Element | None = None

    for name in _ACTIVE_BODIES:
        src = _find_body(source_root, name)
        out = ET.Element("body", {"name": name, "pos": src.get("pos", "0 0 0"),
                                  "quat": src.get("quat", "1 0 0 0")})
        wanted_joints = active_joints(opts.lock_roll_dofs)
        for joint in src.findall("joint"):
            jname = joint.get("name")
            if jname not in wanted_joints:
                continue
            ET.SubElement(out, "joint", {
                "name": jname,
                "type": "hinge",
                "pos": joint.get("pos", "0 0 0"),
                "axis": joint.get("axis", "0 1 0"),
                # flygym's loader overrides the XML's own per-joint damping
                # (0.01-0.1) with these for every ACTUATED joint. We match the
                # loader, not the raw file, because the loader is what the
                # published model actually runs with.
                "damping": str(opts.joint_damping),
                "stiffness": str(opts.joint_stiffness),
            })
        for geom in src.findall("geom"):
            out.append(_copy_geom(geom, collide=False))
        out_by_name[name] = out
        if root_out is None:
            root_out = out

    for parent, child in itertools.pairwise(_ACTIVE_BODIES):
        out_by_name[parent].append(out_by_name[child])

    tip = out_by_name[_TIP_BODY]
    ox, oy, oz = _tip_offset(source_root)
    ET.SubElement(tip, "site", {"name": "grip", "pos": f"{ox} {oy} {oz}", "size": "0.005"})

    if bat is not None:
        # Welded (no joint) at the end of Tarsus1, extending along -z, which
        # is the leg's own distal direction in this model. The pitch joints
        # all rotate about +y, so a bat along -z sweeps a plane perpendicular
        # to them and its tip speed is the quantity G1 measures.
        bat_body = ET.SubElement(tip, "body", {"name": "bat", "pos": f"{ox} {oy} {oz}"})
        ET.SubElement(bat_body, "geom", {
            "name": "bat",
            "type": "capsule",
            "fromto": f"0 0 0 0 0 {-bat.length_mm}",
            "size": str(bat.radius_mm),
            "mass": str(bat.mass_g),
            "contype": "1",
            "conaffinity": "1",
            "rgba": "0.75 0.55 0.3 1",
        })
        ET.SubElement(bat_body, "site", {"name": "bat_tip", "pos": f"0 0 {-bat.length_mm}", "size": "0.005"})

    assert root_out is not None
    return root_out


def build_minimal_body_xml(bat: BatSpec | None = None, opts: BuildOptions | None = None) -> str:
    """Returns the MJCF text for the Phase 1 body. Load with
    `mujoco.MjModel.from_xml_string(xml)` -- meshdir is absolute, so no
    working-directory dependence."""
    opts = opts or BuildOptions()
    tree = _source_tree()
    src_root = tree.getroot()

    root = ET.Element("mujoco", {"model": "flyohtani_minimal_body"})
    # Mirrors the source compiler settings. boundmass/boundinertia matter:
    # MuJoCo CLAMPS any body lighter than boundmass up to it, and the tarsal
    # segments are lighter than 1e-6. That clamping is in the published model
    # too, so we keep it rather than silently running a different fly.
    ET.SubElement(root, "compiler", {
        "angle": "radian", "eulerseq": "XYZ", "autolimits": "true",
        "boundmass": repr(opts.boundmass), "boundinertia": "1e-12",
        "meshdir": str(MESH_DIR),
    })
    ET.SubElement(root, "option", {
        "timestep": str(opts.timestep),
        "gravity": f"0 0 -{units.GRAVITY}",
        "integrator": opts.integrator,
        "solver": "Newton", "iterations": "1000", "tolerance": "1e-12",
    })
    ET.SubElement(root, "size", {"njmax": "4096", "nconmax": "4096"})

    # Thorax and Head are always built (the eye camera hangs off Head), so
    # their meshes are always needed regardless of the visual-body option.
    wanted = set(_ACTIVE_BODIES) | {"Thorax", "Head"}
    if opts.include_visual_body:
        wanted |= set(_VISUAL_BODIES)
    asset = ET.SubElement(root, "asset")
    src_asset = src_root.find("asset")
    assert src_asset is not None
    for mesh in src_asset.findall("mesh"):
        name = mesh.get("name", "")
        if name.removeprefix("mesh_") not in wanted:
            continue
        ET.SubElement(asset, "mesh", {
            "name": name,
            "file": mesh.get("file", "").split("/")[-1],
            "scale": mesh.get("scale", "1 1 1"),
        })

    worldbody = ET.SubElement(root, "worldbody")
    ET.SubElement(worldbody, "light", {"pos": "0 0 10", "dir": "0 0 -1", "diffuse": "0.8 0.8 0.8"})

    src_thorax = _find_body(src_root, "Thorax")
    # No joint on this body == welded to the world. That IS the "supported
    # thorax"; there is nothing else holding it up.
    fly = ET.SubElement(worldbody, "body", {"name": "FlyBody", "pos": "0 0 0"})
    thorax = ET.SubElement(fly, "body", {"name": "Thorax", "pos": src_thorax.get("pos", "0 0 0")})
    for geom in src_thorax.findall("geom"):
        thorax.append(_copy_geom(geom, collide=False))

    if opts.include_visual_body:
        for name in _VISUAL_BODIES:
            if name in ("Thorax",) or name in _ACTIVE_BODIES:
                continue
            try:
                src = _find_body(src_root, name)
            except KeyError:
                continue
            # Flattened onto the thorax at their world-relative rest pose:
            # jointless children would be fused anyway, and flattening keeps
            # the builder from having to rebuild the whole hierarchy.
            static = ET.SubElement(thorax, "body", {
                "name": f"visual_{name}",
                "pos": _world_offset(src_root, name),
                "quat": src.get("quat", "1 0 0 0"),
            })
            for geom in src.findall("geom"):
                g = _copy_geom(geom, collide=False)
                g.set("name", f"visual_{g.get('name')}")
                g.set("group", "3")
                static.append(g)

    head = _find_body(src_root, "Head")
    head_out = ET.SubElement(thorax, "body", {"name": "Head", "pos": head.get("pos", "0 0 0")})
    for geom in head.findall("geom"):
        head_out.append(_copy_geom(geom, collide=False))
    # The eye camera lives on the Head body so it moves with the head, which
    # is what flyohtani/sense/eye_camera.py expects to find.
    ET.SubElement(head_out, "camera", {"name": "eye_cam", "pos": "0.1 0 0",
                                       "xyaxes": "0 -1 0 0 0 1", "fovy": "60"})

    thorax.append(_build_leg(src_root, opts, bat))

    actuator = ET.SubElement(root, "actuator")
    lo, hi = opts.actuator_forcerange
    for jname in active_joints(opts.lock_roll_dofs):
        ET.SubElement(actuator, "position", {
            "name": f"act_{jname}", "joint": jname,
            "kp": str(opts.actuator_kp),
            "forcerange": f"{lo} {hi}",
            "ctrlrange": "-1e6 1e6",
        })

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def _world_offset(src_root: ET.Element, name: str) -> str:
    """Accumulated `pos` from Thorax down to `name` in the source hierarchy."""
    path: list[ET.Element] = []

    def walk(node: ET.Element, trail: list[ET.Element]) -> bool:
        for body in node.findall("body"):
            here = trail + [body]
            if body.get("name") == name:
                path.extend(here)
                return True
            if walk(body, here):
                return True
        return False

    walk(_find_body(src_root, "Thorax"), [])
    total = [0.0, 0.0, 0.0]
    for body in path:
        pos = [float(v) for v in body.get("pos", "0 0 0").split()]
        total = [a + b for a, b in zip(total, pos)]
    return " ".join(str(v) for v in total)

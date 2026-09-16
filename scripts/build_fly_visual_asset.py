"""I-08a-fix (docs/records/FLY-VISUAL-REVIEW.md): bake the static parts of
the NeuroMechFly visual rig into envs/assets/fly_visual_assets.xml /
fly_visual_body.xml, by editing the ORIGINAL bundled MJCF's raw XML tree
directly (preserving its nested body hierarchy exactly) -- NOT by
flattening to extracted world-frame coordinates. Flattening double-counted
each mesh's own placement (confirmed via render in I-08a: extracted-then-
reinjected geom_xpos produced a floating head) -- letting MuJoCo's own
fusestatic composition handle the transform chain, as the original file
does, avoids that bug entirely. See
docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json for package/version/
license/hash provenance of the source meshes.

To re-run: `pip download flygym==1.2.1 --no-deps -d <dir>`, unzip the wheel,
then `python scripts/build_fly_visual_asset.py <dir>/flygym/data/mjcf/neuromechfly_seqik_kinorder_ypr.xml`.
The bundled MJCF/mesh files are Apache-2.0 (NeLy-EPFL/flygym); only the
specific mesh STLs actually used are vendored into
envs/assets/mesh_neuromechfly/ (not the whole package).

I-08a-fix changes from I-08a (docs/records/FLY-VISUAL-REVIEW.md's findings):
1. WORLD-FRAME BUG FIXED: I-08a computed the ground offset in fly_visual's
   OWN local frame (so feet sit at local z=0) but then nested that body
   inside batter_body, which itself sits at world z=1.0 (BATTER_WORLD_POS
   below) -- so feet actually ended up ~1.0m off the ground, not 0. This
   version subtracts BATTER_WORLD_POS[2] so feet land at true world z=0.
2. SOLE/FINGERTIP, NOT GEOM ORIGIN: ground/reach calibration now reads
   real transformed mesh vertices (envs/fly_visual_mesh.py) instead of a
   geom's origin point -- a geom's local (0,0,0) is not the same as its
   mesh's lowest/outermost point, which was silently absorbing ~8cm of
   error in I-08a.
3. NEW POSTURE: only LH/RH (2 legs, not 4) are grounded/support the pose.
   LM/RM are folded in against the body sides (femur/tibia bent, see
   FOLD_FEMUR_PITCH_RAD/FOLD_TIBIA_PITCH_RAD below) -- static, decorative,
   not touching the ground and not used as extra arms. LF/RF remain the
   only dynamic (grip-tracking) legs.
4. UNIFORM SCALE: front legs (LF/RF Femur/Tibia/Tarsus1, exported for
   envs/fly_visual.py's dynamic IK) now use the SAME K as the rest of the
   body -- I-08a's separate 3x arm enlargement is removed. If K=400's
   natural reach cannot cover the real shoulder-to-grip distance, that is
   reported (docs/records/VALIDATION_LOG.md), not silently patched by
   stretching.
5. Front legs now keep Tarsus1 (the real fingertip mesh), not just
   Femur/Tibia -- see envs/fly_visual.py's 3-segment IK.
"""
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np

from envs.fly_visual_mesh import geom_world_vertices


def main(argv: list[str] | None = None) -> None:
    """Reads the source flygym MJCF at argv[0] (or sys.argv[1] when argv is
    None) and writes envs/assets/fly_visual_assets.xml and
    fly_visual_body.xml. Importing this module performs no argv parsing,
    file writes, or MuJoCo compilation by itself -- only calling main()
    does (R-02 follow-up, docs/implementation/REFACTOR-PLAN.md: "import 시
    파일 쓰기/argv 종료가 없는 main 함수"). Behavior when actually invoked is
    unchanged from before this wrapping -- the body below is the same
    top-to-bottom sequence, just parameterized on `argv`/`SRC` instead of
    reading sys.argv directly, and indented one level into this function.
    """
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(
            "usage: build_fly_visual_asset.py <path to neuromechfly_seqik_kinorder_ypr.xml "
            "from the extracted flygym==1.2.1 wheel>"
        )
    SRC = argv[0]
    OUT_DIR = Path(__file__).resolve().parent.parent / "envs" / "assets"
    K = 400.0
    MESH_DIR = "mesh_neuromechfly"

    # envs/assets/baseball_park_b1.xml's <body name="batter_body" pos="...">.
    # MUST be kept in sync by hand -- this script has no way to read the other
    # XML file's value automatically (it generates fragments consumed BY that
    # file, not the other way around).
    BATTER_WORLD_POS = np.array([0.1, 0.9, 1.0])

    GROUND_LEGS = ["LH", "RH"]  # stand on the ground (2 legs, per the user's posture spec)
    FOLD_LEGS = ["LM", "RM"]  # folded in against the body, not grounded, not an arm
    FRONT_LEGS = ["LF", "RF"]  # dynamic grip legs, Coxa kept static here; Femur/Tibia/Tarsus1 exported

    GROUND_KEEP_DEPTH = ["Coxa", "Femur", "Tibia", "Tarsus1"]  # drop Tarsus2-5
    FOLD_KEEP_DEPTH = ["Coxa", "Femur", "Tibia", "Tarsus1"]  # same depth, different pose

    # Middle-leg fold: found by grid search over the SOURCE rig's own Femur/
    # Tibia pitch joints (0.2098 rad-scale residual distance from LMTarsus1 to
    # LMCoxa at these angles, vs. ~1.6 fully extended -- i.e. ~87% folded in),
    # see docs/records/VALIDATION_LOG.md for the search. Applied as a STATIC
    # quat (same technique as the coxa root-rotation compensation), not a live
    # joint -- this whole rig has no joints at all except reference use in this
    # script.
    FOLD_FEMUR_PITCH_RAD = math.radians(-120)
    FOLD_TIBIA_PITCH_RAD = math.radians(-150)

    KEEP_TOP_LEVEL_NON_LEG = {
        "A1A2": None,  # keep whole subtree (A1A2->A3->A4->A5->A6)
        "LHaltere": None,
        "LWing": None,
        "RHaltere": None,
        "RWing": None,
        "Head": None,  # keep whole subtree (eyes, rostrum, antennae) -- own joints stripped below
    }

    # I-08a-style (docs/design/FLY-BATTING-STANCE-AND-COLOR.md section 2):
    # per-part appearance restored from flygym==1.2.1's own
    # flygym/config.yaml (the wheel's actual runtime appearance config, not a
    # guess) -- values copied verbatim (rgb/markrgb/size/random), keyed by
    # a group name -> [part geom names], texture spec (None = flat rgba only,
    # matching config.yaml's `texture: null` entries), and material rgba
    # (config.yaml uses this for alpha and, for textured parts, leaves rgb at
    # 1,1,1 so the texture's own color shows through -- copied as-is).
    APPEARANCE_GROUPS: dict[str, dict] = {
        "wing": {"parts": ["LWing", "RWing"], "texture": None, "rgba": [0.8, 0.8, 0.9, 0.3]},
        "eye": {"parts": ["LEye", "REye"], "texture": None, "rgba": [0.67, 0.21, 0.12, 1]},
        "arista": {"parts": ["LArista", "RArista"], "texture": None, "rgba": [0.26, 0.2, 0.16, 1.0]},
        "haltere": {"parts": ["LHaltere", "RHaltere"], "texture": None, "rgba": [0.59, 0.43, 0.24, 0.6]},
        "head": {
            "parts": ["Head"],
            "texture": {"builtin": "flat", "rgb1": [0.59, 0.39, 0.12], "rgb2": [0.59, 0.39, 0.12],
                        "markrgb": [0.7, 0.49, 0.2], "size": 50, "random": 0.3},
            "rgba": [1, 1, 1, 1],
        },
        "thorax": {
            "parts": ["Thorax"],
            "texture": {"builtin": "flat", "rgb1": [0.59, 0.39, 0.12], "rgb2": [0.59, 0.39, 0.12],
                        "markrgb": [0.7, 0.49, 0.2], "size": 50, "random": 0.3},
            "rgba": [1, 1, 1, 1],
        },
        "antenna": {
            "parts": ["LPedicel", "RPedicel", "LFuniculus", "RFuniculus"],
            "texture": {"builtin": "flat", "rgb1": [0.59, 0.39, 0.12], "rgb2": [0.59, 0.39, 0.12],
                        "markrgb": [0, 0, 0], "size": 50, "random": 0.1},
            "rgba": [1, 1, 1, 0.8],
        },
        "proboscis": {
            "parts": ["Haustellum", "Rostrum"],
            "texture": {"builtin": "flat", "rgb1": [0.59, 0.39, 0.12], "rgb2": [0.59, 0.39, 0.12],
                        "markrgb": [0, 0, 0], "size": 50, "random": 0.1},
            "rgba": [1, 1, 1, 0.8],
        },
        "coxa": {
            "parts": ["LFCoxa", "RFCoxa", "LMCoxa", "RMCoxa", "LHCoxa", "RHCoxa"],
            "texture": {"builtin": "flat", "rgb1": [0.59, 0.39, 0.12], "rgb2": [0.59, 0.39, 0.12],
                        "markrgb": [0, 0, 0], "size": 500, "random": 0.05},
            "rgba": [1, 1, 1, 0.8],
        },
        "femur": {
            "parts": ["LFFemur", "RFFemur", "LMFemur", "RMFemur", "LHFemur", "RHFemur"],
            "texture": {"builtin": "flat", "rgb1": [0.63, 0.43, 0.16], "rgb2": [0.63, 0.43, 0.16],
                        "markrgb": [0, 0, 0], "size": 500, "random": 0.05},
            "rgba": [1, 1, 1, 0.7],
        },
        "tibia": {
            "parts": ["LFTibia", "RFTibia", "LMTibia", "RMTibia", "LHTibia", "RHTibia"],
            "texture": {"builtin": "flat", "rgb1": [0.67, 0.47, 0.2], "rgb2": [0.67, 0.47, 0.2],
                        "markrgb": [0, 0, 0], "size": 500, "random": 0.05},
            "rgba": [1, 1, 1, 0.6],
        },
        "tarsus": {
            "parts": [f"{s}Tarsus{n}" for s in ("LF", "RF", "LM", "RM", "LH", "RH") for n in range(1, 6)],
            "texture": {"builtin": "flat", "rgb1": [0.71, 0.51, 0.24], "rgb2": [0.71, 0.51, 0.24],
                        "markrgb": [0, 0, 0], "size": 500, "random": 0.05},
            "rgba": [1, 1, 1, 0.5],
        },
        "a12345": {
            "parts": ["A1A2", "A3", "A4", "A5"],
            "texture": {"builtin": "gradient", "rgb1": [0.59, 0.39, 0.12], "rgb2": [0.82, 0.67, 0.47],
                        "markrgb": [0.7, 0.49, 0.2], "size": 200, "random": 0.3},
            "rgba": [1, 1, 1, 1],
        },
        "a6": {
            "parts": ["A6"],
            "texture": {"builtin": "gradient", "rgb1": [0.39, 0.2, 0], "rgb2": [0.82, 0.67, 0.47],
                        "markrgb": [0.7, 0.49, 0.2], "size": 200, "random": 0.3},
            "rgba": [1, 1, 1, 1],
        },
    }
    PART_TO_GROUP = {part: group for group, spec in APPEARANCE_GROUPS.items() for part in spec["parts"]}

    ROOT_PITCH_RAD = -math.pi / 2
    COMP_RAD = -ROOT_PITCH_RAD  # cancels ONLY the pitch component for leg compensation (see below)

    # I-08a-style (docs/design/FLY-BATTING-STANCE-AND-COLOR.md): the pitch alone
    # (above) stands the insect up but leaves its "ventral/chest" side (source
    # local -Z) facing world +X -- i.e. facing the pitcher chest-on. A real
    # batter stands SIDEWAYS: chest ~90deg off the home->pitcher line, shoulder
    # axis ~parallel to it. Verified by direct vector transform (VALIDATION_LOG.md):
    # composing this yaw AFTER the pitch (R_total = R_yaw @ R_pitch) sends
    # chest (-Z) -> world -Y and shoulder axis (+Y) -> world +X (parallel to
    # the home->pitcher direction, +X) simultaneously -- picked so a
    # right-handed batter's chest faces in toward the plate (home plate is at
    # lower Y than BATTER_WORLD_POS's +Y/third-base-side box).
    ROOT_YAW_RAD = -math.pi / 2

    # Leg compensation only needs to cancel PITCH, not this new yaw: the total
    # rotation a leg experiences is FlyBody_total * Coxa_local =
    # (Yaw*Pitch)*Pitch^-1 = Yaw. A pure yaw is a rotation about the SAME axis
    # gravity acts along (world Z), so it cannot change how well a leg reaches
    # "down" -- it only changes which horizontal direction the leg (and the
    # whole body) faces. Confirmed by re-running the I-08a-fix ground/reach
    # checks after adding yaw (docs/records/VALIDATION_LOG.md): unchanged.


    def axis_angle_y_quat(theta: float) -> tuple[float, float, float, float]:
        return (math.cos(theta / 2), 0.0, math.sin(theta / 2), 0.0)


    def axis_angle_z_quat(theta: float) -> tuple[float, float, float, float]:
        return (math.cos(theta / 2), 0.0, 0.0, math.sin(theta / 2))


    def rot_y(theta: float) -> np.ndarray:
        c, s = math.cos(theta), math.sin(theta)
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


    def rot_z(theta: float) -> np.ndarray:
        c, s = math.cos(theta), math.sin(theta)
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


    def quat_from_mat(m: np.ndarray) -> tuple[float, float, float, float]:
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, m.flatten())
        return tuple(q.tolist())


    def align_vectors_quat(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float, float]:
        """Quaternion rotating unit vector a to unit vector b (general axis)."""
        a = a / np.linalg.norm(a)
        b = b / np.linalg.norm(b)
        c = float(np.dot(a, b))
        if c > 1.0 - 1e-9:
            return (1.0, 0.0, 0.0, 0.0)
        if c < -1.0 + 1e-9:
            # 180-degree case: pick any axis perpendicular to a
            perp = np.cross(a, np.array([1.0, 0.0, 0.0]))
            if np.linalg.norm(perp) < 1e-6:
                perp = np.cross(a, np.array([0.0, 1.0, 0.0]))
            perp /= np.linalg.norm(perp)
            return (0.0, perp[0], perp[1], perp[2])
        axis = np.cross(a, b)
        axis /= np.linalg.norm(axis)
        angle = math.acos(np.clip(c, -1.0, 1.0))
        s = math.sin(angle / 2.0)
        return (math.cos(angle / 2.0), axis[0] * s, axis[1] * s, axis[2] * s)


    ROOT_TOTAL_MAT = rot_z(ROOT_YAW_RAD) @ rot_y(ROOT_PITCH_RAD)

    # The batter's fixed release-facing target for the head (world coords) --
    # BaseballB1Env.RELEASE; duplicated here as a plain constant since this
    # script has no import path to the env module and the value is a fixed
    # field-geometry constant, not something derived per-episode.
    RELEASE_WORLD_POS = np.array([16.5, 0.0, 1.8])


    tree = ET.parse(SRC)
    root = tree.getroot()
    worldbody = root.find("worldbody")
    flybody = worldbody.find("body")
    assert flybody.get("name") == "FlyBody"
    thorax = flybody.find("body")
    assert thorax.get("name") == "Thorax"

    used_mesh_names = set()


    def scale_pos(elem):
        p = elem.get("pos")
        if p is None:
            return
        vals = [float(x) for x in p.split()]
        vals = [v * (K / 1000.0) for v in vals]
        elem.set("pos", " ".join(f"{v:.8f}" for v in vals))


    def strip_physics_attrs(geom):
        for attr in ["mass", "friction", "solref", "condim", "margin", "fluidcoef", "class"]:
            if attr in geom.attrib:
                del geom.attrib[attr]
        geom.set("contype", "0")
        geom.set("conaffinity", "0")
        geom.set("group", "2")
        part_name = geom.get("name")
        appearance_group = PART_TO_GROUP.get(part_name)
        if appearance_group is None:
            raise ValueError(
                f"geom {part_name!r} has no entry in APPEARANCE_GROUPS -- every kept part must have an "
                "explicit flygym==1.2.1 config.yaml-derived appearance, not a silent fallback color."
            )
        geom.set("material", f"fly_appearance_{appearance_group}")
        mesh_name = geom.get("mesh")
        if mesh_name:
            used_mesh_names.add(mesh_name)


    def process_subtree(body_elem):
        """Recursively rescale positions, clean geoms, and drop joints (fully
        static subtree) in a kept subtree."""
        scale_pos(body_elem)
        for geom in body_elem.findall("geom"):
            strip_physics_attrs(geom)
        for jt in body_elem.findall("joint"):
            body_elem.remove(jt)
        for child in body_elem.findall("body"):
            process_subtree(child)


    def take_leg_chain(coxa_elem, keep_depth):
        """Strip joints/physics-attrs and rescale a Coxa..Tarsus1 chain in
        place, pruning anything deeper than keep_depth. Returns the deepest
        kept element (for further per-leg posing)."""
        for jt in coxa_elem.findall("joint"):
            coxa_elem.remove(jt)
        for geom in coxa_elem.findall("geom"):
            strip_physics_attrs(geom)
        scale_pos(coxa_elem)
        cur = coxa_elem
        depth = 1
        while depth < len(keep_depth):
            nxt = cur.find("body")
            if nxt is None:
                break
            for jt in nxt.findall("joint"):
                nxt.remove(jt)
            for geom in nxt.findall("geom"):
                strip_physics_attrs(geom)
            scale_pos(nxt)
            cur = nxt
            depth += 1
        deeper = cur.find("body")
        if deeper is not None:
            cur.remove(deeper)
        return cur


    # --- Thorax's direct children we keep verbatim (abdomen chain, wings, halteres) ---
    kept_children = []
    for child in list(thorax):
        if child.tag == "geom":
            strip_physics_attrs(child)
            continue
        if child.tag != "body":
            continue
        name = child.get("name")
        if name in KEEP_TOP_LEVEL_NON_LEG:
            process_subtree(child)
            kept_children.append(child)
        elif any(name == f"{side}Coxa" for side in GROUND_LEGS):
            take_leg_chain(child, GROUND_KEEP_DEPTH)
            # cancels the FlyBody root rotation; leg keeps its authored
            # "stand on the ground" shape/orientation relative to true gravity
            cq = axis_angle_y_quat(COMP_RAD)
            child.set("quat", f"{cq[0]:.8f} {cq[1]:.8f} {cq[2]:.8f} {cq[3]:.8f}")
            kept_children.append(child)
        elif any(name == f"{side}Coxa" for side in FOLD_LEGS):
            take_leg_chain(child, FOLD_KEEP_DEPTH)
            # root-rotation compensation at the coxa, PLUS a fold bend at
            # femur/tibia (each about their own local Y, same physical axis
            # since every body here shares an identity quat in the source
            # rest pose) baked in as static quats the same way.
            cq = axis_angle_y_quat(COMP_RAD)
            child.set("quat", f"{cq[0]:.8f} {cq[1]:.8f} {cq[2]:.8f} {cq[3]:.8f}")
            femur_body = child.find("body")
            fq = axis_angle_y_quat(FOLD_FEMUR_PITCH_RAD)
            femur_body.set("quat", f"{fq[0]:.8f} {fq[1]:.8f} {fq[2]:.8f} {fq[3]:.8f}")
            tibia_body = femur_body.find("body")
            tq = axis_angle_y_quat(FOLD_TIBIA_PITCH_RAD)
            tibia_body.set("quat", f"{tq[0]:.8f} {tq[1]:.8f} {tq[2]:.8f} {tq[3]:.8f}")
            kept_children.append(child)
        elif any(name == f"{side}Coxa" for side in FRONT_LEGS):
            # Coxa only in the static rig (the shoulder anchor); Femur/Tibia/
            # Tarsus1 are pruned here and re-derived separately below for the
            # dynamic IK (envs/fly_visual.py), at the SAME uniform K.
            for jt in child.findall("joint"):
                child.remove(jt)
            for geom in child.findall("geom"):
                strip_physics_attrs(geom)
            scale_pos(child)
            deeper = child.find("body")
            if deeper is not None:
                child.remove(deeper)
            cq = axis_angle_y_quat(COMP_RAD)
            child.set("quat", f"{cq[0]:.8f} {cq[1]:.8f} {cq[2]:.8f} {cq[3]:.8f}")
            kept_children.append(child)
        # else: drop (not in our keep list)

    # Rebuild Thorax: keep its own geom + only the kept children
    thorax_geom = thorax.find("geom")
    strip_physics_attrs(thorax_geom)
    for child in list(thorax):
        if child.tag == "body":
            thorax.remove(child)
    for child in kept_children:
        thorax.append(child)
    thorax_prerotation_pos = np.array([float(x) for x in thorax.get("pos").split()]) * (K / 1000.0)
    scale_pos(thorax)

    # --- Rebuild FlyBody: keep only Thorax (Head is nested inside Thorax; see
    # KEEP_TOP_LEVEL_NON_LEG above), drop anything else directly under FlyBody ---
    for child in list(flybody):
        if child.tag == "body" and child.get("name") != "Thorax":
            flybody.remove(child)
    root_quat = quat_from_mat(ROOT_TOTAL_MAT)
    flybody.set("quat", f"{root_quat[0]:.8f} {root_quat[1]:.8f} {root_quat[2]:.8f} {root_quat[3]:.8f}")
    flybody.set("name", "fly_visual")

    # --- Recentering (I-08a-fix; docs/records/FLY-VISUAL-REVIEW.md): FlyBody
    # (our rotation pivot) sits at the origin of the source rig's own frame,
    # but Thorax -- the actual body mass, and the parent every leg/head hangs
    # from -- is offset from that pivot (thorax_prerotation_pos). Rotating
    # about a pivot that ISN'T at the body's own center swings the whole body
    # sideways: at ROOT_PITCH_RAD=-90deg this puts Thorax about 0.52m off in
    # X, which dragged the front legs' shoulders (LFCoxa/RFCoxa, close to
    # Thorax) far enough from the bat that even a full-length arm fell ~0.11-
    # 0.15m short of the grip sites for the ENTIRE episode, prep pose
    # included -- not a swing-dynamics problem, a static placement one (see
    # VALIDATION_LOG.md for the measured before/after). Fixed by translating
    # fly_visual's own X/Y so Thorax's ROTATED position lands back at (0,0)
    # relative to batter_body -- i.e. the body (not an arbitrary rig-authored
    # pivot) is what's centered under batter_body. Z is untouched here (still
    # set below, purely from the real sole-vertex measurement).
    thorax_rotated = ROOT_TOTAL_MAT @ thorax_prerotation_pos
    thorax_rotated_xy = thorax_rotated[:2]
    recenter_xy = -thorax_rotated_xy
    print(f"thorax pre-rotation pos: {thorax_prerotation_pos}, rotated xy: {thorax_rotated_xy}, "
          f"recenter_xy: {recenter_xy}")

    # --- Front-leg dynamic segment lengths (Femur, Tibia, Tarsus1), at the
    # SAME uniform K, measured from the source rig's own rest-pose child-body
    # offsets (the distance each mesh is authored to span between its own
    # proximal and distal joints). Symmetric L/R by construction. Uses a FRESH
    # re-parse of SRC (the FLF/RF Femur/Tibia/Tarsus bodies were already pruned
    # out of `root`/`thorax` above). ---
    _src_tree_for_lengths = ET.parse(SRC)


    def child_offset_len(body_name, child_name):
        b = None
        for e in _src_tree_for_lengths.getroot().iter("body"):
            if e.get("name") == body_name:
                b = e
                break
        c = None
        for e in b.iter("body"):
            if e.get("name") == child_name:
                c = e
                break
        p = np.array([float(x) for x in c.get("pos").split()])
        return float(np.linalg.norm(p)) * (K / 1000.0)


    front_leg_lengths = {
        "femur_m": child_offset_len("LFFemur", "LFTibia"),
        "tibia_m": child_offset_len("LFTibia", "LFTarsus1"),
        "tarsus1_m": child_offset_len("LFTarsus1", "LFTarsus2"),
    }
    print(f"front leg segment lengths (m, K={K:.0f}):", front_leg_lengths)

    # --- Assets: keep only meshes actually referenced in the static rig, plus
    # the front legs' dynamic meshes (Femur/Tibia/Tarsus1, L and R), all at the
    # SAME K (no separate arm scale) ---
    for side in FRONT_LEGS:
        for seg in ("Femur", "Tibia", "Tarsus1"):
            used_mesh_names.add(f"mesh_{side}{seg}")

    asset = root.find("asset")
    for mesh in list(asset.findall("mesh")):
        name = mesh.get("name")
        if name not in used_mesh_names:
            asset.remove(mesh)
            continue
        stem = name.removeprefix("mesh_")
        mesh.set("name", f"fly_{name}")
        mesh.set("file", f"{MESH_DIR}/{stem}.stl")
        mesh.set("scale", f"{K} {K} {K}")
        if "class" in mesh.attrib:
            del mesh.attrib["class"]

    # fix up geom mesh references to the renamed fly_ prefix
    for geom in thorax.iter("geom"):
        m = geom.get("mesh")
        if m:
            geom.set("mesh", f"fly_{m}")

    print("kept meshes:", sorted(used_mesh_names))
    print("num kept meshes:", len(used_mesh_names))

    mesh_xml = "\n".join(ET.tostring(m, encoding="unicode").strip() for m in asset.findall("mesh"))


    def _fmt(vals) -> str:
        return " ".join(f"{v:.6g}" for v in vals)


    # I-08a-style: one <texture>/<material> pair per appearance group (see
    # APPEARANCE_GROUPS above), reproducing flygym==1.2.1's config.yaml
    # exactly. Groups with texture=None (wing/eye/arista/haltere) get a
    # material with no texture reference, matching config.yaml's
    # `texture: null`.
    appearance_xml_parts = []
    for group, spec in APPEARANCE_GROUPS.items():
        mat_name = f"fly_appearance_{group}"
        tex = spec["texture"]
        if tex is not None:
            tex_name = f"fly_tex_{group}"
            appearance_xml_parts.append(
                f'<texture name="{tex_name}" type="2d" builtin="{tex["builtin"]}" '
                f'rgb1="{_fmt(tex["rgb1"])}" rgb2="{_fmt(tex["rgb2"])}" '
                f'markrgb="{_fmt(tex["markrgb"])}" random="{tex["random"]}" '
                f'width="{tex["size"]}" height="{tex["size"]}"/>'
            )
            appearance_xml_parts.append(
                f'<material name="{mat_name}" texture="{tex_name}" texuniform="true" '
                f'rgba="{_fmt(spec["rgba"])}"/>'
            )
        else:
            appearance_xml_parts.append(f'<material name="{mat_name}" rgba="{_fmt(spec["rgba"])}"/>')
    appearance_xml = "\n".join(appearance_xml_parts)

    asset_xml = mesh_xml + "\n" + appearance_xml
    asset_path = OUT_DIR / "fly_visual_assets.xml"
    # MuJoCo's <include> requires the included file to be a single well-formed
    # XML document; bare sibling elements aren't valid XML on their own, so
    # wrap in the (non-standard-MJCF-root) <mujocoinclude> convention MuJoCo
    # recognizes and splices at the inclusion point.
    asset_path.write_text(f"<mujocoinclude>\n{asset_xml}\n</mujocoinclude>\n")


    def compile_probe(flybody_elem) -> tuple[mujoco.MjModel, mujoco.MjData]:
        probe_xml = f"""<mujoco model="fly_visual_probe">
      <compiler angle="radian" meshdir="{OUT_DIR}"/>
      <asset>
    {asset_xml}
      </asset>
      <worldbody>{ET.tostring(flybody_elem, encoding="unicode")}</worldbody>
    </mujoco>"""
        probe_path = OUT_DIR / "_fly_visual_probe.xml"
        probe_path.write_text(probe_xml)
        m = mujoco.MjModel.from_xml_path(str(probe_path))
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        probe_path.unlink()
        return m, d


    # --- Head direction (docs/design/FLY-BATTING-STANCE-AND-COLOR.md section 1):
    # find Head (nested inside Thorax), solve for a LOCAL rotation (pivoting at
    # its own neck attachment, identity for now) that points the head's own
    # forward axis (source local +X, the eyes/antennae-forward direction --
    # also the SAME axis used as the "stand up" axis, which is exactly why the
    # head needs its OWN separate correction: after the body transform alone,
    # local +X ends up pointing world +Z, i.e. straight up, not at the
    # pitcher) at BaseballB1Env.RELEASE. Solved numerically (probe with
    # Head's quat still identity, actual world head position, exact target
    # vector), not a fixed guessed angle, then verified below (<=10deg design
    # tolerance).
    flybody.set("pos", f"{recenter_xy[0]:.6f} {recenter_xy[1]:.6f} 0")
    head_elem = None
    for e in thorax.iter("body"):
        if e.get("name") == "Head":
            head_elem = e
            break
    assert head_elem is not None
    probe_model, probe_data = compile_probe(flybody)
    head_bid_pre = mujoco.mj_name2id(probe_model, mujoco.mjtObj.mjOBJ_BODY, "Head")
    head_world_pos_pre = probe_data.xpos[head_bid_pre].copy()
    desired_head_dir_world = RELEASE_WORLD_POS - head_world_pos_pre
    desired_head_dir_world /= np.linalg.norm(desired_head_dir_world)
    local_target = ROOT_TOTAL_MAT.T @ desired_head_dir_world
    head_quat = align_vectors_quat(np.array([1.0, 0.0, 0.0]), local_target)
    head_elem.set("quat", f"{head_quat[0]:.8f} {head_quat[1]:.8f} {head_quat[2]:.8f} {head_quat[3]:.8f}")
    print(f"head world pos (pre-rotation): {head_world_pos_pre}, "
          f"desired world dir: {desired_head_dir_world}, local target: {local_target}")

    # --- Ground calibration: re-compile with the head rotation now baked in,
    # and read the REAL transformed mesh vertices (not geom origins) of the
    # two ground legs' Tarsus1 to find the true lowest point. Also verifies
    # the head-direction solve above against the ACTUAL compiled geometry. ---
    probe_model, probe_data = compile_probe(flybody)

    head_bid_check = mujoco.mj_name2id(probe_model, mujoco.mjtObj.mjOBJ_BODY, "Head")
    head_pos_check = probe_data.xpos[head_bid_check]
    head_mat_check = probe_data.xmat[head_bid_check].reshape(3, 3)
    actual_head_fwd = head_mat_check @ np.array([1.0, 0.0, 0.0])
    true_desired_dir = RELEASE_WORLD_POS - head_pos_check
    true_desired_dir /= np.linalg.norm(true_desired_dir)
    head_angle_error_deg = math.degrees(
        math.acos(np.clip(float(np.dot(actual_head_fwd, true_desired_dir)), -1.0, 1.0))
    )
    print(f"head-forward vs. release-direction angle error: {head_angle_error_deg:.2f} deg "
          f"(design tolerance: <=10 deg)")
    if head_angle_error_deg > 10.0:
        raise SystemExit(f"head direction error {head_angle_error_deg:.2f}deg exceeds the 10deg design tolerance")

    min_sole_z = math.inf
    for side in GROUND_LEGS:
        gid = mujoco.mj_name2id(probe_model, mujoco.mjtObj.mjOBJ_GEOM, f"{side}Tarsus1")
        verts = geom_world_vertices(probe_model, probe_data, gid, OUT_DIR / MESH_DIR)
        min_sole_z = min(min_sole_z, float(verts[:, 2].min()))

    head_gid = mujoco.mj_name2id(probe_model, mujoco.mjtObj.mjOBJ_GEOM, "Head")
    head_verts = geom_world_vertices(probe_model, probe_data, head_gid, OUT_DIR / MESH_DIR)
    head_top_z = float(head_verts[:, 2].max())
    print(
        f"min sole vertex z (fly_visual at local origin): {min_sole_z:.4f}, "
        f"head top vertex z: {head_top_z:.4f}, standing height: {head_top_z - min_sole_z:.4f}m"
    )

    # fly_visual is nested under batter_body (world pos BATTER_WORLD_POS); we
    # want the sole's WORLD z to land at 0 (true ground), i.e.
    # BATTER_WORLD_POS[2] + local_z_offset + min_sole_z == 0.
    local_z_offset = -BATTER_WORLD_POS[2] - min_sole_z
    flybody.set("pos", f"{recenter_xy[0]:.6f} {recenter_xy[1]:.6f} {local_z_offset:.6f}")
    print(f"fly_visual local pos set to ({recenter_xy[0]:.6f}, {recenter_xy[1]:.6f}, {local_z_offset:.6f}) "
          f"(batter_body world z={BATTER_WORLD_POS[2]}, so world sole z = "
          f"{BATTER_WORLD_POS[2] + local_z_offset + min_sole_z:.6f})")

    body_xml = ET.tostring(flybody, encoding="unicode")
    body_path = OUT_DIR / "fly_visual_body.xml"
    body_path.write_text(f"<mujocoinclude>\n{body_xml}\n</mujocoinclude>\n")

    print("wrote", asset_path)
    print("wrote", body_path)
    print("done")


if __name__ == "__main__":
    main()

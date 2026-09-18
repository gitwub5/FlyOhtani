"""마운드 위의 투수 파리.

던지지는 않는다 -- 공은 `flyshohei.pitch.geometry`가 쏘고, 이 몸은 보는 사람이
가장 먼저 묻는 것("공이 어디서 오는가")에 답한다. 릴리스 지점이 공중의 맨
점이던 동안에는 그 질문에 답이 없었다.

`pitch`와 달리 이 모듈은 `flyohtani.world.batter`의 몸 복사 기계를 쓴다. 그래서 의존
방향이 반대이고, 장면을 만드는 쪽에서 **늦게** 임포트해야 한다.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from flyohtani.world import batter as B
from flyohtani.world.batter import DIRT_TOP_MM
from flyohtani.world.park import MOUND_HEIGHT_MM
from flyshohei.pitch import PITCH_DISTANCE_MM

PITCHER_POSE = {
    **B.STATIC_POSE,
    # right foreleg up and back: the arm the ball leaves from
    "joint_RFCoxa": math.radians(-150), "joint_RFFemur": math.radians(-40),
    "joint_RFTibia": math.radians(70), "joint_RFTarsus1": math.radians(-20),
    "joint_LFCoxa": math.radians(-40), "joint_LFFemur": math.radians(-80),
    "joint_LFTibia": math.radians(95),
}
"""The pitcher's pose: the same static-copy machinery as the batter's own
non-driven legs, with the throwing arm raised. Visual only -- nothing about
this fly is simulated, and the ball's release point comes from the pitch
geometry, not from its hand."""


def pitcher_subtree(src_root: ET.Element, scale: float, foot_z: float = 0.0) -> ET.Element:
    """A second fly, standing on the rubber, facing home plate."""
    facing = B._qmul(B._quat_axis_angle([0.0, 0.0, 1.0], math.pi), B.STANCE_QUAT)
    # `foot_z` is where the probe found this fly's feet, so subtracting it
    # stands the pitcher ON the mound instead of sinking it into one.
    body = ET.Element("body", {
        "name": "Pitcher",
        "pos": f"{PITCH_DISTANCE_MM * scale:.6g} 0 "
               f"{MOUND_HEIGHT_MM * scale - foot_z + DIRT_TOP_MM:.6g}",
        "quat": B._qstr(facing)})
    thorax_src = B._find_body(src_root, "Thorax")
    thorax = ET.SubElement(body, "body", {"name": "P_Thorax", "pos": thorax_src.get("pos")})
    for g in thorax_src.findall("geom"):
        geom = B._copy_geom(g, collide=False)
        geom.set("group", str(B.GROUP_FLY))
        geom.set("rgba", B._CHITIN)
        if geom.get("name"):
            geom.set("name", "P_" + geom.get("name"))
        thorax.append(geom)
    for child in thorax_src.findall("body"):
        thorax.append(B._static_copy(child, group=B.GROUP_FLY, skip=set(),
                                   pose=PITCHER_POSE, prefix="P_"))
    return body

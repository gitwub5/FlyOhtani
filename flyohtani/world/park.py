"""The ballpark: everything the fly plays in and never touches.

Foul lines, bases, the mound, the outfield fence, the stands, the foul poles
and the backstop. Every geom here has collisions off -- the batted ball lands
on the ground plane, and nothing out here can stop it or touch the fly.

One part of it is not decoration. The dark section of the centre-field stands
is the batter's eye, and VM-01 measured what it buys: against the bright sky
a white ball reaches 6% contrast in this eye and is missed in two frames out
of nine; against this it is seen from the release point on. A real ballpark
has one for the same reason.

The pitcher standing on the mound is not here: it is a fly, and it
lives in `flyshohei.body`.

Dimensions are real-ballpark millimetres, scaled by the D27 rule like
everything else. Split out of batter.py, which was doing six jobs.
"""
from __future__ import annotations

import itertools
import math
import xml.etree.ElementTree as ET

import numpy as np

from flyohtani.flyshohei.pitch import PITCH_DISTANCE_MM
from flyohtani.world.batter import (
    CHALK_WIDTH_MM,
    DIRT_TOP_MM,
    GROUP_WORLD,
)

# ---------------------------------------------------------------- the park
# Real-ballpark millimetres, scaled by `scale` like every other dimension
# (D27). All of it is visual: contype=0, so the ball still lands on the
# ground plane and nothing here can touch the fly.

BASE_PATH_MM = 27_432.0        # 90 ft between bases
BASE_SIDE_MM = 381.0           # 15 in
MOUND_RADIUS_MM = 2_743.0      # 9 ft
MOUND_HEIGHT_MM = 254.0        # 10 in
RUBBER_MM = (610.0, 152.0)     # 24 x 6 in
INFIELD_ARC_MM = 28_956.0      # 95 ft from the mound centre
BASE_PATH_WIDTH_MM = 1_829.0   # 6 ft
FENCE_LINE_MM = 99_060.0       # 325 ft down the lines
FENCE_CENTER_MM = 121_920.0    # 400 ft to dead centre
FENCE_HEIGHT_MM = 3_658.0      # 12 ft -- taller than the 8 ft minimum, as many parks are
FOUL_POLE_HEIGHT_MM = 12_000.0
BACKSTOP_MM = 18_288.0         # 60 ft behind the plate
BACKSTOP_HEIGHT_MM = 9_000.0
STANDS_DEPTH_MM = 22_000.0
STANDS_HEIGHT_MM = (12_000.0, 20_000.0)
BATTERS_EYE_HALF_ANGLE_DEG = 12.0
BATTERS_EYE_HEIGHT_MM = 22_000.0
"""The batter's eye is not a free-standing wall: it is the dark section of
the centre-field stands, which is what it is in a real park. VM-01 v3
measured why it has to be there at all -- against the bright sky a white ball
reaches 6% contrast in this eye and is missed; against this it is seen from
the release point.

It is 22 m tall and 24 deg wide because the ball RISES: pitched from 33 mm
with a 21 deg launch, it climbs out of a 14 m screen in the last frames
before the swing must start, and the contrast measured there fell from 21%
to 5% the moment it crossed into the sky. The stands around it are dark for
the same reason -- a real crowd is not bright concrete."""


def _fence_radius_mm(theta_rad: float) -> float:
    """A real outfield fence is shortest down the lines and deepest in dead
    centre; this interpolates between the two with cos(2*theta), which is
    exact at both ends (theta = 0 and +/- 45 deg)."""
    return FENCE_LINE_MM + (FENCE_CENTER_MM - FENCE_LINE_MM) * math.cos(2 * theta_rad)


def _wall_segment(name: str, inner_mm: float, outer_mm: float, theta0: float, theta1: float,
                  height_mm: float, scale: float, rgba: str) -> ET.Element:
    """One box spanning an arc, laid ALONG the chord between two angles: the
    box's local x runs tangentially, its y is the wall's thickness. Rotating
    it the other way turns a wall into a row of radial fins."""
    a = np.array([math.cos(theta0), math.sin(theta0)]) * inner_mm
    b = np.array([math.cos(theta1), math.sin(theta1)]) * inner_mm
    mid_dir = np.array([math.cos((theta0 + theta1) / 2), math.sin((theta0 + theta1) / 2)])
    centre = (a + b) / 2 + mid_dir * (outer_mm - inner_mm) / 2
    # Long enough to cover the OUTER edge of its own wedge: a box sized to
    # the inner chord leaves a widening gap against its neighbour, which
    # reads as a vertical slot in the stands.
    half_len = float(np.linalg.norm(b - a) / 2) * (outer_mm / inner_mm) * 1.02
    yaw = math.atan2(b[1] - a[1], b[0] - a[0])
    return ET.Element("geom", {
        "name": name, "type": "box",
        "size": f"{half_len * scale:.6g} {max(outer_mm - inner_mm, 200.0) * scale / 2:.6g} "
                f"{height_mm * scale / 2:.6g}",
        "pos": f"{centre[0] * scale:.6g} {centre[1] * scale:.6g} {height_mm * scale / 2:.6g}",
        "euler": f"0 0 {yaw:.6g}",
        "rgba": rgba, "contype": "0", "conaffinity": "0", "group": str(GROUP_WORLD)})


def ballpark_geoms(scale: float) -> list[ET.Element]:
    """The park, as scenery (D31c). Every geom here is visual only."""
    out: list[ET.Element] = []
    z = DIRT_TOP_MM

    def flat(name: str, centre, half, material: str, lift: float = 0.0, yaw: float = 0.0):
        out.append(ET.Element("geom", {
            "name": name, "type": "box",
            "size": f"{half[0] * scale:.6g} {half[1] * scale:.6g} {0.0005:.6g}",
            "pos": f"{centre[0] * scale:.6g} {centre[1] * scale:.6g} {z + 0.0005 + lift:.6g}",
            "euler": f"0 0 {yaw:.6g}", "material": material,
            "contype": "0", "conaffinity": "0", "group": str(GROUP_WORLD)}))

    # foul lines and the bases they run to
    corner = BASE_PATH_MM / math.sqrt(2)
    for sign, side in ((+1, "third"), (-1, "first")):
        flat(f"foul_line_{side}", (FENCE_LINE_MM / 2 * math.cos(math.pi / 4),
                                   sign * FENCE_LINE_MM / 2 * math.sin(math.pi / 4)),
             (FENCE_LINE_MM / 2, CHALK_WIDTH_MM / 2), "chalk", yaw=sign * math.pi / 4)
        flat(f"base_{side}", (corner, sign * corner), (BASE_SIDE_MM / 2, BASE_SIDE_MM / 2), "chalk", lift=0.001)
        flat(f"path_{side}", (corner / 2, sign * corner / 2),
             (BASE_PATH_MM / 2, BASE_PATH_WIDTH_MM / 2), "dirt", yaw=sign * math.pi / 4)
        flat(f"path_{side}_out", (corner + corner / 2, sign * corner / 2),
             (BASE_PATH_MM / 2, BASE_PATH_WIDTH_MM / 2), "dirt", yaw=-sign * math.pi / 4)
    flat("base_second", (BASE_PATH_MM * math.sqrt(2), 0.0),
         (BASE_SIDE_MM / 2, BASE_SIDE_MM / 2), "chalk", lift=0.001)

    # infield skin: the 95 ft arc measured from the mound, drawn as a disc
    out.append(ET.Element("geom", {
        "name": "infield_skin", "type": "cylinder",
        "size": f"{INFIELD_ARC_MM * scale:.6g} {DIRT_TOP_MM / 4:.6g}",
        "pos": f"{PITCH_DISTANCE_MM * scale:.6g} 0 {DIRT_TOP_MM / 4:.6g}",
        "material": "dirt", "contype": "0", "conaffinity": "0", "group": str(GROUP_WORLD)}))
    # ... with the grass cut back in, leaving the base paths above on top
    out.append(ET.Element("geom", {
        "name": "infield_grass", "type": "cylinder",
        "size": f"{(INFIELD_ARC_MM - BASE_PATH_WIDTH_MM * 2) * scale:.6g} {DIRT_TOP_MM / 6:.6g}",
        "pos": f"{PITCH_DISTANCE_MM * scale:.6g} 0 {DIRT_TOP_MM / 2 + 0.0002:.6g}",
        "material": "grass", "contype": "0", "conaffinity": "0", "group": str(GROUP_WORLD)}))

    # mound and rubber
    out.append(ET.Element("geom", {
        "name": "mound", "type": "cylinder",
        "size": f"{MOUND_RADIUS_MM * scale:.6g} {MOUND_HEIGHT_MM * scale / 2:.6g}",
        "pos": f"{PITCH_DISTANCE_MM * scale:.6g} 0 {MOUND_HEIGHT_MM * scale / 2:.6g}",
        "material": "dirt", "contype": "0", "conaffinity": "0", "group": str(GROUP_WORLD)}))
    out.append(ET.Element("geom", {
        "name": "rubber", "type": "box",
        "size": f"{RUBBER_MM[1] * scale / 2:.6g} {RUBBER_MM[0] * scale / 2:.6g} {0.0005:.6g}",
        "pos": f"{PITCH_DISTANCE_MM * scale:.6g} 0 {MOUND_HEIGHT_MM * scale + 0.0005:.6g}",
        "material": "chalk", "contype": "0", "conaffinity": "0", "group": str(GROUP_WORLD)}))

    # outfield fence, the stands behind it, and the batter's eye in centre
    n = 28
    edges = [math.radians(-45 + 90 * i / n) for i in range(n + 1)]
    for i, (t0, t1) in enumerate(itertools.pairwise(edges)):
        r0, r1 = _fence_radius_mm(t0), _fence_radius_mm(t1)
        r = (r0 + r1) / 2
        dark = abs(math.degrees((t0 + t1) / 2)) <= BATTERS_EYE_HALF_ANGLE_DEG
        tag = "batters_eye_" if dark else ""
        # One colour all the way round: in a real park the batter's eye is the
        # screen BEHIND the fence, not a repainted stretch of it.
        out.append(_wall_segment(f"fence{i}", r, r + 300.0, t0, t1, FENCE_HEIGHT_MM, scale,
                                 "0.13 0.26 0.17 1"))
        out.append(_wall_segment(
            f"{tag}stand{i}", r + 2_000.0, r + 2_000.0 + STANDS_DEPTH_MM, t0, t1,
            BATTERS_EYE_HEIGHT_MM if dark else STANDS_HEIGHT_MM[0], scale,
            "0.07 0.11 0.08 1" if dark else "0.30 0.31 0.34 1"))
        if not dark:
            out.append(_wall_segment(f"stand_upper{i}", r + 2_000.0 + STANDS_DEPTH_MM,
                                     r + 2_000.0 + 2 * STANDS_DEPTH_MM, t0, t1,
                                     STANDS_HEIGHT_MM[1], scale, "0.26 0.27 0.30 1"))
    for sign in (+1, -1):
        t = sign * math.radians(45)
        r = _fence_radius_mm(t)
        out.append(ET.Element("geom", {
            "name": f"foul_pole_{'third' if sign > 0 else 'first'}", "type": "cylinder",
            "size": f"{150.0 * scale:.6g} {FOUL_POLE_HEIGHT_MM * scale / 2:.6g}",
            "pos": f"{r * math.cos(t) * scale:.6g} {r * math.sin(t) * scale:.6g} "
                   f"{FOUL_POLE_HEIGHT_MM * scale / 2:.6g}",
            "rgba": "0.95 0.80 0.15 1", "contype": "0", "conaffinity": "0",
            "group": str(GROUP_WORLD)}))

    # backstop and the stands behind the plate
    back = [math.radians(135 + 90 * i / 8) for i in range(9)]
    for i, (t0, t1) in enumerate(itertools.pairwise(back)):
        out.append(_wall_segment(f"backstop{i}", BACKSTOP_MM, BACKSTOP_MM + 300.0, t0, t1,
                                 BACKSTOP_HEIGHT_MM, scale, "0.30 0.32 0.33 1"))
        out.append(_wall_segment(f"stand_home{i}", BACKSTOP_MM + 2_000.0,
                                 BACKSTOP_MM + 2_000.0 + STANDS_DEPTH_MM, t0, t1,
                                 STANDS_HEIGHT_MM[1], scale, "0.28 0.29 0.32 1"))
    return out

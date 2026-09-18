"""What the pitcher throws: the arsenal, and the geometry of one delivery.

Nothing here knows about the batter, the scene or MuJoCo -- a pitch is a
release point, a flight time and the parabola between them. That is what
keeps this module importable from `flyohtani.world.batter` without a cycle.

A pitch in this simulation is determined by exactly two numbers: **how long
the ball is in the air** and **where it is released from**. Speed and launch
angle are consequences, so they are computed (`Pitch.speed_mm_s`,
`Pitch.launch_angle_deg`) rather than stored -- the two used to be written
down by hand in two places and had already drifted apart (658 vs 698 mm/s for
the same pitch).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flyohtani import units

# ---------------------------------------------------------------- the mound
# Real-ballpark millimetres, scaled by the D27 rule like every other
# dimension. Where the pitcher stands, and where its hand is when the ball
# leaves it.

PITCH_DISTANCE_MM = 18_440.0   # 60 ft 6 in, plate to rubber
PITCHER_EXTENSION_MM = 1_700.0  # release point in front of the rubber, typical
RELEASE_HEIGHT_MM = 1_800.0    # typical overhand release height

FROM_MOUND = True
"""D35. The ball leaves the pitcher's hand, on the rubber, 34.2 mm away --
not from a point in the air 122 mm out.

D32 put the release at 122 mm because the fly needed time to watch, and the
arithmetic said a pitch long enough to watch had to be thrown from far enough
back to stay flat. That arithmetic used the wrong deadline: it assumed the
whole swing had to finish before contact, when contact happens 24.6 ms into
it (see `flyohtani.world.batter.SWING_TO_CONTACT_S`). With the corrected deadline a
52 ms pitch from the real mound clears every constraint, so the release goes
back where a pitcher's hand is."""


@dataclass(frozen=True)
class Pitch:
    """One pitch type.

    `flight_s` is the whole pitch: lengthen it and the ball is slower, the
    arc deeper, and the eye rate the fly needs is lower
    (`flyohtani.world.batter.min_eye_rate_hz` -- VM-01's hold-out failed precisely
    because flight time and eye rate were treated as independent).

    `distance_scale` moves the release point along the line from the plate:
    1.0 is the pitcher's own hand, larger is farther out. D32 used 3.6 and
    D35 put it back to 1.0."""

    name: str
    flight_s: float
    distance_scale: float = 1.0
    note: str = ""

    def speed_mm_s(self, strike: np.ndarray, scale: float, **kw) -> float:
        """Release speed for a pitch aimed at `strike`. Derived, not stored:
        the straight-line figure (distance / flight) understates it, because
        the ball is thrown upward and gravity bends it back down."""
        _, v0, _ = geometry(strike, scale, pitch=self, **kw)
        return float(np.linalg.norm(v0))

    def launch_angle_deg(self, strike: np.ndarray, scale: float, **kw) -> float:
        """How far above horizontal the ball leaves the hand. Gravity sets
        it: over `flight_s` the ball falls one half g t squared, and a short
        pitch has to be lofted to arrive at the plate rather than in the
        dirt."""
        _, v0, _ = geometry(strike, scale, pitch=self, **kw)
        return math.degrees(math.atan2(float(v0[2]), float(np.hypot(v0[0], v0[1]))))


STANDARD = Pitch(
    name="standard",
    flight_s=0.052,
    note="D35. 24.6 ms of swing to contact + 10 ms of decision latency + "
         "eight eye frames at 480 Hz (17 ms). It is thrown from the rubber, "
         "which costs speed: 35% of a Froude-scaled Kershaw fastball. At "
         "that speed over 34.2 mm it is a lofted changeup, not a fastball.",
)
"""The only pitch that exists. Every measurement in docs/records/ was taken
with this one."""

ARSENAL: dict[str, Pitch] = {p.name: p for p in (STANDARD,)}
"""구종. 하나뿐인 것이 정직한 상태다 -- 두 번째를 넣으려면:

- **구속·비행 시간만 다른 공**(체인지업, 슬로볼)은 지금 바로 된다. `Pitch`를
  하나 더 만들면 끝이다. 대신 **눈 프레임률이 따라 움직인다**
  (`flyohtani.world.batter.min_eye_rate_hz`), 그리고 느린 공은 더 높이 던져 올려야
  해서 궤적이 휜다(D32가 측정한 것).
- **휘는 공**(커브·슬라이더)은 숫자를 하나 더 넣어서 되지 않는다. 지금 공에는
  항력도 스핀도 없어서(`flyohtani.world.swing.batted_ball`의 포물선이 정확한 이유가
  그것이다) 마그누스 힘을 먼저 모델에 넣어야 한다. 그 전에는 "커브"라고 이름만
  붙이는 셈이 된다.
"""


def get(name: str) -> Pitch:
    """The pitch by name, or KeyError. Not a default -- a typo that silently
    threw the standard pitch would be a measurement of the wrong thing."""
    return ARSENAL[name]


def geometry(strike: np.ndarray, scale: float, distance_scale: float | None = None,
             flight_s: float | None = None,
             release_reference: np.ndarray | None = None,
             pitch: Pitch = STANDARD) -> tuple[np.ndarray, np.ndarray, float]:
    """Release point, launch velocity and flight time for one delivery: a
    ball thrown down the same line of approach as a real pitch, arriving at
    `strike` after the pitch's flight time.

    `distance_scale` and `flight_s` override the pitch's own values, for
    measurements that need the ball farther out or slower.

    `release_reference` is where the release point is computed FROM, and it
    defaults to `strike` only for a single-zone pitch. With strike zones it
    must be passed, and must not depend on the zone -- the release point is
    the pitcher's hand, and a pitcher does not move when aiming higher.

    That was a real bug: deriving the release from the strike point meant
    aiming 0.45 mm higher dropped the hand 1.16 mm (the line pivots, and the
    release is 3.6 times farther out than the plate). A high pitch then
    appeared LOWER in the eye than a low one, which is the opposite of the
    thing the fly is supposed to read."""
    flight = pitch.flight_s if flight_s is None else flight_s
    hand = np.array([(PITCH_DISTANCE_MM - PITCHER_EXTENSION_MM) * scale, 0.0,
                     RELEASE_HEIGHT_MM * scale])
    origin = strike if release_reference is None else np.asarray(release_reference, dtype=float)
    dscale = pitch.distance_scale if distance_scale is None else distance_scale
    release = origin + dscale * (hand - origin)
    g = np.array([0.0, 0.0, -units.GRAVITY])
    v0 = (strike - release - 0.5 * g * flight ** 2) / flight
    return release, v0, flight

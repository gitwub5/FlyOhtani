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
    note="D35. Thrown from the rubber, which costs speed: 689 mm/s, 35% of a "
         "Froude-scaled Kershaw fastball, launch +17.5 deg. D37 later cut "
         "swing-to-contact to 12.35 ms, so the eye rule now asks 270 Hz of "
         "this pitch rather than 460.",
)
"""The pitch every measurement in docs/records/ before 2026-09-24 was taken
with. D39 adds FAST and SLOW either side of it."""

FAST = Pitch(
    name="fast",
    flight_s=0.040,
    note="D39. 865 mm/s, launch +8.9 deg -- the FLATTEST pitch this fly can "
         "be thrown, and it only exists because D37 cut swing-to-contact to "
         "12.35 ms. Under the old 24.60 a 40 ms flight left 5.4 ms to decide "
         "in and would have needed a 1,481 Hz eye. The eye rule asks 453 and "
         "runs at 480.",
)

SLOW = Pitch(
    name="slow",
    flight_s=0.060,
    note="D39. 623 mm/s, launch +23.9 deg. The SLOWEST pitch still inside the "
         "+25 deg limit -- past it gravity turns the delivery into a lob "
         "(+32 at 70 ms) and it stops being a pitch. Needs 212 Hz of eye.",
)

ARSENAL: dict[str, Pitch] = {p.name: p for p in (FAST, STANDARD, SLOW)}
"""구종 3종 (D39). **비행 시간만 다르고 휘지는 않는다** — 공에 스핀도 항력도
없으므로 커브라고 이름 붙일 수는 없다(아래 참고).

왜 하나가 아니라 셋인가. 비행 시간이 고정이면 **"첫 움직임을 보고 고정 시간
기다리기"가 이 과제의 정확한 해답**이고, 실제로 회로가 그렇게 행동했다
(프레임 3에 발화 + 학습된 대기 29 ms). 즉 루밍 계산이 전혀 필요 없는 과제였다.
연결 프레임 대역을 재보면 세 구종이 **12~14 / 18~20 / 22~23**으로 서로 겹치지
않으므로, 어떤 고정 대기도 셋을 다 맞힐 수 없다. 팽창 속도를 읽어야 풀린다 —
그것이 LC4/LPLC2가 실제로 하는 계산이다.

선택 규칙은 측정 전에 고정했다: 눈 프레임률 요구 ≤ 480 Hz, 발사각 ≤ +25°
(D32가 +20.8°를 "커브 같다"고 되돌렸다), 연결 대역이 서로 겹치지 않을 것,
3종 이상. 44 ms도 앞의 둘은 통과하지만 40 ms와 프레임 14에서 겹쳐 빠졌다.

**휘는 공은 아직 안 된다.** 공에 항력도 스핀도 없어서
(`flyohtani.world.swing.batted_ball`의 포물선이 정확한 이유가 그것이다) 커브·
슬라이더는 마그누스 힘을 모델에 먼저 넣어야 한다. 그 전에는 "커브"라고 이름만
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

"""Eye image in, swing or not out -- the whole path, wired together.

    BatObservation.eye_left
        -> brain.retina        ON/OFF temporal contrast
        -> receptive fields    pooled per LC4 / LPLC2 cell
        -> brain.circuit       LIF over the MaleCNS subgraph
        -> here                descending spikes -> swing

The last arrow is the motor decoding PLAN calls "the most arbitrary part",
and it is: `DN_SPIKES_TO_SWING` descending spikes inside `DECODE_WINDOW_S`
and the fly swings. Nothing in the connectome says a spike means swing. It is
stated here, in one place, with a number that learning is expected to move.

There is no learning yet. `CircuitPolicy` runs the circuit as wired and
`FixedFramePolicy` swings on a stopwatch; the second one is the baseline the
first has to beat, and it cheats -- it cannot see.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from flyohtani.brain.circuit import LoomingCircuit
from flyohtani.brain.connectome import SOURCE_TYPES
from flyohtani.brain.retina import Retina, build_receptive_fields
from flyohtani.task.env import Action
from flyohtani.task.observation import BatObservation

DN_SPIKES_TO_SWING = 1
DECODE_WINDOW_S = 0.004
"""ENGINEERING MAPPING (PLAN Phase 4). One descending spike within 4 ms
commits the swing. Chosen, not derived: a giant-fibre spike does commit a
fly to an escape, which is the nearest real thing, but a fly's escape is not
a bat swing and nothing here is calibrated against a recording."""

MOTOR_DELAY_FRAMES = 0
"""Frames between the descending spike that commits the swing and the joints
starting to move. Zero by default -- a delay this policy does not need to
invent. It exists because a real motor pathway has one (conduction, muscle
activation), and because the measured offset between this circuit's trigger
and the connecting frame is a constant: exactly the kind of parameter
learning should be left to find rather than handed the answer to."""

CIRCUIT_SUBSTEPS = 2
"""LIF steps per eye frame -- about 1 ms each at 480 Hz, which is the
timestep PLAN Phase 4 asks for."""


@dataclass
class CircuitPolicy:
    """The real thing: sees only what the fly sees.

    Two decisions come out of it. WHEN, from the descending spikes. WHERE,
    from which LC cells were firing when it committed -- their receptive
    fields are spread over the image, so the cells that answer to a high
    pitch sit high in it. `zone_boundaries` splits that centre of mass into
    the three strike zones, and those two numbers are the first thing
    learning has to find: nothing about the anatomy says where a zone ends."""

    circuit: LoomingCircuit = field(default_factory=LoomingCircuit)
    resolution: int = 32
    spikes_to_swing: int = DN_SPIKES_TO_SWING
    window_s: float = DECODE_WINDOW_S
    motor_delay_frames: int = MOTOR_DELAY_FRAMES
    zone_rise_boundary: float = -0.09
    """Rows per frame separating a high pitch from a low one.

    The zone is read from how fast the ball CLIMBS the image, not from where
    it is. Position turned out to carry the clock as much as the zone: the
    ball rises from row 17 to row 11 over a flight, which swamps the ~1 px
    the zones differ by, and a readout taken whenever the circuit happened to
    commit scored at chance (31%). The climb rate does not drift that way --
    measured, -0.17 rows/frame for a high pitch against +0.01 for a low one.

    Two zones, not three: the middle zone is not separable from the low one
    by this eye (d = 0.46), and pretending otherwise would be reading noise.
    That is a limit of the 0.62 deg pixel against zones 0.80 mm apart, and it
    is written down rather than tuned away."""

    zone_window_frames: int = 5
    """Frames the climb rate is fitted over."""
    frame_rate_hz: float = 480.0

    def __post_init__(self) -> None:
        self.retina = Retina(self.resolution)
        self._fields = {t: build_receptive_fields(len(self.circuit.graph.ids_of_type(t)),
                                                  self.resolution)
                        for t in SOURCE_TYPES}
        self._recent: deque[int] = deque()
        self._committed_at: int | None = None
        self._frame = 0
        self._centres = {t: self._fields[t].centres for t in SOURCE_TYPES}
        self._zone: str = "middle"
        self._rows: deque[float] = deque(maxlen=self.zone_window_frames)
        self.zone_evidence_at_commit: float | None = None
        """What `_read_zone` saw, kept for calibration. Read at the moment of
        commitment, which is NOT the end of the episode -- calibrating against
        the end value put the boundaries in the wrong place and the zone
        readout at chance."""
        self.trace: list[dict] = []

    def reset(self) -> None:
        self.retina.reset()
        self.circuit.reset()
        self._recent.clear()
        self._committed_at = None
        self._frame = 0
        self._zone = "middle"
        self._rows.clear()
        self.zone_evidence_at_commit = None
        self.trace.clear()

    def __call__(self, obs: BatObservation) -> Action:
        on, off = self.retina.encode(obs.eye_left)
        motion = on + off
        pooled = {t: self._fields[t].pool(motion) for t in SOURCE_TYPES}
        self._accumulate_zone_evidence(motion)
        drive = self.circuit.retinal_drive(pooled)
        dt = 1.0 / (self.frame_rate_hz * CIRCUIT_SUBSTEPS)
        spikes = np.zeros(self.circuit.n, dtype=bool)
        for _ in range(CIRCUIT_SUBSTEPS):
            spikes |= self.circuit.step(dt, drive)
        dn = int(self.circuit.target_spikes(spikes).sum())

        now = self.circuit.state.time_s
        for _ in range(dn):
            self._recent.append(now)
        while self._recent and now - self._recent[0] > self.window_s:
            self._recent.popleft()

        if self._committed_at is None and len(self._recent) >= self.spikes_to_swing:
            self._committed_at = self._frame
            self._zone = self._read_zone()
            self.zone_evidence_at_commit = self._zone_evidence()
        swing = (self._committed_at is not None
                 and self._frame >= self._committed_at + self.motor_delay_frames)
        self._frame += 1
        self.trace.append({
            "t_s": now,
            "lc_spikes": int(spikes[self.circuit.source_slice].sum()),
            "dn_spikes": dn,
            "dn_v_max": float(self.circuit.state.v[self.circuit.target_slice].max()),
            "swing": swing,
            "zone": self._zone,
        })
        return Action(swing=swing, zone=self._zone)

    def _accumulate_zone_evidence(self, motion: np.ndarray) -> None:
        """Remember where the moving thing was, for the last few frames."""
        total = float(motion.sum())
        if total <= 0:
            return
        rows = np.arange(motion.shape[0], dtype=float)[:, None]
        self._rows.append(float((rows * motion).sum() / total))

    def _zone_evidence(self) -> float | None:
        """Rows per frame the ball is climbing: negative is rising."""
        if len(self._rows) < 3:
            return None
        y = np.asarray(self._rows)
        x = np.arange(len(y), dtype=float)
        return float(np.polyfit(x, y, 1)[0])

    def _read_zone(self) -> str:
        rise = self._zone_evidence()
        if rise is None:
            return "middle"
        return "high" if rise < self.zone_rise_boundary else "low"


@dataclass
class FixedFramePolicy:
    """Swings on frame `frame`, having seen nothing. The baseline -- and the
    thing G3 exists to catch: if a seeing policy cannot beat it across
    varying pitches, the seeing is decorative."""

    frame: int
    _i: int = 0

    def reset(self) -> None:
        self._i = 0

    def __call__(self, obs: BatObservation) -> Action:
        swing = self._i == self.frame
        self._i += 1
        return Action(swing=swing)


def run_episode(env, policy, pitch=None):
    """One episode under a policy. Returns the env's outcome."""
    obs = env.reset(pitch)
    policy.reset()
    done = False
    while not done:
        obs, _, done, _ = env.step(policy(obs))
    return env.outcome

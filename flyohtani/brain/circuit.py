"""The looming circuit, simulated: LC4 and LPLC2 -> six descending neurons.

The wiring is real (MaleCNS v1.0, `connectome.py`). Everything that turns
that wiring into a running network is a modelling assumption, and this
module is where those assumptions live so they can be found and argued with:

  synapse count -> weight   w_ij = SYNAPSE_GAIN * C_ij. Linear, with one
                            free scale. The release gives contact counts,
                            not conductances, and nothing in the data fixes
                            the constant.
  sign                      every connection here is EXCITATORY. MaleCNS
                            does not ship neurotransmitter calls for these
                            cells in the file we vendored, and guessing
                            per-cell signs would be inventing data. LC4 and
                            LPLC2 are cholinergic in the literature, which
                            is why excitatory is the least-bad default -- but
                            it IS a default.
  neuron model              leaky integrate-and-fire, one compartment, a
                            fixed threshold and an absolute refractory
                            period. Real DNs are not this.

None of these are tuned to make the fly hit anything. The only calibration
performed is a dynamic-range one, documented at SYNAPSE_GAIN.

The controls PLAN asks for live here too: `shuffled()` rewires the same
degree sequence at random, and a frozen circuit is simply one that never
learns. A result that survives neither is not a result about the connectome.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from flyohtani.brain.connectome import (
    SOURCE_TYPES,
    TARGET_TYPES,
    LoomingSubgraph,
    load_looming_subgraph,
)

TAU_M_S = 0.020
"""Membrane time constant. Fly central neurons sit in the 10-30 ms range;
20 ms is the middle of it and is not fitted to this task."""

V_THRESHOLD = 1.0
V_RESET = 0.0
REFRACTORY_S = 0.002
"""Dimensionless membrane units: threshold at 1 means "one unit of charge
above rest fires". Putting it in millivolts would imply a calibration
against real recordings that has not been done."""

SYNAPSE_GAIN = 1.0 / 400.0
"""Membrane units per synapse per presynaptic spike.

CALIBRATED, for dynamic range only: the strongest pathway in the subgraph is
LC4 -> DNp04 at 11,597 synapses spread over 126 cells, so a DN sees on the
order of a few hundred synapses from any one LC cell. At this gain a DN needs
roughly 400 synapses' worth of coincident input to reach threshold -- i.e.
several LC cells firing together, not one. It was NOT chosen by looking at
whether the fly connects with the ball."""

INPUT_GAIN = 13_500.0
"""Membrane units per unit of pooled retinal contrast per second.

CALIBRATED against the measured retina, not guessed: over a pitch's decision
window the strongest pooled contrast runs about 0.010 early and 0.018 late,
so this gain brings a cell to threshold in two frames at the late value.
Note what that ratio says -- within the window the signal barely doubles,
because the ball is still sub-pixel. The big growth (10x and up) happens
AFTER the swing has to start, which is a fact about the task, not about the
gain."""


@dataclass
class CircuitState:
    v: np.ndarray
    refractory_until_s: np.ndarray
    time_s: float = 0.0


@dataclass
class LoomingCircuit:
    """A runnable version of the subgraph.

    Neurons are ordered: all source cells (LC4 then LPLC2) first, then the
    descending neurons. `source_slice` and `target_slice` index them.
    """

    graph: LoomingSubgraph = field(default_factory=load_looming_subgraph)
    synapse_gain: float = SYNAPSE_GAIN
    input_gain: float = INPUT_GAIN
    tau_m_s: float = TAU_M_S

    def __post_init__(self) -> None:
        source_ids = [int(b) for t in SOURCE_TYPES for b in self.graph.ids_of_type(t)]
        target_ids = [int(b) for t in TARGET_TYPES for b in self.graph.ids_of_type(t)]
        self.body_ids = np.array(source_ids + target_ids, dtype=np.int64)
        self.index = {int(b): i for i, b in enumerate(self.body_ids)}
        self.n = len(self.body_ids)
        self.source_slice = slice(0, len(source_ids))
        self.target_slice = slice(len(source_ids), self.n)
        self.type_of = np.array([self.graph.node_type[int(b)] for b in self.body_ids])

        w = np.zeros((self.n, self.n))
        for pre, post, count in zip(self.graph.body_pre, self.graph.body_post,
                                    self.graph.weight, strict=True):
            i, j = self.index.get(int(pre)), self.index.get(int(post))
            if i is not None and j is not None:
                w[j, i] += float(count) * self.synapse_gain
        self.weights = w
        self.state = self.new_state()

    # ---------------------------------------------------------------- state

    def new_state(self) -> CircuitState:
        return CircuitState(v=np.zeros(self.n), refractory_until_s=np.full(self.n, -np.inf))

    def reset(self) -> None:
        self.state = self.new_state()

    # ----------------------------------------------------------------- step

    def step(self, dt_s: float, drive: np.ndarray) -> np.ndarray:
        """Advance by `dt_s` with `drive` (membrane units per second) applied
        to every neuron. Returns a boolean spike vector."""
        if drive.shape != (self.n,):
            raise ValueError(f"drive must be one value per neuron ({self.n})")
        s = self.state
        s.time_s += dt_s
        awake = s.time_s >= s.refractory_until_s
        s.v += np.where(awake, (-s.v / self.tau_m_s + drive) * dt_s, 0.0)
        spikes = s.v >= V_THRESHOLD
        if spikes.any():
            s.v[spikes] = V_RESET
            s.refractory_until_s[spikes] = s.time_s + REFRACTORY_S
            # Synaptic input lands on the next step, which is what a delay of
            # one timestep means here; no axonal delays are modelled.
            s.v += self.weights @ spikes.astype(float)
        return spikes

    def retinal_drive(self, pooled: dict[str, np.ndarray]) -> np.ndarray:
        """Turn per-type pooled contrast into a drive vector. Descending
        neurons get no direct visual input -- they hear from the LC cells."""
        drive = np.zeros(self.n)
        start = 0
        for t in SOURCE_TYPES:
            n_t = len(self.graph.ids_of_type(t))
            values = pooled[t]
            if values.shape != (n_t,):
                raise ValueError(f"{t}: expected {n_t} pooled values, got {values.shape}")
            drive[start:start + n_t] = values * self.input_gain
            start += n_t
        return drive

    def target_spikes(self, spikes: np.ndarray) -> np.ndarray:
        return spikes[self.target_slice]


def shuffled(graph: LoomingSubgraph | None = None, seed: int = 0) -> LoomingSubgraph:
    """The control PLAN asks for: same cells, same number of connections,
    same synapse counts, wiring drawn at random. If a result survives this,
    it was not about the connectome's structure."""
    graph = graph or load_looming_subgraph()
    rng = np.random.default_rng(seed)
    pre = graph.body_pre.copy()
    post = rng.permutation(graph.body_post)
    return LoomingSubgraph(
        body_pre=pre, body_post=post, weight=graph.weight.copy(),
        node_type=dict(graph.node_type), node_soma_side=dict(graph.node_soma_side),
        provenance={**graph.provenance,
                    "derived": f"SHUFFLED CONTROL (seed {seed}) -- not the real wiring"},
    )

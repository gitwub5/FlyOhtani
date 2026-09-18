"""The retina, the circuit and the decode -- the parts, not the result.

What the circuit achieves on the task is a measurement and lives in
docs/records/. These tests hold the machinery: that the encoding is a
temporal contrast, that the wiring loaded is the wiring simulated, that a
neuron does what a leaky integrator does, and that the shuffled control is
actually a control.
"""
from __future__ import annotations

import numpy as np
import pytest

from flyohtani.brain import circuit as C
from flyohtani.brain.connectome import SOURCE_TYPES, TARGET_TYPES, load_looming_subgraph
from flyohtani.brain.retina import EPS, Retina, build_receptive_fields


class TestRetina:
    def test_the_first_frame_has_no_motion(self):
        r = Retina(8)
        on, off = r.encode(np.full((8, 8), 100, np.uint8))
        assert not on.any() and not off.any()

    def test_brightening_is_on_and_darkening_is_off(self):
        r = Retina(4)
        r.encode(np.full((4, 4), 100, np.uint8))
        on, off = r.encode(np.full((4, 4), 150, np.uint8))
        assert on.min() > 0 and not off.any()
        on2, off2 = r.encode(np.full((4, 4), 100, np.uint8))
        assert off2.min() > 0 and not on2.any()

    def test_contrast_is_weber_like_with_a_floor(self):
        r = Retina(2)
        r.encode(np.zeros((2, 2), np.uint8))
        on, _ = r.encode(np.full((2, 2), 1, np.uint8))
        assert on[0, 0] == pytest.approx(1.0 / EPS, rel=1e-5)

    def test_a_still_scene_produces_nothing(self):
        r = Retina(6)
        frame = np.random.default_rng(0).integers(0, 255, (6, 6), dtype=np.uint8)
        r.encode(frame)
        on, off = r.encode(frame)
        assert not on.any() and not off.any()


class TestReceptiveFields:
    def test_each_field_is_a_normalised_weighting(self):
        rf = build_receptive_fields(9, 12)
        assert rf.weights.shape == (9, 144)
        assert rf.weights.sum(axis=1) == pytest.approx(np.ones(9))
        assert (rf.weights >= 0).all()

    def test_fields_are_spread_over_the_image(self):
        rf = build_receptive_fields(16, 32)
        assert rf.centres[:, 0].min() < 8 and rf.centres[:, 0].max() > 24

    def test_a_cell_responds_most_to_its_own_patch(self):
        rf = build_receptive_fields(16, 32)
        image = np.zeros((32, 32))
        cy, cx = rf.centres[5]
        image[int(cy), int(cx)] = 1.0
        assert int(np.argmax(rf.pool(image))) == 5

    def test_no_cells_is_an_error(self):
        with pytest.raises(ValueError):
            build_receptive_fields(0, 32)


@pytest.fixture(scope="module")
def net() -> C.LoomingCircuit:
    return C.LoomingCircuit()


class TestCircuit:
    def test_it_simulates_the_wiring_it_loaded(self, net):
        graph = load_looming_subgraph()
        assert net.n == len({*graph.body_pre.tolist(), *graph.body_post.tolist()})
        total = sum(float(w) for w in graph.weight) * C.SYNAPSE_GAIN
        assert net.weights.sum() == pytest.approx(total, rel=1e-9)

    def test_sources_come_first_then_the_descending_neurons(self, net):
        assert set(net.type_of[net.source_slice]) == set(SOURCE_TYPES)
        assert set(net.type_of[net.target_slice]) == set(TARGET_TYPES)

    def test_descending_neurons_get_no_direct_visual_input(self, net):
        pooled = {t: np.ones(len(net.graph.ids_of_type(t))) for t in SOURCE_TYPES}
        drive = net.retinal_drive(pooled)
        assert (drive[net.target_slice] == 0).all()
        assert (drive[net.source_slice] > 0).all()

    def test_a_neuron_leaks_toward_rest(self, net):
        net.reset()
        net.state.v[:] = 1.0 - 1e-9  # just under threshold
        net.step(0.001, np.zeros(net.n))
        assert (net.state.v < 1.0 - 1e-9).all()

    def test_enough_drive_makes_a_spike_and_then_a_refractory_pause(self, net):
        net.reset()
        drive = np.zeros(net.n)
        drive[0] = 10_000.0
        assert net.step(0.001, drive)[0]
        assert net.state.v[0] >= 0.0
        spiked_again = any(net.step(0.0005, drive)[0] for _ in range(3))
        assert not spiked_again, "fired inside its refractory period"

    def test_drive_of_the_wrong_shape_is_refused(self, net):
        with pytest.raises(ValueError):
            net.step(0.001, np.zeros(net.n - 1))


class TestShuffledControl:
    def test_it_keeps_the_cells_and_the_synapses_and_moves_only_the_wiring(self):
        real = load_looming_subgraph()
        fake = C.shuffled(real, seed=3)
        assert fake.n_edges == real.n_edges
        assert sorted(fake.weight.tolist()) == sorted(real.weight.tolist())
        assert fake.node_type == real.node_type
        assert not np.array_equal(fake.body_post, real.body_post)

    def test_it_says_in_its_own_provenance_that_it_is_not_the_real_wiring(self):
        assert "SHUFFLED" in C.shuffled(seed=1).provenance["derived"]

    def test_the_total_drive_is_preserved_so_it_is_a_fair_control(self):
        real = C.LoomingCircuit()
        fake = C.LoomingCircuit(graph=C.shuffled(seed=1))
        assert fake.weights.sum() == pytest.approx(real.weights.sum(), rel=1e-9)

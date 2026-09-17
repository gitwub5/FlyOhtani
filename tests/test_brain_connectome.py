"""G4 regression tests: the vendored looming subgraph is real MaleCNS data,
loads without the 1 GB release, and carries its own licence trail.

These assert against the released data, so a failure means either the
vendored file was regenerated from a different selection or someone edited
it by hand. Neither should happen silently.
"""
from __future__ import annotations

import numpy as np
import pytest

from flyohtani.brain.connectome import (
    SOURCE_TYPES,
    TARGET_TYPES,
    load_looming_subgraph,
)


@pytest.fixture(scope="module")
def graph():
    return load_looming_subgraph()


class TestProvenanceTravelsWithTheData:
    def test_licence_and_version_are_recorded_in_the_file_itself(self, graph):
        """A CC-BY derivative keeps its licence. If the attribution lived
        only in a doc, copying the file would strip it."""
        prov = graph.provenance
        assert prov["dataset"] == "MaleCNS"
        assert prov["version"] == "v1.0"
        assert prov["license"] == "CC-BY"
        assert "janelia" in prov["downloads"].lower()

    def test_source_file_checksums_are_recorded(self, graph):
        files = graph.provenance["source_files"]
        assert len(files) == 2
        for entry in files.values():
            assert len(entry["sha256"]) == 64
            assert entry["bytes"] > 0

    def test_weights_are_labelled_as_raw_synapse_counts(self, graph):
        """The moment this says anything else, some modelling assumption has
        been baked into the data file instead of the model."""
        assert "synapse count" in graph.provenance["weight_meaning"]
        assert graph.weight.dtype == np.int64
        assert graph.weight.min() > 0

    def test_selection_rule_records_that_nothing_was_filtered(self, graph):
        rule = graph.provenance["selection"]["rule"]
        assert "no threshold" in rule
        assert "no reweighting" in rule


class TestCircuitIsTheOneD19Names:
    def test_only_the_declared_types_are_present(self, graph):
        types = set(graph.node_type.values())
        assert types == set(SOURCE_TYPES) | set(TARGET_TYPES)

    def test_source_population_sizes_match_the_release(self, graph):
        """LC4 n=126, LPLC2 n=185 in the MaleCNS v1.0 annotation table."""
        assert len(graph.ids_of_type("LC4")) == 126
        assert len(graph.ids_of_type("LPLC2")) == 185

    def test_every_edge_runs_from_a_source_type_to_a_target_type(self, graph):
        for pre, post in zip(graph.body_pre, graph.body_post, strict=True):
            assert graph.node_type[int(pre)] in SOURCE_TYPES
            assert graph.node_type[int(post)] in TARGET_TYPES

    def test_the_giant_fiber_is_present_and_is_a_pair(self, graph):
        """DNp01 is the Giant Fiber, one per hemisphere."""
        gf = graph.ids_of_type("DNp01")
        assert len(gf) == 2
        assert {graph.node_soma_side[int(b)] for b in gf} == {"L", "R"}

    def test_both_source_populations_reach_the_giant_fiber(self, graph):
        """The LPLC2 -> Giant Fiber connection is the canonical looming
        escape pathway; LC4 -> GF is the other documented arm. If either
        vanishes, the extraction selected the wrong thing."""
        gf = {int(b) for b in graph.ids_of_type("DNp01")}
        for source in SOURCE_TYPES:
            ids = {int(b) for b in graph.ids_of_type(source)}
            reaching = {
                int(w)
                for pre, post, w in zip(graph.body_pre, graph.body_post, graph.weight, strict=True)
                if int(pre) in ids and int(post) in gf
            }
            assert reaching, source


class TestShape:
    def test_subgraph_is_small_enough_to_simulate_directly(self, graph):
        """~300 neurons is the whole point of starting here: it fits in NumPy
        without any reduction step that would need justifying."""
        assert len(graph.source_ids) == 311
        assert len(graph.target_ids) == len(TARGET_TYPES) * 2
        assert graph.n_edges == 1343

    def test_adjacency_preserves_every_synapse(self, graph):
        matrix, rows, cols = graph.adjacency()
        assert matrix.shape == (len(rows), len(cols))
        assert matrix.sum() == graph.weight.sum()

    def test_adjacency_row_and_column_order_is_deterministic(self, graph):
        _, rows_a, cols_a = graph.adjacency()
        _, rows_b, cols_b = graph.adjacency()
        assert np.array_equal(rows_a, rows_b)
        assert np.array_equal(cols_a, cols_b)
        assert np.array_equal(rows_a, np.sort(rows_a))

    def test_edge_arrays_stay_the_same_length(self, graph):
        assert len(graph.body_pre) == len(graph.body_post) == len(graph.weight)

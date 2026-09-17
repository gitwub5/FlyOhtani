"""Replay export for the brain viewer (viewer/, D30).

The Python validator mirrors the viewer's own parser; the node test runs the
viewer's actual parseReplay so the two cannot drift apart unnoticed.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from flyohtani.brain import replay as R
from flyohtani.brain.connectome import SOURCE_TYPES, TARGET_TYPES, load_looming_subgraph

REPO = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@pytest.fixture(scope="module")
def atlas():
    return R.load_viewer_atlas()


@pytest.fixture(scope="module")
def visible(atlas):
    return R.visible_ids(atlas)


@pytest.fixture(scope="module")
def wiring():
    return R.wiring_replay()


class TestAtlasCoverage:
    def test_atlas_is_built_from_the_same_annotation_file_we_use(self, atlas):
        graph = load_looming_subgraph()
        ours = graph.provenance["source_files"]["body-annotations.feather"]["sha256"]
        assert atlas["manifest"]["sourceSha256"] == ours

    def test_every_circuit_neuron_is_a_visible_atlas_body(self, visible):
        graph = load_looming_subgraph()
        assert set(graph.node_type) <= visible
        assert len(graph.node_type) == 323

    def test_circuit_neurons_sit_in_the_right_atlas_groups(self, atlas):
        graph = load_looming_subgraph()
        group_of = dict(zip(atlas["ids"].tolist(), atlas["groups"].tolist(), strict=True))
        for body, cell_type in graph.node_type.items():
            expected = 0 if cell_type in SOURCE_TYPES else 2  # optic / descending
            assert group_of[body] == expected, (body, cell_type)


class TestWiringReplay:
    def test_it_is_valid(self, wiring, visible):
        R.validate_replay(wiring, visible)

    def test_it_says_what_it_is(self, wiring):
        assert wiring["source"]["kind"] == "synthetic"
        assert "not activity" in wiring["source"]["name"].lower()
        assert "no firing rates" in wiring["source"]["normalization"].lower()

    def test_stages_light_the_declared_types_in_order(self, wiring):
        graph = load_looming_subgraph()
        types = [{graph.node_type[b] for b, _ in f["values"]} for f in wiring["frames"]]
        assert types[0] == set()
        assert types[1] == {"LC4"}
        assert types[2] == {"LPLC2"}
        assert types[3] == set(TARGET_TYPES)
        assert types[4] == set(SOURCE_TYPES) | set(TARGET_TYPES)
        assert wiring["frames"][-1]["values"] == wiring["frames"][-2]["values"]

    def test_every_lit_cell_is_visible_and_brightness_tracks_synapses(self, wiring):
        values = dict(map(tuple, wiring["frames"][4]["values"]))
        assert min(values.values()) >= R.WIRING_FLOOR
        assert max(values.values()) == 1.0
        assert len(values) == 323


class TestValidatorRejects:
    @pytest.mark.parametrize("mutate, message", [
        (lambda r: r.update(version=2), "version"),
        (lambda r: r["source"].update(kind="simulated"), "source"),
        (lambda r: r["source"].update(normalization=" "), "source"),
        (lambda r: r["frames"].__setitem__(1, {**r["frames"][1], "time": 0.0}), "increasing"),
        (lambda r: r["frames"][1]["values"].append([1, 0.5]), "visible"),
        (lambda r: r["frames"][1]["values"].append(list(r["frames"][1]["values"][0])), "duplicate"),
        (lambda r: r["frames"][1]["values"][0].__setitem__(1, 1.5), "within"),
        (lambda r: r.update(frames=r["frames"][:1]), "frames"),
    ])
    def test_malformed_replays(self, wiring, visible, mutate, message):
        bad = copy.deepcopy(wiring)
        mutate(bad)
        with pytest.raises(ValueError, match=message):
            R.validate_replay(bad, visible)


def test_activity_replay_uses_the_viewers_rate_convention(visible):
    body = next(iter(load_looming_subgraph().node_type))
    rep = R.activity_replay([0.0, 0.1], [{body: 25.0}, {body: 80.0}], kind="predicted", name="test")
    R.validate_replay(rep, visible)
    assert rep["frames"][0]["values"] == [[body, 0.5]]
    assert rep["frames"][1]["values"] == [[body, 1.0]]  # clamped


@pytest.mark.skipif(NODE is None, reason="node not installed")
class TestViewerAcceptsIt:
    def _parse(self, path: Path) -> subprocess.CompletedProcess:
        return subprocess.run([NODE, "--experimental-strip-types", "tests/viewer/parse_replay.mjs", str(path)],
                              cwd=REPO, capture_output=True, text=True, timeout=60, check=False)

    def test_the_viewers_own_parser_accepts_the_wiring_replay(self, tmp_path, wiring):
        path = tmp_path / "wiring.json"
        path.write_text(json.dumps(wiring))
        done = self._parse(path)
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout.strip().splitlines()[-1]) == {"ok": True, "frames": 6, "kind": "synthetic"}

    def test_the_viewers_own_parser_rejects_an_unknown_body(self, tmp_path, wiring):
        bad = copy.deepcopy(wiring)
        bad["frames"][1]["values"].append([1, 0.5])
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad))
        assert self._parse(path).returncode != 0


def test_export_bundle_writes_what_the_viewer_reads(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (run / "manifest.json").write_text(json.dumps({"scenario": "pitch", "scripted": True,
                                                   "outcome": {"contact": True}, "git_commit": "abc"}))
    out = tmp_path / "bundle"
    exp = R.export_bundle(run, out)
    assert {p.name for p in out.iterdir()} == {"video.mp4", "circuit.replay.json", "experiment.json"}
    assert exp["video_and_brain_are_linked"] is False
    assert exp["replay"]["kind"] == "synthetic"

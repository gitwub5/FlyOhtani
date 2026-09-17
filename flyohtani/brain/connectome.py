"""G4 / Phase 4 (docs/PLAN.md, D19): the real looming-detection subgraph,
extracted from MaleCNS v1.0.

Two things live here, deliberately separated:

  * `load_looming_subgraph()` reads the SMALL derived file vendored in this
    repo. It needs no network and no 1 GB download, and it is what the rest
    of the project imports.

  * `extract_looming_subgraph()` regenerates that file from the full MaleCNS
    release. It needs the 1.05 GB connectome-weights feather and pandas /
    pyarrow, neither of which is a dependency of this project. Run it only
    when the circuit definition changes.

The data is CC-BY. Attribution and the exact source files, versions and
SHA-256s are in docs/RESEARCH_SOURCES.md and in the derived file's own
`provenance` block -- a derived subset keeps the original licence, so that
block travels with the data rather than living only in a doc.

WHAT THIS IS NOT: a model. It is a wiring diagram -- body IDs, cell types
and synapse counts. Turning synapse counts into synaptic weights is a
modelling assumption that belongs in the module that makes it, not here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SUBGRAPH_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "connectome" / "looming-subgraph-male-cns-v1.0.json"
)

SOURCE_TYPES: tuple[str, ...] = ("LC4", "LPLC2")
"""Visual projection neurons that respond to looming. Both are real MaleCNS
`type` values (verified against the annotation table, not assumed from the
literature): LC4 n=126, LPLC2 n=185."""

TARGET_TYPES: tuple[str, ...] = ("DNp01", "DNp02", "DNp03", "DNp04", "DNp06", "DNp11")
"""Descending neurons carrying the signal out of the brain. DNp01 is the
Giant Fiber; the annotation table labels it `DNp01(GF)_R` / `_L`."""


@dataclass(frozen=True)
class LoomingSubgraph:
    """A wiring diagram, not a network. `weight` is the SYNAPSE COUNT between
    two bodies as released; it has not been rescaled, thresholded or turned
    into anything with units."""

    body_pre: np.ndarray
    body_post: np.ndarray
    weight: np.ndarray
    node_type: dict[int, str]
    node_soma_side: dict[int, str]
    provenance: dict

    def __post_init__(self) -> None:
        n = len(self.body_pre)
        if not (len(self.body_post) == len(self.weight) == n):
            raise ValueError("edge arrays must be the same length")

    @property
    def n_edges(self) -> int:
        return len(self.body_pre)

    @property
    def source_ids(self) -> np.ndarray:
        return np.unique(self.body_pre)

    @property
    def target_ids(self) -> np.ndarray:
        return np.unique(self.body_post)

    def ids_of_type(self, cell_type: str) -> np.ndarray:
        return np.array(sorted(b for b, t in self.node_type.items() if t == cell_type), dtype=np.int64)

    def adjacency(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Dense synapse-count matrix plus the row/column body IDs, in sorted
        ID order so the layout is reproducible across runs."""
        rows = self.source_ids
        cols = self.target_ids
        row_of = {b: i for i, b in enumerate(rows)}
        col_of = {b: i for i, b in enumerate(cols)}
        matrix = np.zeros((len(rows), len(cols)), dtype=np.int64)
        for pre, post, w in zip(self.body_pre, self.body_post, self.weight, strict=True):
            matrix[row_of[int(pre)], col_of[int(post)]] += int(w)
        return matrix, rows, cols


def load_looming_subgraph(path: Path | None = None) -> LoomingSubgraph:
    payload = json.loads((path or SUBGRAPH_PATH).read_text())
    edges = payload["edges"]
    nodes = payload["nodes"]
    return LoomingSubgraph(
        body_pre=np.asarray(edges["body_pre"], dtype=np.int64),
        body_post=np.asarray(edges["body_post"], dtype=np.int64),
        weight=np.asarray(edges["weight"], dtype=np.int64),
        node_type={int(k): v for k, v in nodes["type"].items()},
        node_soma_side={int(k): v for k, v in nodes["soma_side"].items()},
        provenance=payload["provenance"],
    )


def extract_looming_subgraph(annotations: Path, weights: Path, out: Path) -> dict:
    """Regenerates the vendored file from the full MaleCNS release.

    Requires pandas and pyarrow (not project dependencies) and the two
    release files named in docs/RESEARCH_SOURCES.md. Imports are local so
    that merely importing this module never needs them.
    """
    import hashlib

    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc
    from pyarrow import feather

    def sha256(p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    ann = pd.read_feather(annotations, columns=["bodyId", "type", "superclass", "somaSide"])
    pre_ids = ann.loc[ann["type"].isin(SOURCE_TYPES), "bodyId"].to_numpy()
    post_ids = set(ann.loc[ann["type"].isin(TARGET_TYPES), "bodyId"].tolist())

    table = feather.read_table(weights, memory_map=True)
    table = table.filter(pc.is_in(table.column("body_pre"), value_set=pa.array(pre_ids)))
    df = table.to_pandas()
    df = df[df["body_post"].isin(post_ids)].sort_values(["body_pre", "body_post"]).reset_index(drop=True)

    used = sorted(set(df["body_pre"]) | set(df["body_post"]))
    meta = ann[ann["bodyId"].isin(used)].set_index("bodyId")

    payload = {
        "provenance": {
            "dataset": "MaleCNS",
            "version": "v1.0",
            "license": "CC-BY",
            "commercial_use": "permitted with attribution",
            "collaboration": "FlyEM (HHMI Janelia), University of Cambridge (Dept. of Zoology), "
                             "MRC Laboratory of Molecular Biology, Google Research",
            "downloads": "https://male-cns.janelia.org/download/",
            "source_files": {
                annotations.name: {"sha256": sha256(annotations), "bytes": annotations.stat().st_size},
                weights.name: {"sha256": sha256(weights), "bytes": weights.stat().st_size},
            },
            "selection": {
                "source_types": list(SOURCE_TYPES),
                "target_types": list(TARGET_TYPES),
                "rule": "every released edge whose presynaptic body is of a source type "
                        "and whose postsynaptic body is of a target type; no threshold, "
                        "no reweighting, no deduplication",
            },
            "weight_meaning": "synapse count as released (minconf 0.5 build)",
        },
        "nodes": {
            "type": {str(b): str(meta.loc[b, "type"]) for b in used},
            "soma_side": {str(b): str(meta.loc[b, "somaSide"]) for b in used},
        },
        "edges": {
            "body_pre": [int(v) for v in df["body_pre"]],
            "body_post": [int(v) for v in df["body_post"]],
            "weight": [int(v) for v in df["weight"]],
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n")
    return payload["provenance"]

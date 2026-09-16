"""Shared STL-vertex utilities for I-08a-fix (docs/records/FLY-VISUAL-REVIEW.md):
the review's core finding was that geom ORIGIN (what scripts/build_fly_visual_asset.py
and envs/fly_visual.py previously measured) is not the same as the actual
mesh SURFACE (sole, fingertip) -- a geom's origin can sit well above/inside
the real lowest/outermost vertex. Every ground-contact and grip-reach
measurement in this fix reads real transformed mesh vertices, not geom
origins.

R-02 (docs/implementation/REFACTOR-PLAN.md): moved here from
scripts/fly_mesh_utils.py so it is part of the installed `envs` package
(pyproject.toml's `[tool.setuptools] packages`) instead of the unpackaged
`scripts/` CLI directory. That unpackaged location was the direct cause of
docs/records/evidence/R00-known-failures-at-checkpoint.md item 1: `pytest`
(the console-script entry point) does not add the current working directory
to sys.path, only `python -m pytest` does -- so
`from scripts.fly_mesh_utils import geom_world_vertices` (used by a ground-
contact test) resolved under one invocation and raised ModuleNotFoundError
under the other. Runtime/test code should never need to import a CLI
script's internals; this move fixes that at the source instead of adding a
sys.path workaround.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np


def read_stl_vertices(path: str | Path) -> np.ndarray:
    """Binary STL -> (N, 3) float64 array of (deduplicated-by-nothing, i.e.
    every triangle corner) vertex positions, in the file's own raw units."""
    path = Path(path)
    with path.open("rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        verts = np.empty((n * 3, 3), dtype=np.float64)
        for i in range(n):
            data = f.read(50)
            vals = struct.unpack("<12f", data[:48])
            verts[i * 3] = vals[3:6]
            verts[i * 3 + 1] = vals[6:9]
            verts[i * 3 + 2] = vals[9:12]
    return verts


def transform_points(points: np.ndarray, pos: np.ndarray, mat: np.ndarray) -> np.ndarray:
    """points (N,3) in a frame's local coords -> world coords, given that
    frame's world pos (3,) and 3x3 rotation matrix (row-major, MuJoCo
    convention: world = pos + mat @ local)."""
    return points @ mat.T + pos


def geom_world_vertices(model, data, geom_id: int, mesh_dir: Path) -> np.ndarray:
    """All (transformed-to-world) vertices of a mesh-type geom, using the
    mesh's OWN raw STL file (re-read directly, not MuJoCo's internal
    triangle buffer) scaled by the compiled <mesh scale>, then placed via
    that geom's actual compiled world pos/mat. This is independent of
    whatever placement bug we're trying to catch (it re-derives the mesh's
    true extent from source, not from any of our own prior computations)."""
    import mujoco

    mesh_id = model.geom_dataid[geom_id]
    mesh_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, mesh_id)
    scale = model.mesh_scale[mesh_id]
    # mesh_name is like "fly_mesh_Thorax" -> file stem "Thorax"
    stem = mesh_name.split("mesh_", 1)[-1]
    raw = read_stl_vertices(mesh_dir / f"{stem}.stl")
    scaled = raw * scale
    pos = data.geom_xpos[geom_id]
    mat = data.geom_xmat[geom_id].reshape(3, 3)
    return transform_points(scaled, pos, mat)

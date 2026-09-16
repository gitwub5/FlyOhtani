# Third-Party Notices

This file lists third-party assets vendored into this repository, separately
from this project's own code license.

## NeuroMechFly / flygym mesh assets

- **Files**: `envs/assets/mesh_neuromechfly/*.stl` (43 body-segment meshes)
- **Source**: [flygym](https://github.com/NeLy-EPFL/flygym) (NeuroMechFly v2),
  PyPI package `flygym==1.2.1`, by Sibo Wang-Chen et al. (NeLy lab, EPFL).
  See [neuromechfly.org](https://neuromechfly.org/).
- **License**: Apache License 2.0. Full text:
  `envs/assets/mesh_neuromechfly/LICENSE-flygym-apache-2.0.txt`.
- **What was taken**: only the specific mesh STL files listed in
  `docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json` (per-file SHA-256
  hashes included there), plus the license file. No other part of the
  `flygym` package (Python source, non-mesh assets, other MJCF variants) is
  vendored.
- **What was derived**: `envs/assets/fly_visual_assets.xml` and
  `fly_visual_body.xml` are generated from the package's bundled
  `neuromechfly_seqik_kinorder_ypr.xml` body/joint hierarchy by
  `scripts/build_fly_visual_asset.py` (rescaled, re-posed upright, pruned to
  a static visual-only rig -- see the manifest for the exact transform).
  `envs/assets/fly_visual_front_legs.xml` and `envs/fly_visual.py` are
  hand-written, using the package's mesh files and rest-pose segment lengths
  as reference data.
- **Use**: purely a visual (non-colliding, massless) overlay for the
  baseball batter character in `envs/assets/baseball_park_b1.xml` -- see
  `docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md` section C (I-08a) and
  `docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json` for the full
  provenance record, scaling/pose derivation, and explicit note that this
  is a research-model appearance used for an anthropomorphized character,
  not a claim about real fly behavior or anatomy.

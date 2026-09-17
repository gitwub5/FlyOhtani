# Third-Party Notices

Third-party assets vendored into this repository, separately from this
project's own code license (MIT).

## NeuroMechFly / flygym mesh assets

- **Files**: `flyohtani/assets/mesh_neuromechfly/*.stl` (45 body-segment
  meshes).
- **Source**: [flygym](https://github.com/NeLy-EPFL/flygym) (NeuroMechFly v2),
  PyPI package `flygym==1.2.1`, by Sibo Wang-Chen et al. (NeLy lab, EPFL).
  See [neuromechfly.org](https://neuromechfly.org/).
- **License**: Apache License 2.0. Full text:
  `flyohtani/assets/mesh_neuromechfly/LICENSE-flygym-apache-2.0.txt`.
- **What was taken**: only the STL files listed in
  `flyohtani/assets/mesh_neuromechfly/PROVENANCE.json` (per-file SHA-256
  hashes and the source wheel's own SHA-256 are recorded there), plus the
  license file. No other part of the `flygym` package -- Python source,
  non-mesh assets, other MJCF variants -- is vendored.
- **Use**: fly body geometry. In the v1 tree these meshes drove a massless,
  non-colliding visual overlay on an enlarged human-scale batter character;
  that rig has been removed (see below). Going forward they are the geometry
  of a real-scale, actually-jointed body (docs/PLAN.md, D22).
- **Facts cited, not vendored**: the raw MJCF's joint structure, DOF list,
  position-control defaults, and rest-pose angles were read from the same
  `flygym==1.2.1` package and are quoted as numbers in
  `flyohtani/units.py` and `docs/records/PRIOR-FINDINGS.md`. No additional
  files were copied for that.

### Note on PROVENANCE.json

That manifest was written for the v1 build and still describes derivations
that no longer exist in this tree -- the K=400 enlargement, the upright
re-posing, and the generated `fly_visual_*.xml` files. It is kept **as
written, unedited**, because it is the provenance record for the mesh files
themselves (counts, hashes, byte-identity check) and editing a provenance
record to match a later refactor would defeat its purpose. The build
scripts and generated XMLs it refers to are preserved at the git tag
`archive/human-scale-v0`.

## NeuroMechFly / flygym source MJCF

- **File**: `flyohtani/assets/mjcf_neuromechfly/neuromechfly_seqik_kinorder_ypr.xml`
- **Source**: the same `flygym==1.2.1` wheel as the meshes above
  (sha256 `5db9bb89b7f57e2fda8d716fd8205b0ba7ac9a46e7c194ea6e752e38964f390d`,
  verified again on re-download), path `flygym/data/mjcf/` inside it.
- **License**: Apache License 2.0 (same license file as the meshes).
- **Modification**: none. Copied byte-for-byte; sha256
  `413b3a1dcb7537d08122e16f256f27ec0d8bb9f52c58670345b6c24c9e72e05a`.
- **Use**: `flyohtani/body/minimal_body.py` reads it to build the foreleg,
  keeping the original joint axes, segment positions and masses. The built
  model is a derived work of an Apache-2.0 file.
- **Note**: this MJCF references Tarsus2-5 meshes that are deliberately NOT
  vendored, so it cannot be compiled as-is from this repo. The builder prunes
  those segments. See `mjcf_neuromechfly/PROVENANCE.json`.

## NeuroMechFly / flygym walking kinematics

- **File**: `flyohtani/assets/behavior_neuromechfly/walking-joint-angles-210902-pr-fly1.npz`
- **Source**: the same `flygym==1.2.1` wheel, path
  `flygym/data/behavior/210902_pr_fly1.pkl`. A 2 kHz recording of a tethered
  walking fly, 42 leg DOFs, 1 s.
- **License**: Apache License 2.0 (same license file as the meshes).
- **Modification**: converted from pickle to npz, losslessly (verified by
  exact array comparison) and with rows sorted by joint name. No value was
  changed. Converted rather than copied so that reading it does not require
  unpickling. Checksums of both the original pickle and the source wheel are
  in `behavior_neuromechfly/PROVENANCE.json`.
- **Use**: `flyohtani/body/limits.py` differentiates it to measure real
  joint angular velocities (docs/records/LIT-01-FLY-LEG-LIMITS.md).
- **Please cite**: Wang-Chen, S., Stimpfling, V. A., Lam, T. K. C., Ozdil,
  P. G., Genoud, L., Hurtak, F. & Ramdya, P. (2024). NeuroMechFly v2:
  simulating embodied sensorimotor control in adult *Drosophila*. *Nature
  Methods* 21(12), 2353-2362. https://doi.org/10.1038/s41592-024-02497-y

## MaleCNS connectome (derived subgraph)

- **File**: `flyohtani/assets/connectome/looming-subgraph-male-cns-v1.0.json`
- **Source**: MaleCNS v1.0, <https://male-cns.janelia.org/download/>, a
  collaboration between FlyEM (HHMI Janelia), the University of Cambridge
  (Dept. of Zoology), the MRC Laboratory of Molecular Biology, and Google
  Research.
- **License**: **CC-BY**. Commercial use is permitted with attribution. This
  is a DIFFERENT license from the Apache-2.0 code/mesh assets above, and a
  derived subset keeps it.
- **What was taken**: 1,343 of the release's 151,856,684 edges -- those from
  LC4 / LPLC2 to six descending-neuron types -- plus each involved body's
  type and soma side. No thresholding, reweighting or deduplication.
  `weight` is the released synapse count.
- **Source file checksums**: recorded both in
  `docs/RESEARCH_SOURCES.md` and inside the derived file's own `provenance`
  block, so the attribution travels with the data rather than only with the
  repository.

### Note on sex

These meshes are from NeuroMechFly, an adult **female** *Drosophila*. The
connectome data this project's neural track targets is MaleCNS (**male**).
These are explicitly not the same individual or sex, and are kept as
separate data layers -- see `docs/RESEARCH_SOURCES.md`.

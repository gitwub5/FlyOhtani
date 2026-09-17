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

### Note on sex

These meshes are from NeuroMechFly, an adult **female** *Drosophila*. The
connectome data this project's neural track targets is MaleCNS (**male**).
These are explicitly not the same individual or sex, and are kept as
separate data layers -- see `docs/RESEARCH_SOURCES.md`.

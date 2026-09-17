# Research Sources

This file tracks external scientific data, citations, and license constraints for FlyOhtani.

## 현재 선택

EXP-001의 확정 데이터 파일·출처·CC BY 4.0·해시 획득 절차는 [DATA_MODEL](design/DATA_MODEL.md)에 있다. 첫 대상은 MaleCNS v1.0 KC→MBON11이다. 현재 실제 데이터는 아직 가져오지 않았다. 코드의 가소성은 설계한 모델이며 논문 원식을 재현했다고 표시하지 않는다. 아래 FlyWire/hemibrain은 후속 비교 후보다.

## 2026-09-16 I-08a: NeuroMechFly mesh assets imported (baseball character visual, not connectome data)

First actual external asset import this project has done: `envs/assets/mesh_neuromechfly/*.stl` (43 files) from PyPI `flygym==1.2.1` (Apache-2.0), used as a purely visual (non-colliding, massless) overlay for the baseball B1 batter character. Full provenance/hashes/derivation: [docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json](design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json) and [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). This is mesh/appearance data only -- **not** connectome/wiring data, and NeuroMechFly's own fly is female while this project's neural-circuit track (below) uses MaleCNS (male); the two are explicitly separate data layers, not the same individual.

## 2026-09-17 VM-01 B1/B2: NeuroMechFly joint/pose data inspected, unit convention resolved (design-only, not imported into the repo)

`docs/design/VM01-B1-MINIMAL-BODY.md`'s joint-structure/DOF/control-default/
natural-pose-range facts were read directly from the SAME `flygym==1.2.1`
(Apache-2.0) package already cited above, re-obtained via `pip download
flygym==1.2.1 --no-deps` (per `scripts/build_fly_visual_asset.py`'s own
documented re-run command) to inspect the RAW (pre-strip) MJCF
(`flygym/data/mjcf/neuromechfly_seqik_kinorder_ypr.xml`), `flygym/fly.py`,
`flygym/preprogrammed.py`, and `flygym/data/pose/{pose_stretch,
pose_tripod}.yaml`. Nothing from this inspection was vendored into
`envs/assets/` -- it is cited numbers/facts in a design doc only, no new
mesh/code files.

**B1 (2026-09-17) reported as UNRESOLVED**: the raw MJCF's own `mass="..."`
attributes summed via a naive regex to ~1.0 (suggesting a body-mass-
fraction convention), while MuJoCo's own compiled `model.body_mass.sum()`
for the same file gave ~0.00026 -- flagged as an unexplained discrepancy,
with an explicit refusal to derive absolute mass/torque numbers until
resolved.

**B2 (2026-09-17, same day) found the "~1.0" was a MEASUREMENT BUG, not a
real discrepancy**: the naive regex also matched `<statistic
meanmass="1.0" .../>`, a visualization-only metadata hint, not a body/geom
mass. Excluding it, the geom-only mass sum is ~0.001 (in the file's native
unit). Tracing `flygym/fly.py`'s actual loader (`dm_control.mjcf.from_path`,
no Python-side mass rescaling found) and NeuroMechFly's own official
documentation resolved the unit convention directly:

> "we use millimeter and gram as base units for length and mass instead of
> their SI counterparts, meter and kilogram... forces read out from the
> simulation are in g·mm·s⁻¹ (i.e., micronewton, μN)"
> — [NeuroMechFly: Advanced model composition](https://neuromechfly.org/tutorials/1b_advanced_model_composition/)

i.e. length=mm, mass=g, force/torque=μN (g·mm·s⁻²), fully consistent with
the model's own `gravity="0 0 -9810"` (the standard trick for keeping
positions in mm while accelerations stay in real seconds). The corrected
~0.001g (~1mg) total body mass matches the commonly-cited order of
magnitude for adult *Drosophila melanogaster* mass, though no specific
literature citation for that exact figure has been pinned down yet.
Per-segment front-leg masses and the original position-control gain/
force-range are now converted to SI in `docs/design/
VM01-B1-MINIMAL-BODY.md` section 1.4.

## 2026-09-16 update

See the [dated review](research/REVIEW.md) for primary sources and evidence limits covering Shiu, FlyVis, NeuroMechFly, Eon, FlyGM, MaleCNS, Stonkfly, DOOMFLY, NeuroCraft Fly, Fly Arena, FLM, and mushroom-body learning papers. No external code or data was imported. (An earlier copy of this review, `archive/RESEARCH_REVIEW_2026-09-16.md`, is preserved for history; `research/REVIEW.md` is the current version.)

- [FlyWire guidelines](https://join.flywire.ai/guidelines): v783 and CC BY-NC 4.0; record annotation snapshots separately.
- [MaleCNS downloads](https://male-cns.janelia.org/download/): candidate for actual brain–VNC and mushroom-body circuitry. Record the selected artifact's version, checksum, and license before import; do not automatically inherit hemibrain notes.
- [Eon implementation](https://github.com/eonsystemspbc/fly-brain): default GPL-2.0-or-later, with separately identified MIT upstream Shiu materials. Code and data terms are distinct.
- [FlyGym API migration](https://neuromechfly.org/migration/): 2026 2.x differs from the Gymnasium-based version used by older examples. Pin software versions alongside paper citations.

## Current Policy

The repository code can use its own software license, but connectome data and derived files must keep their original data license terms. Before adding any external neural morphology, connectivity matrix, annotation table, or derived subset, document:

- source URL
- dataset version or snapshot
- citation
- license
- whether commercial use is allowed
- local file paths that contain derived data

## Candidate Connectome Sources

### FlyWire

Use case:

- Future connectome-inspired visual and motor wiring.
- Candidate source for fly brain cell types, annotations, and connectivity motifs.

Source links:

- FlyWire home: https://home.flywire.ai/
- FlyWire Codex: https://codex.flywire.ai/
- FlyWire citation guidelines: https://join.flywire.ai/guidelines
- FlyWire overview/about: https://codex.flywire.ai/about_flywire

License notes:

- FlyWire public release data is listed by FlyWire as `CC BY-NC 4.0`.
- `CC BY-NC 4.0` permits sharing and adaptation with attribution for non-commercial use.
- Because of the non-commercial restriction, do not mix FlyWire-derived data into artifacts intended for commercial use without checking permissions.
- Keep FlyWire-derived data clearly separated from original project code.

Primary citations to consider:

- Dorkenwald, S. et al. "Neuronal wiring diagram of an adult brain." Nature 634, 124-138 (2024). https://doi.org/10.1038/s41586-024-07558-y
- Schlegel, P. et al. "Whole-brain annotation and multi-connectome cell typing of Drosophila." Nature 634, 139-152 (2024). https://doi.org/10.1038/s41586-024-07686-5

Current project usage:

- No FlyWire data has been imported yet.
- Current code only uses hand-written toy SNN scaffolds and retina-like encoders.

### Janelia FlyEM Hemibrain

Use case:

- Alternative or comparison connectome source.
- Useful for neuPrint-based exploration and cell-type/motif references.

Source links:

- Janelia FlyEM Hemibrain: https://www.janelia.org/node/65250
- Janelia open science overview: https://www.janelia.org/open-science/overview

License notes:

- Janelia lists hemibrain as licensed under `CC-BY`.
- Janelia generally describes many data resources under `CC BY 4.0`, but dataset-specific license notes should take precedence.

Current project usage:

- No hemibrain data has been imported yet.

## README Attribution Guidance

If future versions include connectome-derived wiring, add a short README note:

```text
Connectome data attribution: portions of the connectome-inspired wiring are derived from [dataset/version]. Dataset license: [license]. Please cite [papers].
```

If no external data is included, keep the README wording clear:

```text
This repository currently contains no FlyWire or hemibrain data. FlyWire and hemibrain are listed as candidate scientific references for future connectome-inspired wiring.
```

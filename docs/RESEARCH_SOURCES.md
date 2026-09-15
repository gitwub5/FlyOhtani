# Research Sources

This file tracks external scientific data, citations, and license constraints for FlyOhtani.

## 현재 선택

EXP-001의 확정 데이터 파일·출처·CC BY 4.0·해시 획득 절차는 [DATA_MODEL](design/DATA_MODEL.md)에 있다. 첫 대상은 MaleCNS v1.0 KC→MBON11이다. 현재 실제 데이터는 아직 가져오지 않았다. 코드의 가소성은 설계한 모델이며 논문 원식을 재현했다고 표시하지 않는다. 아래 FlyWire/hemibrain은 후속 비교 후보다.

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

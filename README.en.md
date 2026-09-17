<div align="center">

# FlyOhtani 🪰⚾

**A life-sized fruit fly steps into the batter's box, watches the pitch with its own eyes, and swings.**

A research simulation built from a NeuroMechFly body, a MaleCNS connectome circuit, and MuJoCo physics.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![MuJoCo 3.13](https://img.shields.io/badge/MuJoCo-3.13-0B7285)
![Connectome MaleCNS v1.0](https://img.shields.io/badge/connectome-MaleCNS%20v1.0-6741d9)
![License MIT](https://img.shields.io/badge/license-MIT-2f9e44)
![Status research prototype](https://img.shields.io/badge/status-research%20prototype-e8590c)

[한국어](README.md) · English

<img src="docs/assets/hit.gif" width="640" alt="A 3.7 mm fly in the batter's box swings a bat and hits the ball. Left: a camera down the third-base line. Right: a camera following the ball.">

<sub>A recorded hit, played 8× slower than real time. <b>The swing is still scripted</b> — it is not a learned motion.</sub>

</div>

---

## What this is trying to do

Stand a 3.7 mm fruit fly in the batter's box the way a human batter stands. When
the pitch comes, the fly sees it with the small eyes on either side of its head,
and a circuit lifted from a real fly brain connectome drives its foreleg to swing
the bat. It is rewarded for making contact, and for driving the ball farther into
the infield.

The end goal is to watch all of that **on one screen** — the swing, what the fly
saw, the structure of the circuit inside its brain, and the spikes.

```mermaid
flowchart LR
    A["👁️ Eye cameras<br/>32×32 grayscale ×2"] --> B["Retinal encoding"]
    B --> C["LC4 · LPLC2<br/>311 looming neurons"]
    C --> D["12 descending neurons<br/>DNp01 Giant Fiber, …"]
    D --> E["🦵 Right foreleg<br/>5 joints + bat"]
    E --> F["⚾ Batted ball<br/>contact · direction · carry"]
    F -. "reward" .-> C
```

The wiring (who sends how many synapses to whom) is real data. The neuron
dynamics and the learning rule are **assumptions we made**.

What is verified today and what does not exist yet is in
[STATUS](docs/records/STATUS.md) (Korean); the full plan and the design decisions
are in [PLAN](docs/PLAN.md) (Korean).

## A look around

### The fly at the plate

<img src="docs/assets/batter-ready.jpg" width="720" alt="A fly standing upright in the middle of the right-handed batter's box, holding a bat with its foreleg.">

The body is held fixed and **only the right foreleg** moves, through its real
joints. Bat, ball, home plate and the box are all shrunk by a single factor
(fly height 3.74 mm ÷ human height 1830 mm ≈ 1/490). The bat is a 1.76 mm solid
of revolution made from the profile of a real wooden bat.

<img src="docs/assets/swing-strip.jpg" width="720" alt="Seven frames of the swing, from the ready pose to the contact pose.">

<sub>The 35 ms demo swing. Peak joint speed 215 rad/s, inside the 300 rad/s biological ceiling we adopted.</sub>

### What the fly sees

<img src="docs/assets/fly-eyes.png" width="560" alt="Four 32×32 grayscale eye images: three left-eye frames as the ball approaches, and one right-eye frame.">

One 32×32 grayscale camera on each side of the head (120° field of view). Because
the fly stands sideways, **its left eye looks straight at the pitcher.** The first
three frames are the left eye as the ball closes in; the last is the right eye.
The red ring is an annotation — it is not part of the input the fly receives.

### The circuit in the brain

<img src="docs/assets/brain-circuit.jpg" width="720" alt="Four views of the soma atlas with the circuit's neurons lit up stage by stage.">

Our circuit lit up on top of 124,289 real somata (the blue points). In reading order
from the top left: LC4 → LPLC2 → descending neurons → all together. **Brightness is
synapse count, not neural activity.** No neuron is simulated yet.

### The viewer

<img src="docs/assets/viewer.jpg" width="720" alt="The browser viewer: a recorded episode and its outcome on the left, the 3D brain atlas and the fly body on the right.">

A browser viewer that puts the recorded episode, the brain atlas and the fly body
on one screen. Built by modifying
[fly-connectome-template](https://github.com/cobanov/fly-connectome-template)
(see [below](#brain-visualization-viewer)).

## Results so far

| Check | Result |
| --- | --- |
| **G1** foreleg swing | All 240 runs stable. dt convergence 0.07%, spread across three integrators 0.02%. Actuation was never the bottleneck |
| **LIT-01** speed ceiling | Measured walking peak 98.6 rad/s; jump estimate 240–516 rad/s → design ceiling **300 rad/s** (bat tip up to 4.53 m/s) |
| **G4** connectome | LC4 (126) · LPLC2 (185) → 12 descending neurons, 1,343 connections. Known looming–escape pathways (LPLC2 → Giant Fiber, …) are present in the data |
| **G2** contact | v1 **FAILED** (contact lasted only 3–4 steps, so the restitution coefficient swung 0.33 ↔ 0.63) → v2 passed (restitution 0.42–0.46) |
| Batter-scene contact check | K1–K6 all pass. Restitution 0.41–0.46, no energy created |
| Recorded hit | Pitch 1.81 m/s (scaled), exit speed 602 mm/s, launch −24°, carry 1.96 mm (~1 m at human scale) — **a fair ground ball** |
| Recorded miss | Swinging just 4 ms late misses entirely. The timing window is very narrow |

Failed runs are kept, not deleted. Evidence files are in
[docs/records/evidence/](docs/records/evidence/); the run log is
[VALIDATION_LOG](docs/records/VALIDATION_LOG.md).

## Getting started

**You need:** Python 3.11+, and Node.js 22.18+ for the viewer. Developed on an
Apple M2 Pro laptop; no GPU required. A 0.1 s episode takes about 0.6 s.

```bash
git clone https://github.com/gitwub5/FlyOhtani.git && cd FlyOhtani
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev,video]"
.venv/bin/pytest                      # 139 passed
```

### Record an episode

```bash
.venv/bin/python -m flyohtani.record pitch --out runs/record/hit                     # a hit
.venv/bin/python -m flyohtani.record pitch --timing-ms 4 --out runs/record/miss-late # swinging late
.venv/bin/python -m flyohtani.record pitch --speed-scale 0.5 --out runs/record/slow  # a slower pitch
.venv/bin/python -m flyohtani.record swing --out runs/record/swing                   # the swing alone, no ball
```

Each writes `video.mp4`, a contact sheet `sheet.png` and the outcome
`manifest.json` into `runs/record/<name>/`.

### Brain visualization viewer

```bash
.venv/bin/python -m flyohtani.brain.replay --run runs/record/hit   # export for the viewer
cd viewer && npm ci && npm run dev                                 # http://127.0.0.1:5173
```

Built with [fly-connectome-template](https://github.com/cobanov/fly-connectome-template) by [Mert Cobanov](https://github.com/cobanov).

`viewer/` is that template, modified, and is covered by the **Cobanov Template
Attribution License 1.0** ([viewer/LICENSE](viewer/LICENSE)). The credit above
must not be removed from this README or from the viewer's UI. What we changed is
listed in [viewer/MODIFICATIONS.md](viewer/MODIFICATIONS.md); provenance is in
[viewer/PROVENANCE.json](viewer/PROVENANCE.json).

## Repository layout

```
flyohtani/
├── units.py        unit convention (mm · g · μN), constants measured from the source model
├── body/           the real foreleg + bat model, the G1 sweep, speed limits
├── brain/          MaleCNS looming-circuit loader, export for the viewer
├── sense/          eye cameras, ball detection and tracking, observation schema
├── world/          the batter scene, contact parameters, G2 and the contact check
├── record/         episode → video · stills · outcome JSON
└── assets/         NeuroMechFly meshes/MJCF/walking data, the connectome subgraph (with provenance)
viewer/             3D brain viewer (based on fly-connectome-template)
tests/              139 pytest tests + a viewer parser test
docs/               plan, status, per-gate reports, evidence files (Korean)
```

## How this is run

- **Acceptance criteria are committed before the run.** Commit order serves as
  pre-registration. A bad result does not get the criteria loosened.
- **No single number is trusted until it has been shaken.** dt convergence,
  integrator cross-checks, sensitivity analysis.
- **Failures are not deleted.** The G2 v1 failure, voided runs, and claims that
  turned out to be wrong are all still in the records, with their corrections.
- **"We chose this" and "this is what came out" are kept apart** — engineering
  choices are never written up as measurements.

### What this repository does not claim

- Containing a connectome does **not** mean the brain is reproduced. This is real
  wiring + assumed neuron dynamics + assumed plasticity.
- The brain panel in the viewer shows **wiring**, not activity.
- The swing in the video is **scripted**, not learned.
- Hand-written and RL controllers are environment baselines only. Any claim that
  the real circuit does better waits for shuffled-wiring and frozen-circuit
  controls.

## Documentation

The documents below are in Korean.

| Document | Contents |
| --- | --- |
| [PLAN](docs/PLAN.md) | Design decisions D01–D30, phases and gates |
| [STATUS](docs/records/STATUS.md) | What is verified now and what is blocked |
| [G1 foreleg swing](docs/records/G1-FORELEG-SWING.md) · [LIT-01 speed limits](docs/records/LIT-01-FLY-LEG-LIMITS.md) | Body |
| [G2 contact](docs/records/G2-CONTACT.md) · [batter scene](docs/records/BATTER-SCENE.md) | World |
| [G4 connectome](docs/records/G4-CONNECTOME-ACCESS.md) | Brain |
| [Prior findings](docs/records/PRIOR-FINDINGS.md) | What the previous version settled, and the failures not to repeat |
| [Index](docs/README.md) | The full list |

## Data · licenses · citation

The project code is [MIT](LICENSE); `viewer/` follows the template license above.
Imported third-party assets keep their own licenses, with source, version and
checksums recorded in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) and
[RESEARCH_SOURCES](docs/RESEARCH_SOURCES.md).

| Asset | Source | License |
| --- | --- | --- |
| Fly meshes · MJCF · walking joint angles | NeuroMechFly v2 / flygym 1.2.1 | Apache-2.0 |
| Looming-circuit wiring | MaleCNS v1.0 | CC-BY |
| Soma atlas · fly body inside the viewer | MaleCNS v1.0 · Flybody | CC BY 4.0 · Apache-2.0 |
| Brain viewer | fly-connectome-template (Mert Cobanov) | Cobanov Template Attribution License 1.0 |

This work stands on:

- Wang-Chen, S. et al. (2024). NeuroMechFly v2: simulating embodied sensorimotor control in adult *Drosophila*. *Nature Methods* 21, 2353–2362. [doi:10.1038/s41592-024-02497-y](https://doi.org/10.1038/s41592-024-02497-y)
- MaleCNS v1.0 connectome ([male-cns.janelia.org](https://male-cns.janelia.org/download/)) — FlyEM (HHMI Janelia), University of Cambridge, MRC LMB, Google Research. Terms of use are summarized in the [G4 report](docs/records/G4-CONNECTOME-ACCESS.md).
- Card, G. & Dickinson, M. (2008). Performance trade-offs in the flight initiation of *Drosophila*. *J. Exp. Biol.* 211, 341–353. [doi:10.1242/jeb.012682](https://doi.org/10.1242/jeb.012682)
- Zumstein, N. et al. (2004). Distance and force production during jumping in wild-type and mutant *Drosophila melanogaster*. *J. Exp. Biol.* 207, 3515–3522. [PMID 15339947](https://pubmed.ncbi.nlm.nih.gov/15339947/)

## Previous version

The whole of v1 — a human-sized field and a three-axis rigid bat — is preserved
in the git tag **`archive/human-scale-v0`**.

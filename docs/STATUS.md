# Status

## 2026-09-16 — Architecture and Claude handoff (latest)

- User confirmed the division of work: Codex handles planning and structure; Claude and the user handle implementation and tests.
- Updated the root README to the active research direction and removed the obsolete sequential PPO→SNN roadmap from the main entry point.
- Added `CLAUDE.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `IMPLEMENTATION_HANDOFF.md`, `configs/README.md`, and the draft `experiments/EXP-001-associative-learning.md`.
- Defined module responsibilities, clock/unit boundaries, fast/slow/trace state handling, independent memory probes, configuration and run records.
- Handoff work I-01/I-02 and the independent physics fixes I-03 can proceed with Claude. Dataset/model implementation and EXP-001 scientific execution depend on the listed research choices.
- Scientific paper, dataset, circuit extent, detailed parameters, evaluation thresholds, and compute budget remain pending; the draft is not an executable experiment.
- Existing Python, XML, TOML and YAML implementation/configuration are intentionally unchanged. No application tests, installs, data imports or model runs were performed in this documentation task.

## 2026-09-16 — Planning-first research

- User direction: planning before implementation; investigate whether real fruit-fly circuits can learn new tasks.
- References supplied by the user: Stonkfly, Doom/Smash Bros., Minecraft, NeuroMechFly-based demos, and FLM.
- Added a dated source audit and primary-source research review. The active proposal is `RESEARCH_PLAN.md`; the previous implementation roadmap is historical.
- Proposed sequence: select a literature-backed mushroom-body learning protocol; verify actual connectivity and neural dynamics; test conditioning, retention, and memory removal; extend to timing and then interception.
- Output-layer-only learning is a comparison condition, not the main evidence for internal circuit learning.
- Source concerns: gravity missing from launch calculation; contact checked after frame skipping; metric definitions; neural/physics timing; disconnected configuration and experiment records.
- Current shell: macOS arm64, Python 3.14.0; major runtime/learning packages absent in that interpreter. Python AST checks passed for 19 files. Runtime physics and learning remain unvalidated.
- No implementation, dependency installation, external data import, or training was performed. Documentation only.
- Pending planning choices: reference paper/protocol, dataset and circuit scope, whether whole-brain scale is essential, available hardware and budget. The older implementation next actions below are deferred.

## 2026-09-15

### Current State

- Repository scaffold exists directly at the project root.
- Python package metadata exists in `pyproject.toml`.
- Minimal MuJoCo environment exists in `envs/fly_batter_env.py`.
- MuJoCo XML asset exists in `envs/assets/fly_batter.xml`.
- Scripted swing baseline exists in `controllers/scripted.py`.
- Placeholder MLP, SNN, and Brian2 STDP controller interfaces exist.
- Retina-like and compact ball-state spike encoders exist.
- Demo, training, analysis, and config entry points exist.
- Documentation folder added to track project plan, status, test results, and research sources.

### Decisions

- Start with a deliberately simple agent: one body and one actuated swing limb.
- Use MuJoCo for contact and rigid-body physics.
- Use Gymnasium-style environment APIs for compatibility with PPO tooling.
- Treat external connectome datasets as data dependencies with separate citation and license requirements.
- Do not import FlyWire or hemibrain data until the project explicitly needs it.

### Known Limitations

- The current local environment did not have `mujoco` or `gymnasium` installed during initial validation.
- The MuJoCo environment has passed Python syntax checks and XML syntax checks, but not runtime physics validation yet.
- Scripted swing parameters are initial guesses and should be tuned after MuJoCo runtime is installed.
- The SNN and Brian2 controllers are scaffolds, not finished learning systems.

### Next Actions

1. Install runtime dependencies with `pip install -e ".[dev]"`.
2. Run `python demos/record_episode.py --episodes 3`.
3. If contact does not occur, tune:
   - ball target point
   - flight time range
   - swing hinge torque gear
   - swing trigger distance
   - limb length and collision capsule radius
4. Add first real metrics to `docs/TEST_LOG.md`.
5. Add tests once environment runtime behavior is confirmed.

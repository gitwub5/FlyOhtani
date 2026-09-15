# Project Plan

> Historical scaffold roadmap. As of 2026-09-16, the active planning document is [RESEARCH_PLAN.md](RESEARCH_PLAN.md). The user prioritized research on learning in real-connectome-derived circuits. The implementation sequence below is preserved for context and is deferred during planning.

## Goal

Build FlyOhtani: a connectome-inspired spiking neural agent for 3D ball interception.

Core concept:

> A connectome-inspired spiking neural agent for 3D ball interception.

## Research Questions

1. Can a minimal spiking controller learn swing timing from ball trajectory signals?
2. How does an SNN policy compare with a scripted controller and an MLP/PPO baseline?
3. Which observation encoding is most useful early on: compact ball state, retina-like grid spikes, or connectome-inspired visual pathways?
4. Can reward-modulated STDP produce useful timing behavior before full PPO-based SNN training?

## Milestones

### Phase 0: Project Memory and Scaffold

Status: in progress

- Create Python package structure.
- Add MuJoCo XML asset.
- Add baseline environment, scripted controller, encoders, analysis utilities, and configs.
- Add docs for status, planning, tests, and external data provenance.

### Phase 1: Scripted MuJoCo Baseline

Status: next

- Install runtime dependencies.
- Verify `FlyBatterEnv` loads with MuJoCo.
- Run scripted swing episodes.
- Tune ball trajectory, limb length, hinge torque, and hit detection until contact is reproducible.
- Record first baseline metrics:
  - hit rate
  - timing error
  - contact velocity
  - total reward
  - energy cost

### Phase 2: MLP/PPO Baseline

Status: planned

- Wrap the environment for Stable-Baselines3 PPO.
- Train an MLP policy on compact ball-state observations.
- Save reward curves and trained checkpoints.
- Compare scripted and learned baselines.

### Phase 3: SNN Policy

Status: planned

- Convert ball state or retina-like grid observations into spike inputs.
- Add a trainable SNN policy interface.
- Track spike rasters and firing rates during episodes.
- Compare SNN timing behavior against MLP/PPO.

### Phase 4: Brian2 Reward-Modulated STDP

Status: planned

- Implement a Brian2 controller.
- Add reward-modulated STDP experiments.
- Track weight changes and timing improvements.

### Phase 5: Connectome-Inspired Wiring

Status: planned

- Select public Drosophila connectome source.
- Record source, citation, and license before importing data.
- Start with coarse visual/motor motifs rather than a full-brain copy.
- Map retina-like input populations to motor output populations through simplified intermediate layers.

## Design Principles

- Keep the first environment small enough to debug by inspection.
- Prefer explicit metrics over visual judgment.
- Separate code license from external data licenses.
- Avoid importing FlyWire or hemibrain data until the intended use and license constraints are documented.

"""Learning: search the policy's free parameters against a reward.

Not gradient descent and not plasticity -- a population search over the
handful of numbers the decode leaves open. That is a deliberate first step:

  * the parameters that matter are few and interpretable (when to commit,
    how long to wait, where the zone boundary sits), so a search over them
    answers "is there anything to find" without a learning rule's own
    assumptions on top;
  * the same loop will drive reward-modulated plasticity later; only
    `parameters` and `apply` change.

RULES, fixed before the first run:

  train on training pitches      `pitches.training_pitches`
  report on held-out pitches     `pitches.evaluation_pitches`, never used
                                 to select anything
  keep the baselines             a fixed-frame policy cannot see; if search
                                 does not beat it, seeing bought nothing
  report what comes out          including a search that finds nothing

The reward is named on the command line, not defaulted, because which one is
being optimised is the whole question.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import numpy as np

from flyohtani.brain.circuit import LoomingCircuit
from flyohtani.task import rewards
from flyohtani.task.env import BattingEnv, PitchSpec
from flyohtani.task.pitches import evaluation_pitches, training_pitches
from flyohtani.task.policy import CircuitPolicy, FixedFramePolicy, run_episode


@dataclass(frozen=True)
class Genome:
    """Everything the search may move. Bounds are the ranges over which the
    quantity means anything -- a 12-frame motor delay is longer than the
    pitch, a zone boundary outside the measured rise rates is a constant."""

    motor_delay_frames: int = 3
    spikes_to_swing: int = 1
    zone_rise_boundary: float = -0.09
    zone_window_frames: int = 5
    input_gain_scale: float = 1.0

    BOUNDS: ClassVar[dict[str, tuple[float, float]]] = {
        "motor_delay_frames": (0, 8),
        "spikes_to_swing": (1, 4),
        "zone_rise_boundary": (-0.40, 0.20),
        "zone_window_frames": (3, 9),
        "input_gain_scale": (0.4, 2.5),
    }

    def policy(self) -> CircuitPolicy:
        return CircuitPolicy(
            circuit=LoomingCircuit(input_gain=13_500.0 * self.input_gain_scale),
            spikes_to_swing=self.spikes_to_swing,
            motor_delay_frames=self.motor_delay_frames,
            zone_rise_boundary=self.zone_rise_boundary,
            zone_window_frames=self.zone_window_frames,
        )

    def mutated(self, rng: np.random.Generator, scale: float = 1.0) -> Genome:
        lo, hi = Genome.BOUNDS["zone_rise_boundary"]
        return Genome(
            motor_delay_frames=int(np.clip(
                self.motor_delay_frames + rng.integers(-1, 2), *Genome.BOUNDS["motor_delay_frames"])),
            spikes_to_swing=int(np.clip(
                self.spikes_to_swing + rng.integers(-1, 2), *Genome.BOUNDS["spikes_to_swing"])),
            zone_rise_boundary=float(np.clip(
                self.zone_rise_boundary + rng.normal(0, 0.06 * scale), lo, hi)),
            zone_window_frames=int(np.clip(
                self.zone_window_frames + rng.integers(-1, 2), *Genome.BOUNDS["zone_window_frames"])),
            input_gain_scale=float(np.clip(
                self.input_gain_scale * np.exp(rng.normal(0, 0.15 * scale)),
                *Genome.BOUNDS["input_gain_scale"])),
        )

    @staticmethod
    def random(rng: np.random.Generator) -> Genome:
        return Genome(
            motor_delay_frames=int(rng.integers(*Genome.BOUNDS["motor_delay_frames"])),
            spikes_to_swing=int(rng.integers(1, 5)),
            zone_rise_boundary=float(rng.uniform(*Genome.BOUNDS["zone_rise_boundary"])),
            zone_window_frames=int(rng.integers(3, 10)),
            input_gain_scale=float(np.exp(rng.uniform(np.log(0.4), np.log(2.5)))),
        )


@dataclass
class Score:
    reward: float
    contact_rate: float
    zone_rate: float
    fair_rate: float
    n: int


def evaluate(genome: Genome, pitches: list[PitchSpec], reward_name: str,
             env: BattingEnv | None = None) -> Score:
    env = env or BattingEnv()
    policy = genome.policy()
    reward_fn = rewards.get(reward_name)
    total = contact = zone = fair = 0.0
    for pitch in pitches:
        out = run_episode(env, policy, pitch)
        total += reward_fn(out)
        contact += out.contact
        zone += out.swing_zone == out.pitch_zone
        fair += bool(out.fair)
    n = len(pitches)
    return Score(total / n, contact / n, zone / n, fair / n, n)


BASELINE_FRAMES = range(6, 26)
"""Every frame a blind policy could pick. Fixed as a RANGE, not a guess:
three hand-picked frames (18, 20, 22) scored zero once the pitch got shorter
and the connecting frame moved to 13, which made the search look better than
it was. A baseline has to be the best a blind policy can do, not the best of
three arbitrary ones."""


def baseline_scores(pitches: list[PitchSpec], reward_name: str,
                    env: BattingEnv | None = None) -> dict[str, Score]:
    """Policies that cannot see, for the search to be measured against. Every
    frame is tried and the best one is what the search has to beat."""
    env = env or BattingEnv()
    reward_fn = rewards.get(reward_name)
    out = {}
    for frame in BASELINE_FRAMES:
        total = contact = zone = fair = 0.0
        policy = FixedFramePolicy(frame)
        for pitch in pitches:
            o = run_episode(env, policy, pitch)
            total += reward_fn(o)
            contact += o.contact
            zone += o.swing_zone == o.pitch_zone
            fair += bool(o.fair)
        n = len(pitches)
        out[f"fixed-frame-{frame}"] = Score(total / n, contact / n, zone / n, fair / n, n)
    best = max(out, key=lambda k: out[k].reward)
    out["best-blind"] = out[best]
    out["best-blind-frame"] = Score(float(best.rsplit("-", 1)[1]), 0.0, 0.0, 0.0, 0)
    return out


def search(reward_name: str = "carry-v1", generations: int = 6, population: int = 12,
           train_pitches: int = 16, seed: int = 0, out_path: Path | None = None) -> dict:
    """(mu + lambda) hill climbing from a random start. Small on purpose: the
    point is whether the free parameters can be set at all, not to squeeze a
    number out of a big search."""
    rng = np.random.default_rng(seed)
    env = BattingEnv()
    train = training_pitches(train_pitches)
    held_out = evaluation_pitches(30)

    parent = Genome()
    parent_score = evaluate(parent, train, reward_name, env)
    history = [{"generation": 0, "genome": parent.__dict__ | {}, "train_reward": parent_score.reward}]
    for g in range(1, generations + 1):
        children = [parent.mutated(rng) for _ in range(population - 1)] + [Genome.random(rng)]
        scored = [(evaluate(c, train, reward_name, env), c) for c in children]
        best_score, best = max(scored, key=lambda s: s[0].reward)
        if best_score.reward > parent_score.reward:
            parent, parent_score = best, best_score
        history.append({"generation": g, "genome": dict(parent.__dict__),
                        "train_reward": parent_score.reward,
                        "train_contact": parent_score.contact_rate})

    final = evaluate(parent, held_out, reward_name, env)
    result = {
        "reward": reward_name,
        "seed": seed,
        "generations": generations,
        "population": population,
        "train_pitches": train_pitches,
        "best_genome": dict(parent.__dict__),
        "train_reward": parent_score.reward,
        "held_out": final.__dict__,
        "baselines_held_out": {k: v.__dict__ for k, v in baseline_scores(held_out, reward_name, env).items()},
        "history": history,
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=1) + "\n")
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reward", required=True, choices=sorted(rewards.REWARDS))
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--train-pitches", type=int, default=16)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    result = search(args.reward, args.generations, args.population,
                    args.train_pitches, args.seed, args.out)
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=1))


if __name__ == "__main__":
    main()

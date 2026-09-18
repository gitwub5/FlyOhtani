"""Pitches, rewards and the search loop.

No test here asserts that learning works. Whether it does is a measurement,
it goes in docs/records/, and a test that demanded it would quietly become a
reason to keep tuning until it passed.
"""
from __future__ import annotations

import pytest

from flyohtani.task import learn, pitches, rewards
from flyohtani.task.outcome import Outcome
from flyohtani.world import batter as B


class TestPitches:
    def test_training_and_evaluation_draws_are_disjoint_streams(self):
        assert pitches.TRAINING_SEED != pitches.EVALUATION_SEED
        train = pitches.training_pitches(40)
        held = pitches.evaluation_pitches(40)
        overlap = {(p.zone, round(p.timing_ms, 9)) for p in train} & \
                  {(p.zone, round(p.timing_ms, 9)) for p in held}
        assert not overlap, "a held-out pitch was also trained on"

    def test_the_held_out_set_is_balanced_across_zones(self):
        held = pitches.evaluation_pitches(30)
        counts = {z: sum(p.zone == z for p in held) for z in B.STRIKE_ZONES}
        assert len(set(counts.values())) == 1, counts

    def test_timing_spread_is_wider_than_the_window_that_connects(self):
        """If the jitter were inside the contact window, a fixed-timing
        policy would score without seeing anything."""
        assert pitches.TIMING_JITTER_MS >= 2.0

    def test_a_draw_is_reproducible(self):
        assert [p.zone for p in pitches.training_pitches(10)] == \
               [p.zone for p in pitches.training_pitches(10)]


def _outcome(**kw) -> Outcome:
    return Outcome(**kw)


class TestRewards:
    def test_missing_scores_zero_under_every_version(self):
        miss = _outcome(swung=True, contact=False)
        idle = _outcome(swung=False, contact=False)
        for name in rewards.REWARDS:
            assert rewards.get(name)(miss) == 0.0, name
            assert rewards.get(name)(idle) == 0.0, name

    def test_swinging_and_missing_is_worth_exactly_what_standing_still_is(self):
        """Paying for effort is how a policy learns to flail."""
        for name in rewards.REWARDS:
            fn = rewards.get(name)
            assert fn(_outcome(swung=True, contact=False)) == fn(_outcome(swung=False))

    def test_contact_v1_ignores_everything_except_contact(self):
        a = _outcome(contact=True, fair=True, carry_mm=40.0)
        b = _outcome(contact=True, fair=False, carry_mm=0.1)
        assert rewards.contact_v1(a) == rewards.contact_v1(b) == 1.0

    def test_direction_v1_pays_more_for_fair_and_ignores_distance(self):
        near = _outcome(contact=True, fair=True, carry_mm=0.5)
        far = _outcome(contact=True, fair=True, carry_mm=50.0)
        foul = _outcome(contact=True, fair=False, carry_mm=50.0)
        assert rewards.direction_v1(near) == rewards.direction_v1(far) == 2.0
        assert rewards.direction_v1(foul) == 1.0

    def test_carry_v1_is_the_only_one_that_separates_a_dribbler_from_a_drive(self):
        near = _outcome(contact=True, fair=True, carry_mm=0.5)
        far = _outcome(contact=True, fair=True, carry_mm=30.0)
        assert rewards.carry_v1(far) > rewards.carry_v1(near)
        assert rewards.carry_v1(far) == pytest.approx(3.0)

    def test_the_versions_stack(self):
        hit = _outcome(contact=True, fair=True, carry_mm=15.0)
        assert rewards.contact_v1(hit) <= rewards.direction_v1(hit) <= rewards.carry_v1(hit)

    def test_an_unknown_reward_is_refused_rather_than_defaulted(self):
        with pytest.raises(KeyError):
            rewards.get("carry-v2")


class TestSearch:
    def test_a_genome_stays_inside_its_bounds_however_it_is_mutated(self):
        import numpy as np
        rng = np.random.default_rng(0)
        g = learn.Genome()
        for _ in range(200):
            g = g.mutated(rng, scale=3.0)
            for field, (lo, hi) in learn.Genome.BOUNDS.items():
                assert lo <= getattr(g, field) <= hi, field

    def test_a_genome_builds_the_policy_it_describes(self):
        g = learn.Genome(motor_delay_frames=2, spikes_to_swing=3, zone_window_frames=7)
        p = g.policy()
        assert p.motor_delay_frames == 2
        assert p.spikes_to_swing == 3
        assert p.zone_window_frames == 7

    def test_scoring_reports_the_rates_it_claims(self):
        from flyohtani.task.env import PitchSpec
        score = learn.evaluate(learn.Genome(), [PitchSpec(zone="high")] * 2, "contact-v1")
        assert score.n == 2
        assert 0.0 <= score.contact_rate <= 1.0
        assert score.reward == pytest.approx(score.contact_rate)

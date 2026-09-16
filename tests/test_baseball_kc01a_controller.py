"""Regression tests for controllers/baseball_kc01a.py's "torso_lead_handoff"
mode and its validate_same_direction_candidate() pre-filter (docs/design/
KC-01a-DIRECTION-CONTRACT.md section 8): added after a candidate that
passed every existing check (dt convergence, settle, grip reachability)
turned out to have torso and swing commanded in OPPOSITE directions with
both follow-through targets outside their own joint ranges -- none of
which the 99 pre-existing tests (which never touch this mode's direction
or handoff semantics) could have caught. Passing the pre-existing suite is
explicitly NOT treated as validating this mode's own new behavior.
"""
from __future__ import annotations

import numpy as np

from controllers.baseball_kc01a import (
    SWING_RANGE,
    TORSO_RANGE,
    TorsoBatController,
    validate_same_direction_candidate,
)


def _obs(ball_vx, torso_angle, torso_vel, swing_angle, swing_vel, remaining, contact=False):
    obs = np.zeros(15, dtype=np.float32)
    obs[3] = ball_vx
    obs[6] = torso_angle
    obs[7] = torso_vel
    obs[8] = swing_angle
    obs[9] = swing_vel
    obs[10] = 0.0  # tilt_angle
    obs[12] = remaining
    obs[13] = float(contact)
    return obs


class TestValidateSameDirectionCandidate:
    def test_direction_mismatch_is_flagged(self):
        # The exact candidate docs/records/KC-01a-VALIDATION.md A11/A12
        # previously reported as passing full validation: torso accelerates
        # positive, swing accelerates negative -- opposite signs.
        valid, reasons = validate_same_direction_candidate(0.0, -1.96, 0.5, -1.9640000000000004)
        assert not valid
        assert any("direction mismatch" in r for r in reasons)

    def test_swing_displacement_near_zero_is_flagged(self):
        valid, reasons = validate_same_direction_candidate(0.0, -1.96, 0.5, -1.9640000000000004)
        assert not valid
        assert any("swing displacement too small" in r for r in reasons)

    def test_followthrough_outside_range_is_flagged_for_both_axes(self):
        # torso follow-through = 0.5+0.15=0.65 > 0.6; swing follow-through
        # = -1.964-0.4=-2.364 < -2.0 -- both out of range simultaneously.
        valid, reasons = validate_same_direction_candidate(0.0, -1.96, 0.5, -1.9640000000000004)
        assert not valid
        assert any("torso follow-through" in r for r in reasons)
        assert any("swing follow-through" in r for r in reasons)

    def test_all_failure_reasons_are_reported_together(self):
        # This one candidate fails all three checks at once -- the filter
        # must not stop at the first failure.
        valid, reasons = validate_same_direction_candidate(0.0, -1.96, 0.5, -1.9640000000000004)
        assert not valid
        assert len(reasons) >= 3

    def test_a_genuinely_valid_candidate_passes(self):
        # torso_dir=+1, swing_dir=+1 (same direction); swing displacement
        # 0.56rad (>0.3 minimum); follow-throughs: torso 0.45 (within
        # +-0.6-0.02), swing -1.0 (within +-2.0-0.02).
        valid, reasons = validate_same_direction_candidate(0.0, -1.96, 0.3, -1.4)
        assert valid, reasons
        assert reasons == []

    def test_range_constants_match_xml_jnt_range(self):
        assert TORSO_RANGE == (-0.6, 0.6)
        assert SWING_RANGE == (-2.0, 2.0)


class TestHandoffUsesSignedProgress:
    """docs/design/KC-01a-DIRECTION-CONTRACT.md section 8's fix: the
    handoff condition must use progress SIGNED along the intended
    direction, not abs(torso_angle - prep_torso) -- otherwise a torso
    excursion in the WRONG direction (e.g. a reaction dip) could also
    satisfy the threshold and hand off to swing prematurely."""

    def _controller(self, handoff_fraction=0.5):
        # torso_target=0.4 (dir=+1), swing_target=-1.5 (dir=+1, since
        # prep_swing=-1.96) -- a same-direction, in-range synthetic setup.
        return TorsoBatController(
            "torso_lead_handoff", 0.0, -1.96, 0.0, 0.4, -1.5, 0.1, 999.0, handoff_fraction=handoff_fraction
        )

    def test_backward_torso_excursion_never_triggers_handoff(self):
        controller = self._controller()
        controller.reset()
        # Trigger torso first (remaining crosses its crossing_time).
        controller.act(_obs(ball_vx=-1.0, torso_angle=0.0, torso_vel=0.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.05))
        assert controller._torso_triggered

        # Torso target is +0.4 (moving away from prep=0.0 in the POSITIVE
        # direction); handoff_target_disp = 0.5*0.4 = 0.2rad of signed
        # positive progress. Feed a NEGATIVE torso angle whose absolute
        # value already exceeds that threshold -- under the old abs()-based
        # condition this would incorrectly trigger the handoff.
        for _ in range(5):
            controller.act(
                _obs(ball_vx=-1.0, torso_angle=-0.25, torso_vel=-0.5, swing_angle=-1.96, swing_vel=0.0, remaining=0.04)
            )
        assert not controller._swing_triggered, (
            "swing was handed off despite torso moving in the WRONG (negative) direction -- "
            "the handoff condition is not using signed progress"
        )

    def test_forward_torso_progress_does_trigger_handoff(self):
        controller = self._controller()
        controller.reset()
        controller.act(_obs(ball_vx=-1.0, torso_angle=0.0, torso_vel=0.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.05))
        assert controller._torso_triggered
        assert not controller._swing_triggered

        # Positive progress just short of threshold (0.2rad): no handoff yet.
        controller.act(_obs(ball_vx=-1.0, torso_angle=0.15, torso_vel=1.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.04))
        assert not controller._swing_triggered

        # Positive progress at/above threshold: handoff fires.
        controller.act(_obs(ball_vx=-1.0, torso_angle=0.25, torso_vel=1.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.04))
        assert controller._swing_triggered

    def test_negative_target_direction_also_uses_signed_progress(self):
        # Mirror case: torso_target BELOW prep (dir=-1). A positive
        # excursion (wrong direction here) must not trigger handoff.
        controller = TorsoBatController(
            "torso_lead_handoff", 0.0, -1.96, 0.0, -0.4, -1.5, 0.1, 999.0, handoff_fraction=0.5
        )
        controller.reset()
        controller.act(_obs(ball_vx=-1.0, torso_angle=0.0, torso_vel=0.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.05))
        assert controller._torso_triggered

        for _ in range(5):
            controller.act(
                _obs(ball_vx=-1.0, torso_angle=0.25, torso_vel=0.5, swing_angle=-1.96, swing_vel=0.0, remaining=0.04)
            )
        assert not controller._swing_triggered

        controller.act(_obs(ball_vx=-1.0, torso_angle=-0.25, torso_vel=-1.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.04))
        assert controller._swing_triggered


class TestExistingModesUnaffected:
    """The four pre-existing modes' behavior must be bit-for-bit unchanged
    by the direction-storage refactor (_torso_dir/_swing_dir) and the new
    validate_same_direction_candidate/TORSO_RANGE/SWING_RANGE additions."""

    def test_staggered_mode_still_uses_time_based_trigger(self):
        controller = TorsoBatController("staggered", 0.0, -1.96, 0.0, -0.4, -0.726, 0.242, 0.122)
        controller.reset()
        # Far from arrival: neither axis triggered yet.
        controller.act(_obs(ball_vx=-1.0, torso_angle=0.0, torso_vel=0.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.5))
        assert not controller._torso_triggered
        assert not controller._swing_triggered
        # Crossing torso's own crossing_time triggers torso by TIME, not by
        # any handoff displacement condition.
        controller.act(_obs(ball_vx=-1.0, torso_angle=0.0, torso_vel=0.0, swing_angle=-1.96, swing_vel=0.0, remaining=0.24))
        assert controller._torso_triggered
        assert not controller._swing_triggered

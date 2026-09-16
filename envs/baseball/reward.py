"""ENV-002 B1 scoring and reward: pure functions of already-recorded episode
state, with no MuJoCo/mutable-environment access of their own. Extracted
from envs/baseball_b1_env.py's `_compute_scoring`/`_reward` methods by R-02
(docs/implementation/REFACTOR-PLAN.md) -- `BaseballB1Env` still owns
reset/step and all substep event ordering; it just calls into these
functions instead of computing scoring/reward inline. Behavior is
unchanged: same inputs produce the same outputs as before the extraction
(verified against docs/records/evidence/R00-baseline-mid_mid-before-after.json).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

# I-07c-score (docs/design/BATTING-QUALITY-AND-SWING.md section 1): field
# coordinate origin is home plate's own back vertex, +x toward the pitcher's
# rubber (envs/assets/baseball_park_b1.xml line 2-4 coordinate-system
# comment) -- so "home reference point" is just the world XY origin and
# "forward" is +x. Recorded here (not derived from a runtime geom lookup)
# because home_plate's own geom pos (0.2159, 0, ...) is the plate's *visual
# center*, not its back-vertex origin-defining corner.
HOME_REFERENCE_XY = np.array([0.0, 0.0])


@dataclass(frozen=True)
class RewardWeights:
    """batted-ball-v1 (I-07b-fix, docs/design/ENV-002-BATTED-BALL.md section 4).
    Replaces b0-contact-v1's on-contact reward entirely: mere contact scores
    0; only forward_flight_success scores +10 (once). miss=-3 on any other
    normal (non-timeout) termination. control_cost unchanged in form, now
    integrated across the whole episode (pitch + contact + flight)."""

    forward_flight_success: float = 10.0
    miss: float = 3.0
    control_cost: float = 0.2


@dataclass(frozen=True)
class ForwardCarryRewardWeights:
    """forward-carry-v1 (I-07c-score, docs/design/BATTING-QUALITY-AND-SWING.md
    section 1). Named and versioned separately from batted-ball-v1 -- never
    silently mixed with it (CLAUDE.md reward-versioning discipline). Always
    computed alongside batted-ball-v1 (see BaseballB1Env._info()'s
    "forward_carry_v1" key) so the two can be compared on identical
    episodes, but batted-ball-v1 remains the reward actually returned by
    step() until a caller explicitly opts in via reward_version=
    "forward-carry-v1". RL training on this reward has not started.

    On a normal (non-timeout, non-out-of-bounds) termination: outcome =
    outcome_scale * batting_score if scoring_valid else -miss_penalty.
    control_cost is the same time-integrated -0.2*(u_swing^2+u_tilt^2)dt as
    batted-ball-v1 (unchanged, per spec). Timeout/out-of-bounds endings
    (status="incomplete") get neither the outcome reward nor the miss
    penalty -- only the already-accrued control cost is kept. The old
    contact/gate +10 (forward_flight_success) is intentionally NOT included
    here to avoid double-paying it alongside the new outcome term.
    """

    outcome_scale: float = 0.1
    miss_penalty: float = 3.0
    control_cost: float = 0.2


def compute_scoring(
    *,
    end_reason: str | None,
    incomplete_end_reasons: frozenset[str],
    first_landing_xyz: np.ndarray | None,
    first_contact_ball_pos: np.ndarray | None,
    exit_velocity: np.ndarray | None,
    recontact_count: int,
    prolonged_contact: bool,
    home_reference_xy: np.ndarray = HOME_REFERENCE_XY,
) -> dict[str, Any]:
    """I-07c-score (docs/design/BATTING-QUALITY-AND-SWING.md section 1).
    Pure function of already-recorded episode state -- reads no mutable
    physics state itself, so it is safe to call multiple times per step
    without side effects. `incomplete_end_reasons` is the caller's set of
    end reasons meaning "landing was never observed" (timeouts / leaving
    the safety bound while still in flight), passed in rather than imported
    so this module has no dependency on envs.baseball_b1_env's END_* names."""
    landing_xy = first_landing_xyz[:2].copy() if first_landing_xyz is not None else None

    carry_distance_m = None
    if landing_xy is not None and first_contact_ball_pos is not None:
        carry_distance_m = float(np.linalg.norm(landing_xy - first_contact_ball_pos[:2]))

    landing_range_from_home_m = None
    if landing_xy is not None:
        landing_range_from_home_m = float(np.linalg.norm(landing_xy - home_reference_xy))

    if end_reason is None:
        status = None
    elif end_reason in incomplete_end_reasons:
        # Landing was never observed (truncated or flew past the safety
        # bound while still in flight) -- undetermined, not a 0-distance
        # miss. Distinct from a definite failure below.
        status = "incomplete"
    else:
        status = "complete"

    scoring_valid = False
    if (
        status == "complete"
        and landing_xy is not None
        and exit_velocity is not None  # confirmed clean separation
        and float(exit_velocity[0]) > 0.0
        and recontact_count == 0
        and not prolonged_contact
    ):
        x_rel = float(landing_xy[0] - home_reference_xy[0])
        y_rel = float(landing_xy[1] - home_reference_xy[1])
        scoring_valid = x_rel > 0.0 and abs(y_rel) <= x_rel

    if status == "complete":
        batting_score = carry_distance_m if (scoring_valid and carry_distance_m is not None) else 0.0
    else:
        batting_score = None  # incomplete or episode still in progress: undetermined

    return {
        "status": status,
        "carry_distance_m": carry_distance_m,
        "landing_range_from_home_m": landing_range_from_home_m,
        "scoring_valid": scoring_valid,
        "batting_score": batting_score,
    }


def compute_reward_terms(
    *,
    weights: RewardWeights,
    forward_carry_weights: ForwardCarryRewardWeights,
    swing_ctrl: float,
    tilt_ctrl: float,
    end_reason: str | None,
    forward_flight_success: bool,
    timeout_flight_reason: str,
    miss_end_reasons: frozenset[str],
    actual_substep_duration_s: float,
    scoring: dict[str, Any],
    reward_version: str,
) -> tuple[float, dict[str, float], dict[str, Any], dict[str, float]]:
    """Combine `scoring` (see compute_scoring) with both reward weight
    profiles into batted-ball-v1 and forward-carry-v1 term dicts, and select
    the active scalar reward per `reward_version`. `miss_end_reasons` and
    `timeout_flight_reason` are passed in (rather than imported) for the
    same reason as compute_scoring's `incomplete_end_reasons`."""
    success = float(
        end_reason is not None and forward_flight_success and end_reason != timeout_flight_reason
    )
    miss = float(end_reason in miss_end_reasons and not forward_flight_success)
    control_cost = (swing_ctrl**2 + tilt_ctrl**2) * actual_substep_duration_s

    reward_terms = {
        "forward_flight_success": weights.forward_flight_success * success,
        "control_cost": -weights.control_cost * control_cost,
        "miss": -weights.miss * miss,
    }

    if scoring["status"] == "complete":
        if scoring["scoring_valid"]:
            fc_outcome = forward_carry_weights.outcome_scale * scoring["batting_score"]
        else:
            fc_outcome = -forward_carry_weights.miss_penalty
    else:
        # Not done, or truncated/out-of-bounds before landing: no outcome
        # reward and no miss penalty, only the control cost already spent
        # (docs/design/BATTING-QUALITY-AND-SWING.md section 1: "외부
        # truncation에는 outcome reward/실패 벌점을 지급하지 않고 소모된
        # 제어비용만 유지한다").
        fc_outcome = 0.0
    forward_carry_reward_terms = {
        "outcome": fc_outcome,
        "control_cost": -forward_carry_weights.control_cost * control_cost,
    }

    if reward_version == "forward-carry-v1":
        active_terms = forward_carry_reward_terms
    else:
        active_terms = reward_terms
    return float(sum(active_terms.values())), reward_terms, scoring, forward_carry_reward_terms

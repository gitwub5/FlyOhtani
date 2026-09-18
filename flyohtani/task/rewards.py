"""What counts as doing well. Three versions, in the order PLAN sets them.

The reward is the research decision most able to produce a result that looks
good and means nothing, so each version says what it pays for, what it
refuses to pay for, and how it could be gamed.

    contact-v1    did the bat touch the ball
    direction-v1  ... and did the ball go into fair territory
    carry-v1      ... and how far into it

They stack: a later version pays everything an earlier one does, so a policy
trained under one is not starting from zero under the next. Reward is given
once, at the end of an episode -- there is nothing to say per frame that is
not already in the outcome.

WHAT NONE OF THEM PAY FOR, deliberately:

  swinging          a swing that misses scores exactly what standing still
                    scores. Paying for effort is how a policy learns to
                    flail.
  being early       nothing rewards committing sooner; the only thing that
                    matters is the ball.
  the bat's speed   it would be easy to pay for a fast swing and call it
                    power, and a policy would then swing hard at everything.
                    Exit speed is already inside carry.
"""
from __future__ import annotations

from collections.abc import Callable

from flyohtani.task.outcome import Outcome

CARRY_SCALE_MM = 30.0
"""Carry that scores 1.0 in carry-v1. Measured, not guessed: the scripted
swing's best fair balls land around 30 mm, so the scale sits where good
contact already reaches rather than somewhere a policy can never get to."""


def contact_v1(outcome: Outcome) -> float:
    """1 for touching the ball, 0 otherwise.

    Gameable by: nothing available to the policy -- the bat is where the
    swing puts it, and the timing window is about a millisecond. This is the
    version to start on because it is the one a random policy almost never
    stumbles into (the scripted baseline connects on 1 frame in 32)."""
    return 1.0 if outcome.contact else 0.0


def direction_v1(outcome: Outcome) -> float:
    """1 for contact, 2 for contact into fair territory.

    Gameable by: hitting weak fair balls, which is exactly what the scripted
    swing does (0.5 mm dribblers count the same as 30 mm line drives). That
    is why carry-v1 exists."""
    if not outcome.contact:
        return 0.0
    return 2.0 if outcome.fair else 1.0


def carry_v1(outcome: Outcome) -> float:
    """1 for contact, +1 for fair, +carry/30 mm for distance, uncapped.

    Gameable by: launch angle. A ball hit almost straight up carries far in
    this scene because there is no drag and nothing catches it -- the
    measured best (84 mm) is a towering fly. Until a fielder or a hang-time
    penalty exists, a high score here means "far", not "a hit"."""
    if not outcome.contact:
        return 0.0
    score = 1.0
    if outcome.fair:
        score += 1.0 + (outcome.carry_mm or 0.0) / CARRY_SCALE_MM
    return score


REWARDS: dict[str, Callable[[Outcome], float]] = {
    "contact-v1": contact_v1,
    "direction-v1": direction_v1,
    "carry-v1": carry_v1,
}
"""Named and versioned, because a reward that changes without its name
changing makes every earlier number unreadable."""


def get(name: str) -> Callable[[Outcome], float]:
    if name not in REWARDS:
        raise KeyError(f"unknown reward {name!r}; have {sorted(REWARDS)}")
    return REWARDS[name]

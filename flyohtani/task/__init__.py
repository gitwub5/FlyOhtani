"""The task: what the policy sees, what it may do, and when an episode ends.

`observation.py` is the policy-facing contract (the leak rules live there).
`env.py` runs an episode against `world.rollout`'s physics.

The reward is NOT here yet. PLAN's Phase 5 versions it in three steps
(contact-v1 -> direction-v1 -> carry-v1) and none of them are chosen, so the
env returns 0.0 and hands the outcome to the caller instead of inventing one.
"""

"""ENV-002 B1 support modules split out of envs/baseball_b1_env.py (R-02,
docs/implementation/REFACTOR-PLAN.md): course geometry/timing config in
`courses.py`, pure scoring/reward computation in `reward.py`. `BaseballB1Env`
keeps orchestrating reset/step and MuJoCo substep event ordering itself --
only the independent, side-effect-free calculations and their config moved
here. `envs/baseball_b1_env.py` re-exports every name that used to live at
its own top level, so no other file's imports needed to change.

This package is B1-specific. ENV-001 (`envs/fly_batter_env.py`) and B0
(`envs/baseball_env.py`) have their own separate `RewardWeights` and are
untouched -- the three environments are staged baselines, not variants of a
shared engine (docs/implementation/REFACTOR-PLAN.md R-02).
"""

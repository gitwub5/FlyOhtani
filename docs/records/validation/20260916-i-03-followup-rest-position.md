## 2026-09-16 — I-03 follow-up: "batter" rest position attempt, and why it isn't enough

User request: move the swing limb's rest position to a "batter-like" cocked-back
stance, away from the ball's path, since the baseline comparison above found a
motionless limb intercepts 100% of the time. Changed: `envs/fly_batter_env.py`
(new `SWING_REST_ANGLE = 1.1` constant, used in `reset()` instead of the old
hardcoded `-0.75`), `controllers/scripted.py` (rewritten to swing from the new
rest angle: `swing_gain=-1.0`, `reset_angle=1.0`, since decreasing the hinge
angle from +1.1 sweeps toward the interception zone).

### Investigation: was the actuator too weak to swing at all?

An initial open-loop test (sustained max torque from `qpos=-1.35` for 1.6s)
showed almost no movement, suggesting the actuator (`gear=0.01`) might be too
weak to matter. This was a testing artifact, not a real defect: `-1.35` is
right against the hinge's `range="-1.4 1.4"` limit, so the joint was pinned
against its hard stop. Repeating the same test starting at `qpos=1.2` (away
from any limit) showed the limb sweep from +1.2 to -1.2 rad in under 0.5s under
sustained torque — the actuator is not the bottleneck. No change made to
`gear`.

### Command

```bash
python -c "... sweep SWING_REST_ANGLE over 11 values from -1.4 to +1.3,
run 30 seeded episodes each with an all-zero action, measure hit rate ..."
```

### Result: every reachable rest angle still gets ~100% hit with zero action

| rest angle (rad) | motionless (`none`) hit rate over 30 episodes |
| --- | --- |
| -1.4, -1.2, -0.9, -0.6, -0.3, 0.0, 0.3, 0.6, 0.9, 1.1, 1.3 | **1.000 for all 11** |

Root cause (confirmed analytically): the gravity-compensated launch (I-03's
main fix) requires a large initial vertical velocity to land exactly on the
fixed target `(0.08, 0, 0.52)` at `t=flight_time`. For the current
`ball_z∈[0.45,0.65]` / `flight_time∈[0.72,0.95]s` ranges, computed apex height
ranges **1.12–1.69 m** — far above both the target and the swing limb's
maximum reach (hinge at `z≈0.39`, arm length `0.58` ⇒ max reach `z≈0.97`). The
hinge is only `~0.143 m` from the exact target point (`sqrt(0.06²+0.13²)`),
which is much smaller than the arm's `0.58 m` length, so the target lies well
inside the arm's full reach circle at every angle the arm can take. Combined
with the trajectory's final descent sweeping through a range of directions
relative to the hinge as it approaches the target (varying by seed), a static
arm anywhere in its ±1.4 rad range ends up crossing the ball's path.

**Conclusion:** repositioning the *rest angle* cannot by itself make the task
discriminate control skill, regardless of which angle is chosen — this is a
task/environment **geometry** issue (target-to-hinge distance vs. arm length
vs. launch-arc height), not fixable by the rest-position change alone. The
`SWING_REST_ANGLE=1.1` + rewritten `ScriptedSwingController` changes are kept
(a genuine "cocked back, must swing" starting stance, and still the literal
change requested), but do not yet resolve the underlying discrimination
problem. Candidate real fixes (not implemented, need a design decision):
narrow the launch-arc height (tighter `flight_time`/height ranges), move the
target point farther from the hinge, or give the limb more reach/DOF margin
to clear the corridor. Recorded in `docs/implementation/WORK_PACKAGES.md`.

### Command

```bash
pytest tests/ -q   # 8/8 passed (added test_reset_starts_the_limb_at_the_cocked_back_rest_angle)
ruff check envs/ controllers/ demos/ tests/   # clean (pre-existing brian2_stdp_controller.py issues untouched)
```

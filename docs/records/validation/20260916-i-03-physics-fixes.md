## 2026-09-16 — I-03 physics defect fixes and baseline comparison

Changed: `envs/fly_batter_env.py` (rewritten), `envs/assets/fly_batter.xml` (`ball_free` joint damping override), `demos/record_episode.py` (rewritten: fixes a `None`-vs-`np.nan` bug and adds `--controller {scripted,none,random,all}`), new `tests/test_fly_batter_env.py`.

### Command

```bash
pytest tests/ -v
```

### Result

Passed, 7/7. Each test targets one audited defect with a deterministic setup (white-box manipulation of `env.data`/`env.model`, not reliant on any controller's behavior):

- `test_gravity_compensated_launch_reaches_target_without_limb_interference` — with limb collision disabled (`geom_contype`/`conaffinity=0`), a zero-action flight from `ball_z=0.55` reaches within 0.05 m of the fixed target `(0.08, 0, 0.52)` at `flight_time=0.8s`, and never drops within 0.05 m of the ground. **This only passed after also fixing the XML** (see below) — the launch-velocity formula alone was not sufficient.
- `test_no_double_hit_reward_on_repeated_contact` — forcing sustained ball/limb contact confirms `hit_success` reward is granted exactly once (first control step), zero on any later step even though the two-return-value contract (`terminated=True`) means a real caller wouldn't call `step()` again.
- `test_point_velocity_is_in_m_per_s_and_scales_with_lever_arm` — with the hinge spinning at a known `omega`, `_point_velocity` at two different radii from the hinge axis returns speeds within 20% of `omega*r`, confirming it does not reproduce the old bug (summing the ball's m/s speed with the limb's raw rad/s).
- `test_ground_contact_terminates_with_distinct_end_reason` — a ball forced near the ground with downward velocity (limb collision disabled) terminates with `end_reason="ground_contact"`, `hit=False`, and a negative `miss` reward term. Previously ground contact was never checked at all.
- `test_control_cost_matches_action_squared_and_is_isolated` — a single mid-episode step with `action=0.6` yields `reward_terms["control_cost"] == -weight * 0.6**2` exactly, with `miss`/`hit_success` at 0 (confirms no cross-contamination from removing the timing-based term).
- `test_timing_error_missing_reason_when_no_contact` — with limb collision disabled, a full episode (ends via ground/pass/timeout) reports `timing_error=None`, `timing_error_missing_reason="no_contact"`.
- `test_timing_error_defined_after_hit_when_zone_crossing_detected` — a two-phase setup (cross `ZONE_X` with limb disabled, then re-enable and force contact at the recorded limb position) confirms `timing_error` is a finite `>=0` value once both a zone-crossing and a hit are recorded.

### Finding: gravity-compensated launch formula alone was insufficient

The `<default><joint damping="0.02".../></default>` block in `envs/assets/fly_batter.xml` cascaded onto the ball's own `ball_free` joint (`model.dof_damping` was `[0.02]*7`, all 7 DOFs including the ball's 6 free-joint DOFs), applying artificial viscous drag to a body that should fly freely under gravity alone. With this damping present, `test_gravity_compensated_launch_reaches_target...` failed by ~0.12 m even with the correct ballistic-compensation formula. Fixed by adding `damping="0"` directly on the `ball_free` joint (overriding the class default, which is evidently meant for the actuated `swing_hinge`, not the ball). After this, the same test passes with <0.05 m error. This was not in the original P0/P1 audit list — discovered while verifying the gravity fix.

### Command

```bash
python demos/record_episode.py --controller all --episodes 50 --seed 0
```

### Result (measured, not a target)

All three baselines — `scripted`, `none` (always zero torque), and `random` (uniform random action each step) — score **hit_rate=1.000 across 50/50 episodes each**, under matched reset conditions (same seed sequence, same observation/action interface via `--controller all`). `end_reasons` is uniformly `{"hit": 50}` for all three.

**This is a new finding, not previously documented**: before the gravity fix, hit_rate was 0/5 for `scripted` because the ball crashed into the ground before reaching the swing zone (I-01's measured -2×10⁷ reward blowup). After the gravity fix, the ball reliably reaches the fixed target point `(0.08, 0, 0.52)`, but the swing limb's geometry at its *rest* angle (`-0.75` rad, unmoving) already occupies enough of the airspace between the ball's approach corridor and the target that it intercepts the ball regardless of control input. Measured static-geometry check: the closest point on the rest-position limb capsule to the exact target point is ~0.158 m away (capsule radius + ball radius = 0.063 m contact threshold), so contact isn't happening exactly *at* the target — it's happening somewhere along the ball's parabolic approach path, which the 0.58 m-long capsule spans a wide enough arc to intercept.

**Consequence:** the environment currently cannot discriminate control/timing skill — a motionless arm "solves" it as reliably as any active controller. This is a task-design issue (arm rest position / fixed target point), not a metric or physics-correctness bug, and is left unfixed pending a deliberate decision (see `docs/implementation/WORK_PACKAGES.md` I-03's "새로 발견해 미해결로 남긴 항목").

### Command

```bash
ruff check envs/ demos/ tests/
```

### Result

Passed, clean, after fixing import-order/unused-variable nits in the new/changed files (auto-fixed via `ruff check --fix` plus 2 manual nits). The 3 remaining repo-wide `ruff check .` findings are pre-existing issues in `controllers/brian2_stdp_controller.py`, untouched by this work (out of I-03 scope).

### Notes

This fixes the environment-level defects I-03 listed and produces the first reproducible deterministic-scenario evidence for each. It does **not** establish that the task (ball interception) is meaningful as currently configured — see the baseline-comparison finding above. Physical realism of the fly/limb/ball scale is still not claimed (per existing README wording).

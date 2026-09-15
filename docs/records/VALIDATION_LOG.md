# Test Log

Record command results here so experiment state remains recoverable.

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

## 2026-09-16 — I-01 environment setup and first runtime verification

Interpreter: `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11` (Python 3.11.5, CPython, macOS-26.6.2-arm64-arm-64bit). Chosen per `docs/PLAN.md` D07. Project-dedicated venv created at `.venv/` (previously the shell's active `python3` resolved to an unrelated project's Python 3.9.6 virtualenv, which does not satisfy `pyproject.toml`'s `>=3.10`).

### Command

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Result

Passed. Core deps (`gymnasium==1.3.0`, `mujoco==3.13.0`, `numpy==2.4.6`, `PyYAML==6.0.3`, `matplotlib==3.11.2`) and dev deps (`pytest==9.1.1`, `ruff==0.16.7`) installed without conflicts. Full pinned set recorded in `requirements-lock.txt`. `rl`/`snn` optional extras (stable-baselines3, torch, brian2) were not installed in this pass — out of scope for I-01's core verification.

### Command

```bash
python -c "import envs, controllers, encoders, train, analysis, demos"
# plus explicit per-submodule imports, including controllers.brian2_stdp_controller
```

### Result

Passed. All 6 top-level packages and every submodule import without error, including `controllers.brian2_stdp_controller` despite brian2 not being installed (confirms it is interface-only, per existing docs — no top-level `import brian2` yet).

### Command

```python
import mujoco
model = mujoco.MjModel.from_xml_path("envs/assets/fly_batter.xml")
data = mujoco.MjData(model)
mujoco.mj_step(model, data)
```

### Result

Passed — first actual MuJoCo runtime load and physics step in this project (previously only XML-syntax-checked, never loaded by the MuJoCo runtime). `nq=8 nv=7 nu=1 nbody=4`, one step advances `data.time` to `0.002` (confirms `model.opt.timestep=0.002`, so `max_steps = int(1.6/(0.002*5)) = 160` in `FlyBatterEnv`).

### Command

```python
from envs.fly_batter_env import FlyBatterEnv
env = FlyBatterEnv()
obs, info = env.reset(seed=0)
# 20 random-action steps
```

### Result

Passed — first successful Gymnasium `reset`/`step` cycle. `obs.shape=(11,)`, `action_space=Box(-1,1,(1,))`. No exceptions, no NaN.

### Command

```bash
python -m demos.record_episode  # internally: FlyBatterEnv + ScriptedSwingController, 5 episodes, seeds 0-4
python demos/record_episode.py --episodes 3 --render none
```

### Result

Ran to completion without crashing (measured, not a target number): scripted controller scored **0/5 hits** across 5 episodes (160 steps each, terminates only on contact or `max_steps`/ball-passed truncation). `demos/record_episode.py --episodes 3` produced episode rewards on the order of **-2×10⁷**, far larger in magnitude than the -20..-25 range seen in the direct 20-step random-action check above. Root cause not investigated further here (out of scope for I-01) — the `timing_error` reward term divides by ball x-velocity (`envs/fly_batter_env.py:_time_to_swing_zone`) and is only guarded for `abs(vx) < 1e-6`; under the known uncompensated-gravity trajectory (`docs/records/PROJECT_AUDIT_2026-09-16.md` P0) the ball likely crosses low-`vx` states after ground contact, which is consistent with this magnitude. This is corroborating measured evidence for I-03, not a newly diagnosed bug; no fix applied.

### Command

```bash
pip install build && python -m build --wheel
```

### Result

Passed. All 6 declared packages (`envs`, `controllers`, `encoders`, `train`, `analysis`, `demos`) and `envs/assets/fly_batter.xml` are present in the built wheel — package-data inclusion for the new asset is intact.

### Command

```bash
pytest --collect-only -q
ruff check .
```

### Result

`pytest`: runs, 0 tests collected (`tests/` does not exist yet — expected, no test suite has been written). `ruff`: runs, found 5 pre-existing lint issues in `envs/fly_batter_env.py` (import order, mutable class-attribute default) — not fixed here, out of I-01 scope.

### Notes

This establishes a working, reproducible environment and first-ever runtime execution of the existing scaffold. It does **not** establish physics correctness, learning performance, or that `FlyBatterEnv`'s reward/termination logic is sound — see I-03 in `docs/implementation/WORK_PACKAGES.md` for the known physics defects this run's numbers are consistent with.

## 2026-09-16 — Planning structure review

- Compared SHA-256 fingerprints before/after the documentation changes for all 22 existing Python, XML, TOML and YAML files: identical; no implementation or runtime configuration changes.
- Checked relative Markdown links across 15 root/config/project documents: no missing targets.
- Reviewed active-plan, historical-roadmap, and pending-choice labels for consistency with the Claude implementation handoff.
- These were documentation consistency checks only. No application tests, package installation, physics simulation, or learning experiment was run.

## 2026-09-15–16 — Planning review

- Read 19 Python files, XML, config, package metadata, and project documents.
- Parsed all Python sources with `ast.parse`, without importing dependencies or generating bytecode: 19 passed.
- Current shell inspection: arm64, macOS 26.6.2, Python 3.14.0. NumPy, MuJoCo, Gymnasium, PyTorch, Brian2, SB3 and pytest were absent from this interpreter.
- Memory query `sysctl -n hw.memsize` was denied; available RAM remains unknown.
- Analytic launch check: missing gravity correction causes 2.5428–4.4268 m displacement relative to target over 0.72–0.95 s, assuming free flight. Ground collision was not simulated.
- No local `.git` entry in the project folder. No Git initialization was performed.
- Initial documentation patch was rejected during patch validation; no files changed in that attempt. A revised documentation-only patch was then applied.
- No dependency installation, runtime physics test, external model execution, training, or dataset download was performed.

These checks establish source findings, not physics correctness or model performance.

## 2026-09-15

### Command

```bash
python3 -m compileall envs controllers encoders train analysis demos
```

### Result

Passed. All Python source files compiled successfully.

### Notes

The local shell did not provide `python`; `python3` was used instead.

## 2026-09-15

### Command

```bash
python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject ok')"
```

### Result

Passed. `pyproject.toml` parsed successfully.

## 2026-09-15

### Command

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('envs/assets/fly_batter.xml'); print('xml ok')"
```

### Result

Passed. The MuJoCo XML file is well-formed XML.

### Limitations

This only checks XML syntax. It does not validate MuJoCo semantics or runtime physics behavior.

## 2026-09-15

### Command

```bash
python3 -c "import sys; print(sys.version); import importlib.util; print('mujoco', importlib.util.find_spec('mujoco')); print('gymnasium', importlib.util.find_spec('gymnasium'))"
```

### Result

`mujoco` and `gymnasium` were not installed in the current environment.

### Next Runtime Test

After installing dependencies:

```bash
pip install -e ".[dev]"
python demos/record_episode.py --episodes 3 --render none
```

# 검증 기록

## 2026-09-16 — I-03b: ENV-001 기반 오류 수정과 검증 (T10)

범위: `docs/implementation/WORK_PACKAGES.md`의 I-03b 1~5, `docs/design/ENV-001-interception.md` 전체, `docs/implementation/VALIDATION.md`의 "물리 회귀의 필수 추가 항목" 8개. 변경 파일: `envs/fly_batter_env.py`(재작성), `envs/assets/fly_batter.xml`(관절 범위, contact exclude, gear), `controllers/scripted.py`(재작성 + `ConstantAngleController` 추가), `controllers/__init__.py`, `demos/record_episode.py`(재작성: held_pose 진단, dev/test seed 분리, Wilson CI), `tests/test_fly_batter_env.py`(22개 테스트로 전면 교체), 신규 `docs/design/ENV-001-calibration.json`.

### 1. 초기 관통·연결부 자기충돌 (ENV-001 항목1-2)

- XML에 `<contact><exclude body1="agent_body" body2="swing_limb"/></contact>` 추가. thorax-limb 연결부 겹침(REVIEW가 찾은 dist=-0.0567m)만 명시적으로 제외했고, 다른 모든 pair(공-지면, 공-팔, 공-몸통, 팔-지면)는 그대로 유지.
- 힌지 관절 범위를 `[-1.4,1.4]`→`[-1.4,0.65]`로 좁혔다(REVIEW가 찾은 +1.1rad에서의 지면 관통 -0.1449m 재발 방지).
- 준비각을 0.50rad으로 변경(ENV-001 후보값). 확인: 준비각에서 접촉 0건, 지면 여유 0.094m(요구 0.02m 이상 충족).
- `reset()`에 `_check_no_initial_penetration()`을 추가해 `contact.dist < -1e-6`이면 즉시 `RuntimeError`. 조용히 넘어가지 않는다.

**검증:** `test_reset_never_starts_from_a_penetrating_state`(seed 0-19), `test_prep_pose_has_ground_clearance_margin`, `test_no_ground_penetration_across_the_full_joint_range`(관절범위 전체 0.05rad 간격 스윕), `test_thorax_limb_connector_overlap_is_excluded_not_penetrating`(관절범위 전체) — 모두 통과.

### 2. zero_torque/held_pose/actuated 구분과 구동 재측정 (ENV-001 항목3-5)

REVIEW의 지적대로 **zero_torque는 정지 상태가 아니다** — 중력이 가벼운 팔에 토크를 가해 0.35초 만에 준비각(0.50)에서 0.60rad까지 수동으로 회전한다(측정: `test_zero_torque_held_pose_and_actuated_are_three_distinct_conditions`). held_pose는 매 control step마다 qpos/qvel을 강제로 준비각에 고정하는 별도 진단(진짜 controller 아님)으로 구현했다(`demos/record_episode.py:run_held_pose_episode`).

**충돌 없는 구동 측정값** (공 없음, thorax-limb 제외 외 다른 충돌 유지, damping=0.02/armature=0.001 유지, dt=0.002s, 준비각 0.50→정렬각 -0.264, 기준 0.35s):

| gear | 초기 접촉 | 도달 시각 | 관절한계 반발 | 판정 |
| --- | --- | --- | --- | --- |
| 0.01 | 0 | 도달 못함(1.0s 내) | 없음 | 실패 |
| 0.04 | 0 | 0.548s | 없음 | 실패(기준 초과) |
| **0.08** | 0 | **0.28s** | 없음 | **통과 (최소값 선택)** |
| 0.12 | 0 | 0.202s | 없음 | 통과 |

선택: gear=0.08(가장 작은 통과값), XML에 반영. 전체 기록: `docs/design/ENV-001-calibration.json`. 이전 gear=0.01 측정("0.5초에 2.4rad")은 REVIEW가 지적한 대로 초기 관통의 충돌 반발력이 섞인 결과였음을 재확인 — 관통을 없앤 뒤 gear=0.01은 1.0초 안에 정렬각에 전혀 도달하지 못한다.

**검증:** `test_actuator_reaches_alignment_angle_within_deadline_without_ball`(XML에 반영된 gear=0.08로 재현).

### 3. 목표점·통과 경계 설정 공유 (ENV-001 항목3)

`target=(0.50,0,0.52)`, `pass_x=target_x+0.25=0.75`, `prep_angle=0.50`을 `FlyBatterEnv` 생성자 인자 겸 인스턴스 속성으로 만들어 reset/관측(TTC)/종료판정에서 전부 공유한다. 이전의 `ZONE_X=0.08`/`0.45` 하드코딩은 제거했다. `flight_time_range`도 [0.72,0.95]→[0.40,0.50]로 ENV-001 후보값 적용.

자유낙하 목표 오차(공-팔 충돌 비활성, 15seed 평균, physics substep 단위로 정렬각 시각에 정지):

| dt | 평균 오차 | 최대 오차 | 0.01m 초과 비율(30seed) |
| --- | --- | --- | --- |
| 0.002s(기본값) | 0.0077m | 0.0113m | 13% |
| 0.001s | 0.0069m | 0.0091m | 0% |

dt를 절반으로 줄이면 오차가 악화되지 않고 개선된다(요구사항 충족). 다만 **기본 dt=0.002s에서는 일부 seed(약13%)가 0.01m 기준을 근소하게(최대 1.1mm) 초과한다** — RK4 적분 오차가 아니라 목표 도착시각 T가 physics_dt의 정수배가 아니어서 생기는 정지시점 양자화 잔차다(수정 안 함, 아래 "남은 문제" 참고).

**검증:** `test_gravity_compensated_launch_error_does_not_worsen_when_dt_halves`(15seed, dt 완화 없음 확인 + dt=1ms에서 ≤0.01m).

### 4. substep 사건 순서·종료 분류·타이밍·시간적분 비용 (ENV-001 항목4)

- `step()`의 substep 루프가 **최초 terminal 사건에서 즉시 break**하도록 재작성(이전엔 frame_skip 5회를 항상 다 돌고 사후 판정). 같은 substep에 지면접촉과 hit가 동시에 있으면 지면접촉 우선(보수적 실패 규칙).
- `end_reason ∈ {hit, ground_contact, passed_no_contact, timeout}`; hit/ground_contact/passed_no_contact는 `terminated=True`, timeout만 `truncated=True`(이전엔 passed가 truncated였음 — REVIEW 지적 반영).
- terminal 뒤 `step()` 호출은 `RuntimeError`.
- 타이밍을 재정의: 실제 zone-crossing을 기다리는 대신 `planned_arrival_s`(=reset에서 뽑은 T)를 기준으로 `signed_timing_error_s = contact_time_s - planned_arrival_s`를 계산. hit가 나면 항상 값이 존재한다(이전엔 hit가 조기 종료를 유발해 zone-crossing을 못 봐서 자주 결측이었음).
- 제어비용을 `torque² × 실제 substep 경과시간`으로 재정의(이전엔 매 control step마다 고정 action²만 사용해 control_dt에 의존).

**검증:** `test_ground_and_limb_contact_in_the_same_substep_prioritizes_ground`, `test_first_terminal_event_stops_the_substep_loop_early`(elapsed==1 substep만), `test_mid_substep_contact_within_frame_skip_is_not_missed`, `test_passed_no_contact_is_terminated_not_truncated`, `test_timeout_is_truncated_only`, `test_step_after_terminal_raises_runtime_error`, `test_no_double_hit_reward_on_repeated_contact`(재호출 시 RuntimeError 포함), `test_timing_uses_planned_arrival_and_is_always_present_on_hit`, `test_timing_error_on_a_naturally_launched_hit_not_just_teleported_ball`(순간이동 없이 scripted controller의 실제 10회 발사 중 hit 발생 확인, VALIDATION.md의 "인위적 순간이동 테스트만으로 대체 금지" 충족), `test_timing_missing_reason_when_no_contact`, `test_control_cost_invariant_to_control_dt`(physics_dt=1ms에서 control_dt 5/10/20ms 절대오차 1e-9 이내 일치), `test_point_velocity_matches_omega_cross_r_analytically`(성분별 오차 1e-8 이내).

### 5. baseline 재정의와 dev/test seed 분리 (ENV-001 항목5)

`demos/record_episode.py`에 `zero_torque`/`held_rest`/`random`/`scripted`/`best_constant_angle` 5종을 구현. `DEV_SEEDS=range(20)`(튜닝용), `TEST_SEEDS=range(1000,1100)`(튜닝 미사용, 판정용)로 분리. `RandomController`는 독립 RNG를 쓰므로 다른 controller의 환경 입력을 바꾸지 않음(`test_env_rng_is_independent_of_controller_choice`로 검증).

scripted 컨트롤러는 "남은 도달시간(관측 기반 예측) − 구동 보정시간(0.30s, gear=0.08 측정치+여유)" 트리거로 재작성. `best_constant_angle`은 개발 시드에서 각도 후보(-0.15~-0.40)를 스윕해 **-0.30rad**을 선택(20/20 hit).

**첫 정비 통과 기준 결과 — 시험 시드(1000-1099, n=100, 튜닝에 사용 안 함):**

| baseline | hit | hit_rate | Wilson95% | 기준 | 판정 |
| --- | --- | --- | --- | --- | --- |
| zero_torque | 0/100 | 0.000 | (0.000,0.037) | ≤5% | 통과 |
| held_rest | 0/100 | 0.000 | (0.000,0.037) | =0% | 통과 |
| random | 0/100 | 0.000 | (0.000,0.037) | (scripted-random≥30pp의 분모) | — |
| scripted | 100/100 | 1.000 | (0.963,1.000) | ≥80% | 통과 |
| scripted−random | — | 1.000 | — | ≥30pp | 통과 |
| best_constant_angle(-0.30) | 100/100 | 1.000 | (0.963,1.000) | (참고, 통과 기준 아님) | — |

개발 시드(0-19, n=20)에서도 동일 패턴(zero_torque/held_rest/random=0/20, scripted=20/20). **ENV-001의 모든 "첫 정비 통과" 기준을 시험 시드에서 충족했다.**

### 종합

`pytest tests/ -q` → **22 passed**. `ruff check envs/ controllers/ demos/ tests/` → clean. `docs/implementation/VALIDATION.md`의 "물리 회귀의 필수 추가 항목" 8개 전부 대응하는 테스트를 추가했다(위 절별로 매핑).

### 남은 문제 (수정 안 함, 다음 논의 필요)

1. 기본 물리 해상도(dt=0.002s)에서 자유낙하 목표 오차가 일부 seed(약13%)에서 0.01m 기준을 근소하게(최대1.1mm) 초과한다. dt=1ms에서는 전부 충족. 정지시각 양자화 잔차이며 RK4 오차가 아니다. dt를 기본값으로 낮출지, 허용오차를 조정할지는 설계 결정이 필요하다.
2. `best_constant_angle=-0.30`이 시험 시드 100/100을 전부 맞힌다 — ENV-001이 스스로 명시한 "고정 목표점의 한계"를 재확인한 것으로, 새로운 문제가 아니다. ENV-001 문서가 요구하는 대로, 이 결과를 "타이밍 학습"의 증거로 사용하려면 목표 위치/도달시간을 바꾸는 새 규약이 먼저 필요하다(수정 안 함, 범위 밖).
3. "always max torque" 정책 baseline(ENV-001의 향후 규약에서 언급)은 구현하지 않았다 — 첫 정비 통과 기준에는 불필요.
4. `held_rest`는 매 control step(10ms)마다 qpos/qvel을 재고정하는 근사 구현이다. 한 control step 안의 물리 substep 5회 동안 미세하게 드리프트할 수 있으나 관측된 hit_rate에는 영향이 없었다(0/100).
5. I-02(설정·기록 계약)는 여전히 미구현. I-04/I-05(실제 회로, EXP-001 실행)는 이번 작업과 독립이며 착수하지 않았다. 강화학습 훈련도 시작하지 않았다(사용자 지시).

## 2026-09-16 — ENV-002 계획 연결 확인

- MLB 공식 필드/릴리스 설명과 공식 링크의2025 규칙집을 참조하고, 설계용 preset과 구분했다.
- Markdown24개의 상대 링크 검사: 누락0. I-07/ENV-002/VIZ/PLAN/상태·설정 인계를 연결했다. 문서만 수정, 신규 환경 실행·학습은 하지 않았다.


## 2026-09-16 — 문서 정합성 확인

- 루트/설정/docs의 Markdown23개에서 상대 링크 검사: 누락0. archive의 이동 전 링크도 수정.
- EXP-001 1.0, ENV-001 1.0, VIZ-001, I-01~I-06과 T01~T10의 참조를 대조했다.
- Git 변경 파일 확인: 문서만 변경. 기존 소스/XML/YAML/TOML/lock에는 차이 없음. 신경 실험·새 환경 구현·시각화 실행은 수행하지 않았다.

## 2026-09-16 — Codex 독립 검토

- 기준 commit e2447bb. `.venv/bin/python -m pytest tests/test_fly_batter_env.py -q`:8 passed in0.23s.
- reset 직후 contact 검사 및 seed0/frame_skip1/zero torque 재현: ground–limb dist=-0.1449m, thorax–limb dist=-0.0567m; +1.1rad→약0.712s hit 때 -1.2466rad. 재현 절차와 한계는 [REVIEW](REVIEW_2026-09-16.md).
- in-memory 모델에서 thorax/ball collision을 제외한 actuator 분리 측정: 최대 음의 입력0.5s, q0=0→-0.03173rad, q0=0.5→0.44742rad. 원본 XML/gear는 수정하지 않았다.
- ENV 후보의 고정 준비각+0.5/목표(0.5,0,0.52)/27개 표본 궤적에서 최소 표면 여유 약0.166m. 전체 동역학/baseline 성공률 검증 아님.
- 과거 아래 기록의 ‘geometry confirmed’·‘motionless’ 해석은 최신 검토로 정정한다. 이전 측정값은 보존한다.


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

# KC-01a-validation — dt 수렴·정착·에너지·타이밍 보완 결과

2026-09-17 · 기준 문서: `docs/tasks/KC-01a-VALIDATION-AND-VISION.md` (A절),
후속 사용자 지시(발산 원인 분리 A6-A8, 방향 계약, `same_direction_staggered`
수용 검증 A9, 몸통 선행 메커니즘 검증 A10-A12) · 후속 정정 대상:
`docs/records/KC-01a-COMPARISON.md`(원본 보존, 상단에 이 문서 링크 추가) ·
원자료: `docs/records/evidence/KC-01a-{dt-convergence, settle-diagnostics,
energy-validation, timing-window, noball-dt-isolation,
contact-only-dt-isolation, constraint-decomposition, same-direction-search,
same-direction-dt-convergence, same-direction-acceptance,
torso-lead-analysis, torso-lead-handoff-search,
torso-lead-handoff-validation, torso-lead-handoff-search-v2,
torso-lead-handoff-validation-v2}.json` · 재현: `scripts/kc01a_dt_convergence.py`
→ `scripts/kc01a_settle_diagnostics.py` → `scripts/kc01a_energy_validation.py`
→ `scripts/kc01a_timing_window.py` → `scripts/kc01a_noball_dt_isolation.py`
→ `scripts/kc01a_contact_only_dt_isolation.py` →
`scripts/kc01a_constraint_decomposition.py` →
`scripts/kc01a_same_direction_search.py` →
`scripts/kc01a_same_direction_dt_convergence.py` →
`scripts/kc01a_same_direction_acceptance.py` →
`scripts/kc01a_torso_lead_analysis.py` →
`scripts/kc01a_torso_lead_handoff_search.py`(참고, 무효 후보) →
`scripts/kc01a_torso_lead_handoff_validation.py`(참고, 무효 후보) →
`scripts/kc01a_torso_lead_handoff_search_v2.py` →
`scripts/kc01a_torso_lead_handoff_validation_v2.py` · 회귀 테스트:
`tests/test_baseball_kc01a_controller.py` · 관련: `docs/design/
KC-01a-DIRECTION-CONTRACT.md`(회전 방향 계약, 새 조건 설계 규칙,
motion-triggered handoff 모드, 유효성 검사)

## 현재 판정 (요약)

**KC-01a의 조건 간 우위 비교는 여전히 결론 내릴 수 없다.** dt 수렴은 기존 4개
조건 중 1개(`torso_swing_with_arm_hold`)만 통과했고, 그 1개는 물리적으로
일관되게 "유효 타구를 만들지 못한다"는 음성 결과다. 나머지 3개 조건은
수렴하지 않아 그 수치(점수·발사각·유효 여부)를 신뢰할 수 없다 — 특히 이전에
"최고 성적"이라던 `staggered_swing_and_torso`는 정밀한 dt에서 **무효로
뒤집힌다.** 정착은 관찰 시간을 늘리자 3개 조건에서 명확히 확인됐고, 에너지
잔차는 관절한계 반력을 포함하자 대부분 설명됐다. 시각 정책 통합 여부는 이
결과들을 근거로 보류한다.

**후속 원인 분리(A6-A8, 이번 갱신)로 세 가지가 바뀌었다**: (1) A2의 "접촉의
이산화 민감도로 추정"은 더 이상 추정이 아니다 — 구동만 분리하면 완벽히
수렴하고, 동일한 충돌 직전 상태에서 접촉만 재생해도 전체 실행과 같은 패턴으로
발산한다는 것을 직접 확인했다(§A6). (2) A3의 "정착 실패와 유효 타구 실패가
같은 근본 원인(gear 대비 관성 과다)일 가능성이 높다"는 추측은 관절한계
활성 시점·에너지 기여도 측정으로 더 구체적인 근거를 얻었지만 여전히 gear를
직접 바꿔 확인하지는 않았다(§A7). (3) `simultaneous_swing_and_torso`의 에너지
잔차(A4에서 "원인 미상"이라 남겼던 5.7~10.8%)는 dt를 하나 더 세분화해 보니
실제로는 1차 절단오차처럼 깨끗이 줄어든다 — 미상이 아니라 평범한 수치오차였다
(§A7). 별도로, **사용자가 지적한 `simultaneous`/`staggered`의 몸통-배트
역회전(counter-rotation) 문제**는 `docs/design/KC-01a-DIRECTION-CONTRACT.md`에
정리했고, 부호를 맞춘 새 조건(`same_direction_staggered`)이 **처음으로 실제
타구가 발생하면서 동시에 dt 수렴도 통과**했다(§A8) — 다만 협응 우위를
결론내리기엔 아직 이르다(정착·에너지·타이밍 재검증 전).

**추가 갱신(A9-A12, `same_direction_staggered` 수용 검증과 몸통 선행 메커니즘,
이번 갱신)**: `same_direction_staggered`의 수용 검증 결과 **torso 축이 정착
기준을 충족하지 못한다**(§A9) — dt/그립/타이밍 성공구간은 확인했지만 이
자체만으로 시각 실험의 물리 기준선으로 채택하기엔 부족하다. 에너지 잔차를
다시 계산하며, XML이 `integrator="RK4"`인데도 이전 보고가 "semi-implicit
Euler 절단오차"라고 잘못 설명했던 부분을 정정했다(§A9) — 실제 원인은
스크립트 자신의 사후 work 적분(quadrature)이며, RK4가 담당하는 상태(qpos/
qvel) 적분 자체는 이미 거의 완전히 수렴해 있다. 사용자가 영상에서 관찰한
"배트가 먼저 움직이는 것처럼 보인다"는 지적은 **데이터로 확인됐다** —
`same_direction_staggered`의 "몸통 10ms 선행"은 실제 각속도 임계값 교차
시각 기준으로 선행 0초다(§A10). 원인은 몸통-배트가 같은 힌지 사슬에 있어
몸통의 각가속도가 배트(swing) 자유도에 즉시 반작용 각속도를 유도하기
때문이며, 이 반작용이 raw qvel 기반 "시작 시각" 측정 자체를 오염시킨다(§A10).
진짜 제어 수준의 선행(트리거 시점 차이)을 크게 늘리는 새 컨트롤러 모드
(`torso_lead_handoff`, 물리 모션에 연동된 인계)를 추가해 탐색한 결과,
torso_target=0.5/torso_ct=0.33/handoff_fraction=0.5 조건이 dt 수렴·정착
(양 축)·그립 도달성·접촉 침투를 모두 통과한 것처럼 보였고 production dt
점수(6.78m)도 지금까지 KC-01a에서 나온 어떤 값보다 높았다(§A11-A12) —
**이 판정은 이후 철회됐다(§정정, §A15-A18).** 이 후보는 실제로는 몸통(+)과
팔(−)이 반대 방향으로 가속하는 명령이었고, 팔의 명령 변위는 사실상 0
(−0.004rad)이었으며, 양 축의 팔로우스루 목표가 모두 자기 관절 범위 밖이라
"정착"은 능동 제동이 아니라 관절 하드 스톱에 눌린 결과였다 — 유효성 검사
자체(방향 일치·최소 팔 변위·관절 범위 여유)가 빠져 있었기 때문에 이걸
걸러내지 못했다. 검사를 고치고(`controllers/baseball_kc01a.py`의
`validate_same_direction_candidate`, 인계 조건도 절대값 대신 부호 있는
진행량으로 수정) 재탐색한 결과(torso_target=0.25, §A16-A17) 방향·변위·범위·
능동 제동 정착·그립은 통과하는 후보를 찾았지만, **이번엔 dt 수렴에
실패한다** — "유효성 검사를 통과하고, 능동 제동으로 정착하고, 동시에 dt
수렴까지 하는" 후보는 아직 없다(§A18).

## A1. 조건명 재정의와 결론 철회

| 옛 이름 | 새 이름 | 유지 축(P제어, 하드락 아님) |
| --- | --- | --- |
| `arm_only` | `arm_swing_with_torso_hold` | torso(목표 0) |
| `torso_only` | `torso_swing_with_arm_hold` | swing(목표 -1.96) |
| `simultaneous` | `simultaneous_swing_and_torso` | — (tilt만 항상 유지) |
| `staggered` | `staggered_swing_and_torso` | — (tilt만 항상 유지) |

`controllers/baseball_kc01a.py`의 내부 `mode` 문자열(구 이름)은 바꾸지 않았다 —
위 표는 **보고/분석에서 쓰는 이름**이며 코드 동작은 동일하다. **"진짜 lock"이
아니라 컨트롤러의 유지 P제어(gain=50)로 구현했다** — 매 substep qpos/qvel을
강제 초기화하는 방식(`env.set_held_pose()`)을 이전 세션에서 시도했으나, 그
방식은 접촉 동역학을 바꿔 `arm_swing_with_torso_hold`가 어느 타이밍에서도 유효
타구를 못 내게 만들었다(0.03~0.30s 전 구간 재탐색해도 무효) — 매 substep
속도를 지우는 것이 실제 물리를 왜곡한다는 증거이며, 이번에도 하드락을 쓰지
않는다. 유지 축의 액추에이터 일은 0이 아니다(§A4) — 반작용을 억제하려고 실제로
토크를 쓴다.

**철회하는 진술** (`docs/records/KC-01a-COMPARISON.md` §2): "점수/일 비율로
'모터 효과'와 '협응 효과'가 분리된다"는 결론을 철회한다. 유지 축도 일을 하므로
그 비율 자체가 이미 "협응"과 "유지 제어 비용"을 섞고 있었다. 또한 A2 결과로
그 원본 점수들 자체가 dt-수렴되지 않은 값이라 비교의 근거가 되지 못한다.

## A2. timestep 수렴 (최우선) — 4개 중 1개만 통과

physics_dt ∈ {0.00025, 0.000125, 0.0000625}s, control_dt=0.005s 고정.
**REPLAY**(기준 dt에서 기록한 제어 명령을 다른 dt에 그대로 재생, zero-order
hold)와 **INDEPENDENT**(각 dt에서 컨트롤러를 새로 실행) 두 방식 모두 확인했다.
수용 기준(측정 전 고정): 두 가장 미세한 dt에서 event/scoring_valid 동일,
접촉·분리시각 차≤0.5ms, 출구속도 차≤max(0.1m/s,2%), 착지XY 차≤max(0.05m,2%).

| 조건 | dt=0.00025 | dt=0.000125 | dt=0.0000625 | 수렴 |
| --- | --- | --- | --- | --- |
| `arm_swing_with_torso_hold` | 유효, 2.63m | 유효, 2.22m | 유효, 2.12m | ❌ (출구속도·착지 오차 초과) |
| `torso_swing_with_arm_hold` | 무효 | 무효 | 무효 | ✅ |
| `simultaneous_swing_and_torso` | 유효, 0.67m | 유효, 0.51m | 유효, 0.75m | ❌ (비단조, 오차 초과) |
| `staggered_swing_and_torso` | 유효, **3.64m** | **무효** | **무효** | ❌ (판정 자체가 뒤집힘) |

REPLAY와 INDEPENDENT는 서로 거의 일치했다(예: simultaneous dt=0.0000625:
0.7473 vs 0.7473) — 즉 발산의 주원인은 컨트롤러의 상태 피드백이 아니라 **접촉
물리 자체의 이산화 민감도**다.

**추가 세분화(1/8 dt, 0.00025/8=3.125e-05s)로 원인 구분**:
- `arm_swing_with_torso_hold`: 2.626→2.222→2.119→2.062 — 단조 감소, 감소폭도
  줄어든다(진짜 수렴 중이나 느림). production dt=0.00025의 결과(2.626)는 참값
  추정(~2.0-2.05) 대비 **약 25~30% 이산화 오차**를 품고 있다는 뜻이다.
- `simultaneous_swing_and_torso`: 0.672→0.510→0.747→0.785 — **비단조**. 단순
  절단오차가 아니라 경계 근접에 의한 진짜 민감도(카오스적 거동)로 해석한다.
- `staggered_swing_and_torso`는 dt=0.00025보다 미세한 모든 dt에서 일관되게
  **무효**다 — 즉 이전 "staggered가 최고"라는 결론은 **수렴 전 결과의 인공물**
  이었다.

**결론(수정됨 — 아래 §A6에서 "추정"을 확인으로 바꿨다)**: gear·재료·트리거를
몰래 바꾸지 않았다. 수렴 실패 원인은~~접촉의 이산화 민감도(이미 알려진 B1의
±5ms 취약성과 같은 계열의 문제로 추정)~~ **접촉(충돌) 계산 자체의 이산화
민감도다 — §A6에서 구동-전용 실행과 충돌-전용 재생으로 분리해 직접 확인했다,
더 이상 유추가 아니다.** 최소 수정안은 §A8·§다음 단계 참고.

## A3. 정착 관찰 (착지 후 진단 연장)

일반 env의 "terminal 후 step 거부" 계약은 그대로 두고, `env.step()`을 다시
부르지 않는 **별도 진단 러너**(`mj_step`을 직접 호출)로 (1) 착지 후 최소 1.2s
연장 관찰, (2) 배트 충돌을 비활성화한 무공 스윙, 두 경로에서 확인했다. 기준:
제동 시작(accelerate→brake) 후 0.5s 이내 `|qvel|<0.2rad/s`, 이후 **연속** 0.2s
동안 각도 p-p<0.02rad 및 속도 조건 유지(단일 샘플 아님).

| 조건 | 축 | 착지 후 정착시간 | 무공 정착시간 | 판정 |
| --- | --- | --- | --- | --- |
| `arm_swing_with_torso_hold` | swing | 0.395s | 0.236s | ✅ |
| `torso_swing_with_arm_hold` | torso | 미정착(2.32s 관찰해도) | 미정착(1.25s) | ❌ **실제 정착 실패** |
| `simultaneous_swing_and_torso` | torso/swing | 0.410s/0.305s | 0.425s/0.375s | ✅/✅ |
| `staggered_swing_and_torso` | torso/swing | 0.250s/0.210s | 0.271s/0.326s | ✅/✅ |

이전(관찰 창 부족으로 "미확정")과 달리 이번엔 **확정적** 결론이다: 3개 조건은
잘 정착하고, `torso_swing_with_arm_hold`의 torso는 관찰을 2.3초로 늘려도 최종
`|qvel|`이 0.08~0.19rad/s로 여전히 임계값(0.2) 근처를 맴돌 뿐 완전히 정착하지
않는다 — 유효 타구 실패(§A2)와 **같은 근본 원인**(gear=30 대비 관성 35kg가
너무 커 구동력이 부족)일 가능성이 높다는 추측을 §A7이 더 구체화한다(여전히
gear를 실제로 바꿔 확인하지는 않았다 — 추측이 구체화됐을 뿐, 증명은 아니다).

## A4. 에너지 검증

**무공 에너지 잔차** (`torso_body`+`bat_body`+`bat_tilt_body` 부분계, 공은 접촉이
없는 한 역학적으로 분리돼 있어 3×3 질량행렬 부분만으로 정확): Δ(KE+PE) =
W_액추에이터 + W_감쇠 + W_관절한계반력 + 잔차.

| 조건 | Δ(KE+PE) | W_액추에이터 | W_감쇠 | W_관절한계반력 | 잔차(비율) |
| --- | --- | --- | --- | --- | --- |
| `arm_swing_with_torso_hold` | 2.988J | 4.077J | -0.867J | 0 | -0.222J (-5.4%) |
| `torso_swing_with_arm_hold` | 1.516J | 27.568J | -1.003J | -23.89J* | -1.162J (-4.2%) |
| `simultaneous_swing_and_torso` | -0.313J | 2.699J | -2.721J | 0 | -0.291J (-10.8%) |
| `staggered_swing_and_torso` | -0.334J | 13.819J | -2.012J | -12.08J* | -0.064J (-0.5%) |

\* 처음엔 관절한계 반력(`qfrc_constraint`)을 빼먹어 잔차가 **88~91%**에 달했다
— 원인을 추적한 결과 `torso_swing_with_arm_hold`(최대 torso각 0.620rad)와
`staggered_swing_and_torso`(최대 0.633rad)가 실제로 torso의 ±0.6rad 관절
한계를 넘어서고 있었다(follow-through 오버슈트). 이 반력의 일을 포함하자
잔차가 4~9배 줄었다 — **이것은 실제로 존재하는 물리적 에너지 흡수 경로였다.**
`simultaneous`는 관절한계를 넘지 않는데도 잔차가 5.7~10.8%로 가장 크다 —
~~원인 미상으로 정직하게 남긴다~~ **§A7에서 dt를 한 단계 더 세분화(3번째 dt
점)해 보니 이 잔차는 실제로는 order≈1로 깨끗이 줄어든다(0.108→0.057→0.029,
매번 거의 절반) — 평범한 적분(절단) 오차였고, 미상이 아니었다.** dt를
절반으로 하면 잔차도 대체로 절반 가까이 줄어(수렴 방향), `staggered`만
예외적으로 약간 커진다(-0.064→-0.229J, 절대값은 여전히 작음) — **이 비단조성은
§A7의 3-dt 재확인에서도 재현됐다(order 추정치가 음수로 나옴): `staggered`만
유일하게 진짜 절단오차로 설명되지 않는다.**

**공통 예산 비교는 수행하지 않았다.** A4는 "A2 통과 후에만" 공통 W+/피크출력/
토크 한도 비교를 하라고 명시한다. A2가 3/4 조건에서 실패했으므로, 예산을
적용해 제어 일정을 바꾸면 A2의 수렴 확인을 다시 반복해야 한다(문서의 명시적
요구) — 이번 작업 범위에서는 이 반복 사이클을 완료하지 못했다. 각 조건의
무공 W+/피크출력/피크토크 자체는 `docs/records/evidence/
KC-01a-noball-validation.json`(이전 세션)과 이번 `KC-01a-energy-validation.json`에
있으며, 향후 예산 설계의 입력으로 쓸 수 있다.

## A5. 타이밍 성공 구간

수렴한 조건(`torso_swing_with_arm_hold`) 하나에서만 -20~+20ms(1ms 간격, 41개
표본, control_dt=5ms 양자화로 실제 9개 서로 다른 트리거 스텝) 스윕했다:
**41개 전부 무효(성공 구간 0%)** — 원래도 무효였던 결과가 인근 전체에서도
그대로였다는 뜻이다. 나머지 3개 조건은 수렴하지 않은 설정에서 타이밍을 최적화
하지 않는다는 지시에 따라 스윕하지 않았다(연기).

## A6. 발산 원인 분리 — 구동(actuation/integration) vs 접촉(collision) 계산

`scripts/kc01a_noball_dt_isolation.py`와
`scripts/kc01a_contact_only_dt_isolation.py`, 결과
`docs/records/evidence/KC-01a-{noball,contact-only}-dt-isolation.json`.
기존 4개 조건(변경 없음, 진단 기록 보존 — `docs/design/
KC-01a-DIRECTION-CONTRACT.md` §3)에 대해 두 가지를 따로 확인했다:

1. **구동-전용(공-배트 충돌 완전 비활성화, mj_step 직접 구동)**: 두 가장
   미세한 dt(0.000125s, 0.0000625s) 사이 torso/swing 각도 궤적의 최대 차이를
   제어주기마다 비교(사전 등록 기준: 절대 0.01rad 또는 진폭의 2% 중 큰 쪽).
   **4개 조건 모두 사실상 완벽히 수렴한다**(최대 차이 0~0.0069rad, 기준 대비
   훨씬 작음). 즉 구동/적분 쪽은 dt에 거의 무감하다.
2. **접촉-전용(동일 충돌 직전 상태에서 재생)**: `arm_swing_with_torso_hold`
   조건의 BASE_DT(0.00025s) 실행에서 제어주기마다 (시각, qpos, qvel) 스냅샷을
   남기고, `first_contact_time_s` 직전 마지막 스냅샷을 체크포인트로 삼아, 그
   상태를 세 dt 각각에 그대로 주입한 뒤(공 포함 전체 qpos/qvel 복사, env의
   내부 phase/contact 북키핑은 재설정 불필요 — 체크포인트 자체가 접촉 이전
   상태라 fresh reset()의 값과 이미 같다) 같은 행동열을 재생했다. **4개 조건
   중 3개가 전체 실행(A2)과 똑같은 패턴으로 발산한다**: `torso_swing_with_arm_hold`만
   수렴, 나머지는 접촉만 다시 재생해도 dt에 따라 유효/무효·점수가 바뀐다.

| 조건 | 구동-전용 수렴 | 접촉-전용(동일 사전상태) 수렴 |
| --- | --- | --- |
| `arm_swing_with_torso_hold` | ✅ | ❌ |
| `torso_swing_with_arm_hold` | ✅ | ✅ |
| `simultaneous_swing_and_torso` | ✅ | ❌ |
| `staggered_swing_and_torso` | ✅ | ❌ |

**결론**: 두 표가 일치한다 — 구동/적분은 모든 조건에서 dt에 무감하고, 접촉
계산만 dt에 민감하다. A2가 관찰한 발산은 전부 접촉(충돌) 계산에서 나온다.
이는 더 이상 "추정"이 아니라 구동을 완전히 배제하고 확인한 결과다.

## A7. 관절한계 활성 시점·기여도, 구속 종류/적분오차 분리

`scripts/kc01a_constraint_decomposition.py`, 결과
`docs/records/evidence/KC-01a-constraint-decomposition.json`. `efc_type`별로
`qfrc_constraint`를 분해해(`LIMIT_JOINT` 행만 골라 `efc_J.T @ efc_force`를
다시 계산) "관절한계 반력"과 "접촉 반력"을 구분했다(무공 실행에서 접촉 반력이
정확히 0이 되는 것으로 분해 자체를 검증).

**관절한계 활성 시점(실제 타구 실행, production dt)**:

| 조건 | 최초 활성 시각 | 제동 latch로부터 | 접촉으로부터 | latch 이후 W_한계 | latch 이후 W_액추에이터 |
| --- | --- | --- | --- | --- | --- |
| `arm_swing_with_torso_hold` | 비활성 | — | — | 0 | 0 |
| `torso_swing_with_arm_hold` | 0.4485s | +0.0285s(제동 후) | -0.0058s(접촉 전) | -9.497J | -7.071J |
| `simultaneous_swing_and_torso` | 비활성 | — | — | 0 | -8.882J |
| `staggered_swing_and_torso` | 0.5015s | +0.0365s(제동 후) | +0.0428s(접촉 후) | -25.00J | -6.952J |

`torso_swing_with_arm_hold`는 제동 시작 직후(0.5.도달 전)부터 타구 시점까지
이미 관절한계가 걸려 있고, 제동 구간의 에너지 흡수 중 **관절한계 반력이
액추에이터 자체 제동보다 더 크다**(-9.50J vs -7.07J) — §A3의 "gear=30 대비
관성 과다" 추측과 방향이 일치한다(액추에이터 자체 제동력이 관절한계 없이는
부족했다는 정량적 근거). `staggered_swing_and_torso`는 접촉 이후 follow-through
구간에서야 관절한계가 걸린다 — 타구 자체보다는 사후 감속에 관여한다.

**구속 종류 vs 적분오차(3번째 dt 추가)**: 무공 에너지 잔차를 세 번째(가장
미세한) dt까지 확장하고 수렴 차수를 추정했다(`log2(잔차(dt)/잔차(dt/2))`,
1에 가까우면 semi-implicit Euler의 평범한 절단오차와 일치).

| 조건 | 잔차(3개 dt) | 수렴 차수 추정 | 해석 |
| --- | --- | --- | --- |
| `arm_swing_with_torso_hold` | -0.222→-0.111→-0.056J | ~1.00, 1.00 | 절단오차 |
| `torso_swing_with_arm_hold` | -1.162→-0.706→-0.279J | 0.72, 1.34 | 절단오차(수렴) |
| `simultaneous_swing_and_torso` | -0.291→-0.145→-0.073J | 1.00, 1.00 | 절단오차(A4의 "원인 미상" 정정) |
| `staggered_swing_and_torso` | -0.064→-0.229→-0.114J | **-1.84, 1.00** | **비단조 — 절단오차만으로 설명 안 됨** |

3개 조건은 order≈1로 깔끔히 수렴해 평범한 수치 적분오차로 설명된다.
`staggered_swing_and_torso`만 첫 구간이 음의 차수(잔차가 dt를 줄였는데 오히려
커짐)로, A2·A6에서 이미 드러난 이 조건의 비단조/판정-뒤집힘 발산과 같은
계열의 이상 징후다 — 여전히 미해결이며 숨기지 않는다.

## A8. 회전 방향 계약과 동방향(same-direction) 조건 (사용자 후속 지시)

전체 규칙·근거는 `docs/design/KC-01a-DIRECTION-CONTRACT.md`. 요약:

- **발견**: `simultaneous_swing_and_torso`/`staggered_swing_and_torso`의 torso
  목표각(-0.4)은 swing(+방향)과 **반대 부호**다. `torso_yaw`와 `bat_hinge`가
  같은 world Z축의 연속 회전이라 배트 월드 각속도 = torso_vel + swing_vel이고,
  반대 부호는 상쇄한다 — 실제 운동사슬(가산)이 아니라 우연히 그렇게 찾아진
  값이었다(`scripts/kc01a_calibrate.py`의 `shared` 탐색이 torso 음수만 훑었기
  때문). 이 조건들은 **진단용 기록으로 그대로 보존**했다(수치·컨트롤러 불변).
- **새 조건**: `scripts/kc01a_same_direction_search.py`가 torso 양수만
  탐색해(제한 제거) 찾은 `torso_target=0.3, swing_target=-1.710,
  tilt_target=0.0`, 트리거 `torso_ct=0.122s`(swing보다 10ms 먼저),
  `swing_ct=0.112s`. 그립 도달성(`FrontLegGripOverlay`) 전 구간 만족
  (오차 0). 접촉점 속도의 월드 x성분(투수 방향) 기여 분해(`mujoco.mj_jac`):
  torso +0.572m/s(43%), swing +0.768m/s(57%), tilt ≈0 — **두 축이 같은
  부호로 가산**한다(옛 조건의 상쇄와 대조).
- **dt 수렴**: `scripts/kc01a_same_direction_dt_convergence.py`가 A2와
  **동일한 사전 등록 기준**(REPLAY+INDEPENDENT, 세 dt)으로 확인 — **통과**
  (production dt 점수 1.091m → 1.104m → 1.110m, 단조·작은 변화, 유효 여부
  불변). 기존 4개 조건 중 실제 타구가 나면서 동시에 수렴한 조건은 이번이
  처음이다.
- **아직 결론 내리지 않는 것**: 점수(1.09m)는 이전(철회된) `staggered`의
  3.64m보다 낮다 — 이것만으로 "동방향이 더 낫다/못하다"를 말하지 않는다.
  정착(A3)·에너지(A4)·타이밍 성공구간(A5)을 이 새 조건에 아직 적용하지
  않았다(§다음 단계). "역방향 상쇄가 dt 민감도를 키운다"는 가설도 이
  하나의 수렴 사례만으로 확정하지 않는다 — §A6과 같은 방식(구동-전용/
  접촉-전용 분리)으로 이 조건도 재확인하는 것이 다음 단계다.
- **영상·그래프**: `runs/kc01a-same-direction-video/`(gitignored)에 위쪽
  고정 카메라 영상(옛 조건과 새 조건 각각) 및 `angular_velocity_comparison.png`
  (torso/swing/world_bat 각도·각속도 비교)를 생성했다 — 원자료는
  `docs/records/evidence/KC-01a-timelines/{staggered,same_direction_staggered}.json`.

## A9. `same_direction_staggered` 수용 검증 (설정 고정, gear·재료·보상 불변)

`scripts/kc01a_same_direction_acceptance.py`, 결과 `docs/records/evidence/
KC-01a-same-direction-acceptance.json`. torso_target=0.3/swing_target=-1.710/
torso_ct=0.122/swing_ct=0.112(§A8)를 그대로 고정하고 A3/A4/A5와 같은
방법론을 적용했다.

**정착**: swing은 latch 후 0.373s에 정착(기준 통과). **torso는 1.5초를
관찰해도 "0.5초 이내 진입 후 연속 0.2초 유지" 기준을 만족하지 못한다**
(최종 `|qvel|`=0.0014rad/s로 사실상 정지 직전까지 가지만, 그 전에 여러 차례
다시 임계값을 넘나든다 — 완전히 못 멈추는 `torso_swing_with_arm_hold`와는
다르지만, 깨끗이 한 번에 정착하지도 않는다). **이것만으로 이 조건을
시각 실험의 물리 기준선으로 채택할 수 없다**(§A9 결론, §다음 단계).

**타이밍 성공구간**: ±20ms(1ms 간격, 41점) 스윕 — **10/41(24%) 유효**. 이전에
수렴 확인한 `torso_swing_with_arm_hold`가 0/41였던 것과 달리 이 조건은 실제
성공 구간을 가진다.

**접촉 침투/힘/충격량 (geom 쌍 식별, dt별 비교 — 수치수렴과 물리적 적절성
분리)**: 접촉은 항상 `ball_geom`↔`bat_geom`. 최대 침투 −0.0510~−0.0516m
(dt 3개 사이 편차 1% 이내 — **수치적으로는 잘 수렴**), 최대 법선력
1668~1678N, 충격량 5.33~5.43N·s, 접촉 지속 8.5~8.75ms — 모두 dt에 대해
안정적이다. **물리적 적절성은 별개 문제로 남는다**: 이 침투 깊이(공 반경
0.0366m + 배트 반경 0.025m = 0.0616m 대비 −0.05m, 즉 유효 반경합의 84%에
달하는 겹침)는 KC-01a/B1이 원래부터 갖고 있던 특성이다 — 기존 4개 조건도
동일 코스에서 −0.036~−0.058m를 보인다(`docs/records/evidence/
KC-01a-dt-convergence.json`). `envs/assets/baseball_park_kc01a.xml`의
`ball_geom` 주석이 이미 명시하듯, 이 접촉 재료는 "퇴화하지 않는 충돌
응답을 얻도록만 튜닝했고, 실제 반발계수로 검증된 적은 없다." 즉
`same_direction_staggered`의 −0.0515m은 **새로 나빠진 것이 아니라 기존에
검증되지 않은 채로 남아 있던 것과 같은 수준**이다 — 수치 수렴과 물리적
타당성 미검증이라는 두 사실을 섞지 않는다.

**에너지(RK4로 정정, rect vs trapezoidal quadrature 비교)**: `envs/assets/
baseball_park_kc01a.xml`은 `integrator="RK4"`다(`mujoco.mjtIntegrator.
mjINT_RK4`로 직접 확인) — **A4/A7이 "semi-implicit Euler 절단오차"라고 쓴
것은 틀렸다. 정정한다.** RK4는 매끄러운(구속력 제외) 동역학을 4차 정확도로
적분하는 방법이며, `scripts/kc01a_noball_dt_isolation.py`가 이미 보였듯
상태(qpos/qvel) 궤적 자체는 세 dt에서 사실상 동일하다(이 실행에서
Δ(KE+PE)는 dt 3개 사이 소수점 8자리까지 일치: −0.095392045891{23,35,36}).
**잔차의 dt-의존성은 전부 이 분석 스크립트들 "자신의" work 적분
(quadrature) 오차에서 나온다** — 매 substep마다 `qfrc*qvel*dt`를 더하는
것은 상태 적분기의 차수와 무관하게 그 자체로 별도의 이산화이며(오른쪽
리만합), 상태(state) 적분 오차와 일의 수치 적분 오차는 서로 다른 것이다.
사각형(rect)과 사다리꼴(trapezoidal) 두 적분법을 같은 실행에서 나란히
계산했다: production dt에서 rect −0.0945J vs trap −0.0956J, 가장 미세한
dt에서 −0.0236J vs −0.0239J — **거의 같고, 수렴 차수도 둘 다 ≈1.0으로
동일하다.** 이는 "더 정교한 구적법을 쓰면 차수가 올라갈 것"이라는 애초
가설을 **기각한다** — torso/swing 각속도 자체가 반작용 결합으로 매우 빠르게
진동하기 때문에(§A10), 지금 시험한 dt 범위(0.00025~0.0000625s)에서는 아직
사다리꼴의 통상적 2차 이점이 나타날 만큼 그 진동을 잘게 쪼개지 못했을
가능성이 높다 — 이 설명은 아직 가설이며, 더 미세한 dt로 확인해야 한다.
**production dt에서 잔차 비율은 32%로 작지 않다**(-0.0945/0.2948) — dt를
줄이면 대략 절반씩 줄어 가장 미세한 dt에서 10.5%까지 내려가지만, 실제
채점에 쓰는 production dt 기준으로는 무시할 수 없는 크기임을 그대로
보고한다.

**공동회전(co-rotation) 구간과 관절한계 정지 여부**: 두 축이 모두
움직이는(|qvel|>0.05) 78개 제어주기 중 45개(58%)에서 같은 부호(공동회전)다
— 나머지는 반작용 결합으로 부호가 갈린다(§A10). torso 최대 각도
0.219rad로 자체 관절한계(±0.6rad)에 도달하지 않는다 — 정착 실패는 관절
한계 정지가 원인이 아니다(§A7의 `torso_swing_with_arm_hold`/`staggered`와
다른 양상).

**A9 결론**: dt 수렴·그립·타이밍 성공구간은 통과했지만 torso 정착 미충족과
production dt 32% 에너지 잔차 때문에, 이 설정 그대로는 시각 입력 실험의
물리 기준선으로 **아직 채택하지 않는다**(§A9 최종 판정은 §A12에서 A11의
새 후보와 함께 내린다).

## A10. 몸통 선행 메커니즘 검증 — 명령 시점 vs 실제 운동

`scripts/kc01a_torso_lead_analysis.py`, 결과 `docs/records/evidence/
KC-01a-torso-lead-analysis.json`, 타임라인 `docs/records/evidence/
KC-01a-torso-lead-timeline.json`. 사용자가 영상에서 본 "배트가 먼저
움직이고 몸통이 따라간다"는 인상을 데이터로 확인했다.

`same_direction_staggered`(torso_ct=0.122, swing_ct=0.112, **명령상 10ms
선행**)에서:

| 지표 | 값 |
| --- | --- |
| torso 명령 트리거(`_torso_triggered`) 시각 | 0.345s |
| swing 명령 트리거(`_swing_triggered`) 시각 | 0.355s (명령 선행 10ms, 설계대로) |
| torso 실제 운동 개시(|qvel|>0.05rad/s) 시각 | 0.345s |
| swing 실제 운동 개시(|qvel|>0.05rad/s) 시각 | **0.345s — torso와 동일 제어주기** |
| swing 개시 순간 torso 각도/각속도 | −1.9e-5rad / 0.0008rad/s (사실상 0) |

**즉 명령은 10ms 먼저 나가지만, 실제 각속도 임계값 교차는 동시다** — torso가
가속을 시작해도 그 각속도가 눈에 띄게 쌓이기 전에(불과 0.0008rad/s) 이미
swing 쪽 각속도도 임계값을 넘는다. 원인은 `bat_hinge`가 `torso_yaw`의
자손이라는 사슬 구조: torso가 갑자기 가속하면 그 관성 반작용이 배트(swing)
자유도에 **즉시** 유도 각속도를 만든다(swing 액추에이터가 아직 켜지지
않았는데도 swing_ctrl은 P-hold 대역 안에서 작게 움직이는데 swing_vel은
±0.1~0.2rad/s까지 흔들린다 — 실측, `KC-01a-torso-lead-timeline.json`).
**이 반작용은 실제 물리이지 버그가 아니다.** 그 결과 raw qvel 임계값으로
"몸통이 먼저 움직였다"를 판정하는 것 자체가 이 반작용에 오염돼 신뢰할 수
없다는 것이 이번 검증의 핵심 결론이다 — **§A11이 이 문제를 우회하는
방법(제어 트리거/`_Axis.state` 기반 정의)을 쓴다.**

**가속 구간 전체에서의 접촉점 속도 기여**(접촉 순간 한 시점이 아니라 전체
가속/제동 구간 77개 제어주기): torso 기여 비율의 최소 0.4%, 최대 79.1%,
평균 22.4% — §A8에서 보고한 "접촉 순간 43%"는 이 조건에서 우연히 torso
기여가 큰 순간을 짚은 것이며, 전체 구간 평균은 그보다 훨씬 낮다(반작용에
의한 진동 때문에 순간값이 크게 요동친다).

**유지축 대비 능동 구동축의 일**: `arm_swing_with_torso_hold`(torso를
0으로 유지)에서 torso 액추에이터의 순일은 −1.22J(peak power 46.3W)로,
"유지"도 0이 아니다(§A1에서 이미 지적). 능동으로 흔드는
`same_direction_staggered`의 torso가 이보다 유의미하게 더 많은 일을 하는지
정밀 비교하려면 축별 일 분해가 더 필요하다 — 이번엔 전체(3축 합) 수치만
확인했고 축별 정밀 비교는 하지 않았다(§다음 단계).

**중요한 해석 제한(사용자 지시대로 명시)**: 위 접촉점 속도 기여 분해는
`v_point = Σ jacp[:,i]*qvel[i]`라는 **순간 속도**의 선형 분해다. 이것은
"각 축의 각속도가 그 순간 접촉점 속도에 얼마나 기여하는가"를 보여줄 뿐,
**에너지나 운동량이 한 축에서 다른 축으로 전달됐다는 증거가 아니다** — 그런
흐름 분석은 이번에 수행하지 않았고, 위 비율을 그런 의미로 읽지 않는다.

## 정정 (A11-A14) — torso_target=0.5 후보는 무효, 참고 결과로 보존

**아래 A11-A14는 원문 그대로 보존하지만, 그 "검증 통과" 판정은 철회한다.**
사용자가 지적한 대로 이 후보(torso_target=0.5, swing_target=−1.964)는:

1. **몸통은 양(+) 방향, 팔은 음(−) 방향으로 가속하라는 명령이다**
   (torso_dir=+1, swing_dir=−1) — §A8에서 정의한 "동방향(same-direction)"
   조건이 전혀 아니다. swing의 총 명령 변위는 겨우 −0.004rad로, 사실상
   "팔이 스윙한다"고 부를 수 없는 크기다.
2. **몸통과 팔의 팔로우스루 목표가 모두 자기 관절 범위 밖이다**: 몸통
   0.5+0.15=0.65rad(범위 ±0.6), 팔 −1.964−0.4=−2.364rad(범위 ±2.0). 둘 다
   물리적으로 도달 불가능한 목표이며, A12가 "정착"이라 판정한 것은 이
   불가능한 목표를 향한 PD 제동이 아니라 몸통이 자기 관절 하드 스톱에
   눌려서 멈춘 것이었다.
3. 이 두 가지를 §A11-A12의 탐색/검증 어디에서도 사전에 확인하지 않았다 —
   "제어 수준 225ms 선행"과 "6.78m 점수"라는 결과만 보고 방향·변위·범위를
   확인하지 않은 것이 원인이다.

**정정 조치**: `controllers/baseball_kc01a.py`에 `validate_same_direction_
candidate()`를 추가해 방향 일치·최소 팔 변위·양 축 prep/target/
follow-through의 관절 범위 여유를 시뮬레이션 전에 검사하도록 했고,
`torso_lead_handoff`의 인계 조건 자체도 절대 각변위(`abs(torso_angle-prep)`)
대신 **의도한 방향으로의 부호 있는 진행량**을 쓰도록 고쳤다(반대 방향으로
움직여도 인계되던 잠재적 결함 수정, `tests/test_baseball_kc01a_controller.py`로
회귀 테스트 추가). 아래 A11-A14는 **이 결함이 발견되기 전의 기록으로
보존**하며, 그 결론("검증 통과", "협응 우위 후보")은 A15-A18로 대체한다.

## A11. Motion-triggered handoff 컨트롤러와 재탐색 (원문 보존 — 판정 철회, 위 정정 참고)

`controllers/baseball_kc01a.py`에 새 모드 `"torso_lead_handoff"`를
추가했다(기존 4개 모드의 동작은 무변경, 테스트 99개 그대로 통과). swing은
고정 시간이 아니라 **torso 자신의 각변위가 자기 목표의 `handoff_fraction`에
도달할 때** 트리거된다 — "모든 축을 처음부터 최대 입력으로" 몰지 않고
"선행 시간을 늘리면 항상 좋다"고 가정하지 않기 위해, swing은 인계 전까지
순수 P-hold만 한다.

`scripts/kc01a_torso_lead_handoff_search.py`(1차, 60개 조합: torso_target
∈{0.2,0.3,0.4}×torso_ct∈{0.15..0.36}×handoff_fraction∈{0.15..0.7}) →
유효 2/60, 둘 다 §A10과 같은 반작용 오염으로 raw-qvel "실제 선행"이
0으로 나왔다. **원인 진단 후 지표를 교체**: raw qvel 대신 컨트롤러 자신의
트리거 플래그(`_torso_triggered`/`_swing_triggered`, 즉 각 축이 실제로
"accelerate" 상태로 전환되는 시각)로 "선행"을 재정의했다 — 이것은 반작용에
오염되지 않는, 각 축의 **자기 액추에이터가 실제로 켜지는 시각**이다. 이
정의로 재확인한 결과 §A11의 유효 조합들은 실제로 **205ms의 진짜 제어
수준 선행**을 갖고 있었다(torso_target=0.4/torso_ct=0.25/
handoff_fraction=0.5: torso 트리거 0.210s, swing 트리거 0.415s).

확장 탐색(torso_target∈{0.3..0.5}×torso_ct(7개)×handoff_fraction∈{0.3..0.6},
140개 조합) → **유효 10/140**, 그중 최고 성적:
**torso_target=0.5, swing_target=−1.964, torso_ct=0.33,
handoff_fraction=0.5 → production dt 점수 6.78m, 제어 수준 선행 225ms.**
이 값이 §A12에서 전체 검증을 통과한 새 후보다.

## A12. 새 후보(`torso_lead_handoff`, torso_target=0.5) 전체 검증 (원문 보존 — 판정 철회)

`scripts/kc01a_torso_lead_handoff_validation.py`, 결과 `docs/records/
evidence/KC-01a-torso-lead-handoff-validation.json`. §A9와 동일한 항목을
전부 다시 통과해야 한다는 사용자 지시에 따라 재확인했다:

| 검증 | 결과 |
| --- | --- |
| dt 수렴(A2 방법론, REPLAY+INDEPENDENT) | **통과** — 6.778→6.749→6.723m, 단조·작은 변화, 유효 여부 불변 |
| 접촉 침투(geom쌍) | `ball_geom`↔`bat_geom`, −0.0494~−0.0500m(dt 안정, 기존 범위와 같은 수준) |
| 최대 법선력/충격량 | 1997~2022N / 5.98~6.13N·s (dt 안정) |
| 정착 — torso | latch 후 0.34s에 정착(**통과**, §A9와 달리 정착함) |
| 정착 — swing | latch 후 0.095s에 정착(통과) |
| 그립 도달성 | 오차 0(항상 도달, **통과**) |
| 에너지 잔차(무공, 관절한계 포함) | production dt 잔차 −3.5%, 가장 미세한 dt −0.2% — §A9(32%)보다 훨씬 작다 |
| 공동회전 구간 | 47/122(38.5%) 제어주기에서 공동회전 |
| torso 관절한계 도달 여부 | **도달한다**(최대각 0.603rad, 범위 ±0.6rad — follow-through 목표(0.5+0.15=0.65)가 애초에 한계 밖이라 실제로는 한계에 눌려 멈춘다. torso 정착이 "성공"으로 판정된 것은 브레이크 제어가 아니라 **물리적 하드 스톱** 덕분일 가능성이 높다 — `torso_swing_with_arm_hold`/`staggered_swing_and_torso`와 같은 계열의 메커니즘) |

**A12 판정**: dt 수렴·정착(양 축)·그립·접촉 침투(기존 범위 내)·에너지
정합성 모두 이 조건에서 §A9보다 낫다. **다만 torso가 관절한계에 눌려서
멈춘다는 점은 새로운 우려사항이다** — "정착"이 능동 제어의 결과가 아니라
하드 스톱에 기댄 것이라면, 향후 관절한계나 gear를 바꾸는 순간 이 결과가
깨질 수 있다(§최소 수정안 제안).

## A13. 시각 기준선 판정 (A9-A12 종합, 사용자 요청) (원문 보존 — 판정 철회, §A18 참고)

**`same_direction_staggered`(§A8-A9, 10ms 명령 선행)는 시각 입력 실험의
물리 기준선으로 채택하지 않는다** — torso 정착 미충족, production dt
에너지 잔차 32%.

**`torso_lead_handoff`(torso_target=0.5, §A11-A12, 225ms 제어 선행)는
dt/정착/그립/침투/에너지 5개 항목을 모두 통과해 기준선 후보로 더 낫다.**
그러나 다음 이유로 **아직 "확정 채택"은 보류한다**:
1. torso 정착이 관절한계 하드 스톱에 의존한다(위 표) — 능동 제어로 정착하는
   것이 아니므로, 시각 정책이 이 조건 위에서 학습될 경우 하드 스톱이라는
   비-일반적 동역학에 암묵적으로 의존하게 될 위험이 있다.
2. §A9의 침투 깊이 논의(기존 모델과 같은 수준이지만 실제 반발계수로 검증된
   적 없음)가 이 후보에도 그대로 적용된다.
3. 공통 에너지 예산 비교, 구동-전용/접촉-전용 분리(§A6과 같은 방식)를 이
   후보에 아직 적용하지 않았다.
4. production dt 점수(6.78m)가 이전 모든 KC-01a 결과보다 높다는 사실 자체를
   "협응이 더 낫다"는 근거로 쓰지 않는다 — `staggered`의 3.64m이 정밀 dt에서
   무효로 뒤집힌 선례(§A2)가 바로 이런 종류의 성급한 결론을 경계하라는
   증거다.

**최소 수정안**: (1)~(3)을 마저 확인하는 것이 다음 단계이며, 이번 범위에서는
gear/관절한계/재료를 바꾸지 않는다는 지시를 그대로 지켰다 — torso가
관절한계에 기대는 문제의 "최소 수정"이 gear 재조정일 가능성이 높지만, 그
자체가 새 실험이므로 사용자 승인 후 진행한다.

## A14. 몸통 선행 + 유효 타격의 기구학적 제약 (요약) (원문 보존 — §A18에서 재평가)

사용자의 마지막 질문 — "몸통 선행과 유효 타격을 함께 만족하지 못하면
기구 배치·가동범위·제어의 어떤 제약 때문인지 보고하라" — 에 대한 답: **이번
탐색 범위에서는 함께 만족하는 후보를 찾았다(§A11-A12).** 다만 그 경로에서
드러난 제약들:

- torso의 최대 각가속도(11.41rad/s²)가 swing의 것(134.4rad/s²)보다 약
  12배 작다 — 아주 작은(10ms) 명령 선행은 실제 운동에서 무의미해진다
  (§A10). 의미 있는 선행을 얻으려면 handoff처럼 "torso가 실제로 상당량
  움직일 때까지 기다리는" 방식이 필요했다 — 단순 시간차로는 이 관성비를
  극복하지 못한다.
- `bat_hinge`가 `torso_yaw`의 자손이라는 기구학적 배치 때문에, torso의
  가속은 swing 자유도에 즉시 반작용 각속도를 유도한다(§A10) — 두 축의
  운동을 시각적으로/qvel 기준으로 완전히 분리해서 보여주는 것은 이
  기구학적 사슬 위에서는 애초에 불가능하다(반작용 자체가 실제 물리이므로
  "안 보이게" 만들 수 없다 — 없애려면 사슬 구조 자체를 바꿔야 한다).
- torso 목표각을 크게(0.5rad) 키우자 자체 관절한계(±0.6rad)에 근접/도달하는
  방식으로 "정착"이 이뤄졌다(§A12) — 가동범위 한계가 이 조건의 안정성에
  실제로 관여하고 있다는 뜻이며, 향후 gear/관절범위를 조정하면 이 특정
  결과가 재현되지 않을 수 있다.

## A15. 유효성 검사 자체를 수정 (사용자 지시, 이번 갱신)

`controllers/baseball_kc01a.py`에 `validate_same_direction_candidate()`를
추가했다 — 어떤 (torso_target, swing_target) 조합이든 **시뮬레이션 전에**
세 가지를 검사한다:

1. **가속 방향 일치**: torso_dir과 swing_dir이 같은 부호인가(다르면
   "동방향 운동사슬"이 아니다 — A11/A12 후보가 정확히 이 검사에 걸린다).
2. **최소 팔 스윙 변위**: `|swing_target - prep_swing|`이 최소 기준
   (0.3rad, 사전 등록)을 넘는가 — 기하 탐색이 "torso 혼자 거의 다 도달해
   swing은 거의 안 움직여도 됨"으로 퇴화하는 것을 막는다.
3. **관절 범위 여유**: 양 축의 prep/target/follow-through(=target+offset×dir,
   컨트롤러가 실제로 쓰는 것과 같은 식) 각도가 모두 자기 관절 범위
   안쪽에 여유(0.02rad, 사전 등록)를 두고 있는가.

세 검사 모두 독립적으로 보고한다(첫 실패에서 멈추지 않음). A11/A12 후보에
적용하면 세 가지 모두 실패로 나온다(방향 불일치, swing 변위
−0.004rad<0.3rad, 양 축 follow-through 범위 밖) — `tests/
test_baseball_kc01a_controller.py`의 회귀 테스트로 고정했다.

**인계 조건 자체의 결함도 수정**: `torso_lead_handoff`의 swing 트리거가
`abs(torso_angle - prep_torso) >= handoff_target_disp`(절대값)를 쓰고
있었다 — 이러면 torso가 **반대 방향**으로 그만큼 움직여도 인계가 발생할 수
있다(사용자 지적). **의도한 방향으로의 부호 있는 진행량**
`(torso_angle - prep_torso) * torso_dir >= handoff_target_disp`으로
고쳤다. `tests/test_baseball_kc01a_controller.py::TestHandoffUsesSignedProgress`가
이 수정이 실제로 필요했음을 보인다 — 수정 전 코드로는 통과하지 못했을
합성 시나리오(torso가 반대 방향으로 임계값만큼 움직이는 경우)로 확인했다.
기존 4개 모드(`arm_only`/`torso_only`/`simultaneous`/`staggered`)의 동작은
이 변경으로 전혀 바뀌지 않는다(`TestExistingModesUnaffected`, 그리고 기존
99개 테스트가 여전히 그대로 통과) — **다만 "기존 99개가 통과한다"는 사실
자체를 새 모드/새 함수의 검증으로 쓰지 않는다**: 새로 추가한 10개 테스트
(`tests/test_baseball_kc01a_controller.py`)가 새 동작을 검증하는 것이고,
기존 99개는 그 동작을 건드리지 않았다는 것만 보인다.

## A16. 재탐색 v2 — 사전 필터를 통과한 후보만 검색

`scripts/kc01a_torso_lead_handoff_search_v2.py`, 결과 `docs/records/
evidence/KC-01a-torso-lead-handoff-search-v2.json`. 기하 탐색 자체도
수정했다: swing_target을 "최근접점"이 아니라 **방향·최소 변위 제약이 걸린
범위**(`swing ∈ [prep_swing + 0.3, 2.0]`) 안에서만 찾는다 — 옛 탐색처럼
torso_target이 커질수록 swing이 필요 없어지다 못해 역방향으로 넘어가는
경로를 원천 차단한다.

torso_target ∈ {0.1,...,0.4}(0.05 간격) 중 **기하학적으로 도달 가능하고
사전 필터를 통과하는 것은 0.1~0.3의 5개뿐**이다(0.35 이상은 이 제약 안에서
공에 도달할 수조차 없다 — 최근접 거리가 접촉 임계값을 넘는다). 이 5개에
대해 torso_ct×handoff_fraction 그리드(처음 20개 조합)를 돌리자 **유효
1/100** — 옛 탐색(제약 없음)의 "60개 중 2개, 140개 중 10개"보다 유효 비율이
훨씬 낮다. 이것이 바로 "동방향 제약을 지키면 도달 가능한 진짜 유효 조합이
드물어진다"는, 이번 탐색이 드러낸 사실이다. 그 하나(torso=0.3)도 팔 축이
능동 제동으로 정착하지 못했다.

그리드를 세분화(torso_ct 14개×handoff_fraction 9개, 5개 torso_target =
630개)하자 **유효 5개**를 찾았다. 이 중 두 축 모두 **능동 제동으로
정착**(자기 관절한계로부터 0.02rad 이상 떨어진 채로 마지막 0.3초 동안
유지 — 하드 스톱에 눌린 것이 아님)하는 최고 성적 후보:

**torso_target=0.25, swing_target=−1.644(변위 +0.316rad, torso와 같은
+ 방향), torso_ct=0.16, handoff_fraction=0.1.**

## A17. 새 후보(torso_target=0.25) 전체 재검증 — dt 수렴 실패

`scripts/kc01a_torso_lead_handoff_validation_v2.py`, 결과 `docs/records/
evidence/KC-01a-torso-lead-handoff-validation-v2.json`.

| 검증 | 결과 |
| --- | --- |
| 사전 필터(`validate_same_direction_candidate`) | **통과**(방향 일치, 변위 0.316rad>0.3, 양 축 follow-through 범위 내) |
| dt 수렴(A2 방법론) | **실패** — production dt 3.327m → 3.720m → 3.812m, **단조 증가하며 수렴하지 않는다** |
| 접촉 침투(geom쌍) | `ball_geom`↔`bat_geom`, −0.0552~−0.0568m — **"통과"로 표시하지 않는다.** dt에는 안정적이지만(1% 이내), §A9와 같은 이유로 물리적 타당성은 여전히 미해결이다 |
| 최대 법선력/충격량 | 1796~1857N / 5.82~6.07N·s |
| 정착 — torso | latch 후 0.475s에 정착, 자기 한계로부터 0.197rad 여유(능동 제동, 하드 스톱 아님) |
| 정착 — swing | latch 후 0.290s에 정착. 최대 각도가 자기 한계(−2.0)에서 0.035rad — **주의: 이 값은 하드 스톱 근접이 아니라 swing 자체가 prep(−1.96)에서 시작해 한계에서 멀어지는 방향(−1.644)으로만 움직이기 때문에 나오는 값**(전 KC-01a 조건이 공유하는 prep_swing 위치의 특성이지, 이 후보의 새로운 결함이 아니다) |
| 그립 도달성 | 오차 0(항상 도달) |
| 제어 수준 선행 | 75ms(torso 트리거 0.305s, swing 트리거 0.380s) |
| 인계 순간 몸통 각변위/각속도 | 0.032rad / 0.738rad/s |
| 인계 순간 팔의 몸통 기준 각도/각속도 | −1.9568rad(prep 대비 Δ0.003rad, 거의 안 움직임) / 0.643rad/s(반작용 포함 — 아래 참고) |
| 지속 변위 기준 "본격 스윙" 개시 | torso 0.360s, swing 0.380s(=인계 순간과 거의 동시 — 0.02s 창·0.03rad 이상 부호 있는 진행이 유지되는 첫 시점) |

**dt 수렴 실패는 이번 검증에서 가장 중요한 결과다.** 방향·변위·관절범위
사전 필터를 통과하고 두 축 모두 능동 제동으로 정착하는 후보를 찾았지만,
그 후보는 §A2와 같은 사전 등록 기준으로 timestep 수렴을 통과하지 못한다
— 유효성 검사를 고쳤다고 해서 dt 수렴까지 저절로 따라오지 않는다는 것을
보여준다. **이 후보도 "검증된 후보"가 아니라 "유효성 검사는 통과했지만
dt 미수렴인 후보"로 보고한다.**

**접촉 침투는 여전히 미해결이다.** §A9와 마찬가지로 −0.055~−0.057m는
dt에 대해 안정적이지만(수치 수렴), 실제 반발계수로 검증된 적 없는 기존
KC-01a/B1 접촉 모델의 특성을 그대로 물려받은 것이며, 이번 후보가 "정상
접촉 검증을 통과했다"는 뜻이 아니다.

## A18. 갱신된 최종 판정

- `same_direction_staggered`(§A9): 시각 기준선 채택 안 함(torso 정착 실패,
  32% 에너지 잔차).
- `torso_lead_handoff`, torso_target=0.5(§A11-A14): **무효** — 방향
  불일치, 팔 변위 사실상 0, 양 축 follow-through 범위 밖. 참고 기록으로만
  보존.
- `torso_lead_handoff`, torso_target=0.25(§A16-A17): 유효성 검사(방향·
  변위·범위·능동 제동 정착·그립)는 통과하지만 **dt 수렴에 실패**하고
  접촉 침투는 미해결이다 — 시각 기준선으로도, "협응 우위" 근거로도 아직
  쓸 수 없다.
- **현재 KC-01a에는 "방향·변위·범위가 올바르고, 능동 제동으로 정착하고,
  동시에 dt 수렴까지 통과하는" 몸통 선행 후보가 없다.** 이것이 이번
  갱신의 정직한 결론이다 — 추가 탐색(더 넓은 grid, 다른 torso_target
  구간)과 gear 재보정은 사용자가 다음에 명시적으로 지정한 뒤 진행한다.

## 산출물

- 4조건×dt 표, 최초 발산 원인: 본 문서 §A2, 원자료
  `docs/records/evidence/KC-01a-dt-convergence.json`
- 축별 정착표: §A3, `docs/records/evidence/KC-01a-settle-diagnostics.json`
- 에너지 잔차: §A4, `docs/records/evidence/KC-01a-energy-validation.json`
- 타이밍 구간: §A5, `docs/records/evidence/KC-01a-timing-window.json`
- 발산 원인 분리(구동/접촉): §A6, `docs/records/evidence/
  KC-01a-{noball,contact-only}-dt-isolation.json`
- 관절한계 타이밍·구속종류/적분오차: §A7, `docs/records/evidence/
  KC-01a-constraint-decomposition.json`
- 방향 계약·동방향 조건: §A8, `docs/design/KC-01a-DIRECTION-CONTRACT.md`,
  `docs/records/evidence/KC-01a-same-direction-{search,dt-convergence}.json`,
  `runs/kc01a-same-direction-video/`(gitignored, 영상·그래프)
- `same_direction_staggered` 수용 검증(정착/에너지/타이밍/침투/RK4 정정):
  §A9, `docs/records/evidence/KC-01a-same-direction-acceptance.json`
- 몸통 선행 메커니즘(명령 vs 실제, 반작용 결합): §A10, `docs/records/
  evidence/KC-01a-torso-lead-{analysis}.json`, `docs/records/evidence/
  KC-01a-torso-lead-timeline.json`
- Motion-triggered handoff 모드와 탐색(**무효 후보, 참고용**): §A11,
  `controllers/baseball_kc01a.py`(`torso_lead_handoff` 모드),
  `docs/records/evidence/KC-01a-torso-lead-handoff-search.json`
- 새 후보 전체 검증(**무효 후보, 참고용**): §A12, `docs/records/evidence/
  KC-01a-torso-lead-handoff-validation.json`
- 전후 영상(위쪽+측면, 실시간+8배 슬로모션 라벨)·속도/기여 그래프
  (**§A11-A12의 무효 후보 기준, 참고용**): §A10-A12,
  `runs/kc01a-torso-lead-before-after/`(gitignored)
- 유효성 검사 정정과 회귀 테스트: §A15, `controllers/baseball_kc01a.py`
  (`validate_same_direction_candidate`, 인계 조건의 부호 있는 진행량
  수정), `tests/test_baseball_kc01a_controller.py`(10개 테스트)
- 재탐색 v2(사전 필터 적용)와 새 후보 재검증(dt 미수렴 포함): §A16-A17,
  `scripts/kc01a_torso_lead_handoff_search_v2.py`,
  `scripts/kc01a_torso_lead_handoff_validation_v2.py`, `docs/records/
  evidence/KC-01a-torso-lead-handoff-{search-v2,validation-v2}.json`
- 명령 일정/설정: 각 스크립트(`scripts/kc01a_dt_convergence.py` 등)의
  `CONDITIONS` 딕셔너리가 실제 실행 설정이다(코드가 곧 기록).
- 기존 B1 회귀 87개 + KC-01a 22개 = 109개, 두 pytest 진입점 일치, 전체 lint
  클린(매 커밋 확인).

## 최소 수정안 제안 (A6-A8 근거, 아직 적용하지 않음)

재료·gear·보상을 바꾸는 대신, 근거가 가장 직접적인 순서로 제안한다:

1. **`staggered_swing_and_torso`/`simultaneous_swing_and_torso`(옛 역회전
   조건)를 더 이상의 수정 대상으로 삼지 않는다.** §A8에서 이 두 조건의
   torso 목표각이 물리적 근거 없이(탐색 범위 제한) 반대 부호로 찾아졌다는
   것과, 부호를 맞춘 `same_direction_staggered`가 곧바로(추가 solver 튜닝
   없이) dt 수렴을 통과한다는 것을 확인했다 — 상쇄에 가까운 배치 자체가
   접촉 민감도를 키웠을 가능성이 높으므로, 접촉 solver 파라미터를 건드리는
   것보다 **동방향 조건을 다음 비교의 기본 후보로 채택**하는 쪽이 더 최소
   수정에 가깝다. (가설 상태 — §A8 마지막 항목대로 아직 확정 아님.)
2. `torso_swing_with_arm_hold`의 정착·유효 타구 실패는 §A7이 정량적으로
   뒷받침한다(제동 구간에서 관절한계 반력이 액추에이터 자체 제동보다 큼) —
   gear 재보정이 실제 최소 수정안이 될 가능성이 높지만, gear를 바꾸는 것은
   새 실험이므로 사용자 승인 후 진행한다(변경 없음, 이번 범위 아님).
3. `staggered_swing_and_torso`(옛 역회전 조건)의 비단조 잔차/발산은 §A7에서
   재확인됐지만 원인이 아직 없다 — 이 조건 자체를 더 고치기보다 §A8의 동방향
   조건으로 대체하는 것이 우선이므로, 이 조건의 solver 진단은 낮은 우선순위로
   내린다.
4. ~~`torso_lead_handoff`(torso_target=0.5, §A11-A12)의 torso 정착이
   관절한계 하드 스톱에 의존한다~~ — 이 후보 자체가 무효(§정정, §A18)라
   더 이상 해당 사항 없음.
5. **(이번 갱신 추가)** `torso_lead_handoff`(torso_target=0.25, §A16-A17)는
   유효성 검사·능동 제동 정착·그립을 통과하지만 dt 수렴에 실패한다 — 최소
   수정안은 아직 없다(원인 진단이 먼저 필요, §다음 단계 1).

## 다음 단계 (이번에 하지 않음)

1. `torso_lead_handoff`(torso_target=0.25, §A16-A17)의 dt 미수렴 원인을
   §A6과 같은 방식(구동-전용/접촉-전용 분리)으로 진단한다 — 최소 수정안은
   원인을 안 뒤에 제안한다.
2. `same_direction_staggered`(§A8-A9)와 `torso_lead_handoff`(torso_target=
   0.5, §A11-A14, 무효)는 더 이상 이 계열의 기본 후보가 아니다 — 다음
   탐색은 §A16의 v2 방법론(사전 필터 통과 + 능동 제동 정착)을 기본으로
   하고, 필요하면 탐색 범위(torso_target, torso_ct, handoff_fraction 그리드
   해상도)를 넓힌다.
3. `torso_swing_with_arm_hold`의 정착 실패·유효 타구 실패에 대한 gear
   재보정은 그것 자체가 새로운 실험이므로 사용자 승인 후 진행한다.
4. 공통 에너지 예산 비교(A4 후반)는 관심 조건들이 모두 dt 수렴을 통과한
   뒤 재개한다 — 지금까지 나온 어떤 점수(6.78m 포함, 무효로 판정됨)도
   "협응이 낫다"는 근거로 쓰지 않는다(§A18).
5. VISION-01(`docs/design/VISION-01.md`) 통합 여부는 위 1-2가 마무리돼
   dt 수렴하는 유효 후보가 나온 뒤 재검토한다 — 현재는 어떤 `torso_lead_
   handoff` 후보도 시각 기준선으로 쓸 만큼 완결되지 않았다(§A18).
6. 접촉 침투(§A9, §A17 모두 −0.05m대)의 물리적 타당성은 이번에도 검증하지
   않았다 — 실제 반발계수 데이터나 별도 재료 실험 없이는 "정상"이라고
   말할 수 없는 채로 남겨둔다.

KC-01b·8코스·변화구·RL·실제 신경회로·시각 제어 구현은 이번 작업에 포함하지
않았다(사용자 지시).

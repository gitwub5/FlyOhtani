# KC-01a-validation — dt 수렴·정착·에너지·타이밍 보완 결과

2026-09-17 · 기준 문서: `docs/tasks/KC-01a-VALIDATION-AND-VISION.md` (A절),
후속 사용자 지시(발산 원인 분리 A6-A8, 방향 계약) · 후속 정정 대상:
`docs/records/KC-01a-COMPARISON.md`(원본 보존, 상단에 이 문서 링크 추가) ·
원자료: `docs/records/evidence/KC-01a-{dt-convergence, settle-diagnostics,
energy-validation, timing-window, noball-dt-isolation,
contact-only-dt-isolation, constraint-decomposition, same-direction-search,
same-direction-dt-convergence}.json` · 재현: `scripts/kc01a_dt_convergence.py`
→ `scripts/kc01a_settle_diagnostics.py` → `scripts/kc01a_energy_validation.py`
→ `scripts/kc01a_timing_window.py` → `scripts/kc01a_noball_dt_isolation.py`
→ `scripts/kc01a_contact_only_dt_isolation.py` →
`scripts/kc01a_constraint_decomposition.py` →
`scripts/kc01a_same_direction_search.py` →
`scripts/kc01a_same_direction_dt_convergence.py` · 관련: `docs/design/
KC-01a-DIRECTION-CONTRACT.md`(회전 방향 계약, 새 조건 설계 규칙)

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
- 명령 일정/설정: 각 스크립트(`scripts/kc01a_dt_convergence.py` 등)의
  `CONDITIONS` 딕셔너리가 실제 실행 설정이다(코드가 곧 기록).
- 기존 B1 회귀 87개 + KC-01a 12개 = 99개, 두 pytest 진입점 일치, 전체 lint
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

## 다음 단계 (이번에 하지 않음)

1. `same_direction_staggered`(§A8)에 A3(정착)·A4(에너지)·A5(타이밍 구간)를
   그대로 적용한다 — 지금까지는 dt 수렴만 확인했다.
2. `same_direction_staggered`에도 §A6과 같은 구동-전용/접촉-전용 분리를
   적용해 "역회전 상쇄가 dt 민감도를 키운다"는 가설을 별도로 검증한다.
3. `torso_swing_with_arm_hold`의 정착 실패·유효 타구 실패에 대한 gear
   재보정은 그것 자체가 새로운 실험이므로 사용자 승인 후 진행한다.
4. 공통 에너지 예산 비교(A4 후반)는 관심 조건들이 모두 dt 수렴을 통과한
   뒤 재개한다.
5. VISION-01(`docs/design/VISION-01.md`) 통합 여부는 이 문서의 결과(대부분
   미수렴, `same_direction_staggered`만 예외)를 근거로 **보류**한다 — 물리가
   충분히 수렴하지 않은 조건 위에 시각 정책을 올리면 어느 결과가 시각
   때문이고 어느 것이 물리 이산화 때문인지 구분할 수 없다.

KC-01b·8코스·변화구·RL·실제 신경회로·시각 제어 구현은 이번 작업에 포함하지
않았다(사용자 지시).

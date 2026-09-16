# KC-01a-validation — dt 수렴·정착·에너지·타이밍 보완 결과

2026-09-17 · 기준 문서: `docs/tasks/KC-01a-VALIDATION-AND-VISION.md` (A절) ·
후속 정정 대상: `docs/records/KC-01a-COMPARISON.md`(원본 보존, 상단에 이 문서
링크 추가) · 원자료: `docs/records/evidence/KC-01a-{dt-convergence,
settle-diagnostics,energy-validation,timing-window}.json` · 재현:
`scripts/kc01a_dt_convergence.py` → `scripts/kc01a_settle_diagnostics.py` →
`scripts/kc01a_energy_validation.py` → `scripts/kc01a_timing_window.py`

## 현재 판정 (요약)

**KC-01a의 조건 간 우위 비교는 여전히 결론 내릴 수 없다.** dt 수렴은 4개 조건 중
1개(`torso_swing_with_arm_hold`)만 통과했고, 그 1개는 물리적으로 일관되게
"유효 타구를 만들지 못한다"는 음성 결과다. 나머지 3개 조건은 수렴하지 않아 그
수치(점수·발사각·유효 여부)를 신뢰할 수 없다 — 특히 이전에 "최고 성적"이라던
`staggered_swing_and_torso`는 정밀한 dt에서 **무효로 뒤집힌다.** 정착은 관찰
시간을 늘리자 3개 조건에서 명확히 확인됐고, 에너지 잔차는 관절한계 반력을
포함하자 대부분 설명됐다. 시각 정책 통합 여부는 이 결과들을 근거로 보류한다.

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

**결론**: gear·재료·트리거를 몰래 바꾸지 않았다. 수렴 실패 원인은 접촉의
이산화 민감도(이미 알려진 B1의 ±5ms 취약성과 같은 계열의 문제로 추정)이며,
최소 수정안은 §다음 단계 참고.

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
너무 커 구동력이 부족)일 가능성이 높다.

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
원인 미상으로 정직하게 남긴다(추가 조사 필요, 이번에 억지로 줄이지 않음).
dt를 절반으로 하면 잔차도 대체로 절반 가까이 줄어(수렴 방향), `staggered`만
예외적으로 약간 커진다(-0.064→-0.229J, 절대값은 여전히 작음).

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

## 산출물

- 4조건×dt 표, 최초 발산 원인: 본 문서 §A2, 원자료
  `docs/records/evidence/KC-01a-dt-convergence.json`
- 축별 정착표: §A3, `docs/records/evidence/KC-01a-settle-diagnostics.json`
- 에너지 잔차: §A4, `docs/records/evidence/KC-01a-energy-validation.json`
- 타이밍 구간: §A5, `docs/records/evidence/KC-01a-timing-window.json`
- 명령 일정/설정: 각 스크립트(`scripts/kc01a_dt_convergence.py` 등)의
  `CONDITIONS` 딕셔너리가 실제 실행 설정이다(코드가 곧 기록).
- 기존 B1 회귀 87개 + KC-01a 12개 = 99개, 두 pytest 진입점 일치, 전체 lint
  클린(매 커밋 확인).

## 다음 단계 (이번에 하지 않음)

1. `staggered_swing_and_torso`/`simultaneous_swing_and_torso`의 dt 비수렴
   원인을 더 분해(접촉 시점 자체가 dt에 따라 이동하는지 확인 등) — 원인 확인
   후 최소 수정안(예: 접촉 solver 파라미터의 dt 의존성 점검, **재료 재보정은
   아님**)을 별도로 제시해야 한다.
2. `torso_swing_with_arm_hold`의 정착 실패·유효 타구 실패는 같은 근본 원인
   (gear=30 대비 관성 과다)으로 보이며, gear 재보정이 필요하다면 그것 자체가
   새로운 실험이므로 사용자 승인 후 진행한다.
2b. 공통 에너지 예산 비교(A4 후반)는 A2가 통과한 뒤 재개한다.
3. VISION-01(`docs/design/VISION-01.md`) 통합 여부는 이 문서의 결과(대부분
   미수렴)를 근거로 **보류**한다 — 물리가 수렴하지 않은 조건 위에 시각 정책을
   올리면 어느 결과가 시각 때문이고 어느 것이 물리 이산화 때문인지 구분할 수
   없다.

KC-01b·8코스·변화구·RL·실제 신경회로·시각 제어 구현은 이번 작업에 포함하지
않았다(사용자 지시).

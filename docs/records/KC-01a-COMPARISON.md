# KC-01a — 몸통·배트 협응 비교 결과

2026-09-17 · mid_mid만 · 기준 문서: `docs/design/KC-01a-TORSO-BAT-COORDINATION.md`
· 원자료: `docs/records/evidence/KC-01a-{comparison,noball-validation,grip-reach-check}.json`,
`docs/records/evidence/KC-01a-timelines/*.json` · 재현: `scripts/kc01a_calibrate.py` →
`scripts/kc01a_noball_validation.py` → `scripts/kc01a_compare_conditions.py` →
`scripts/kc01a_plot_timelines.py`/`kc01a_structure_diagram.py` →
`demos/record_kc01a_comparison.py`

## 요약

같은 하드웨어(같은 gear·range, torso gear=30/swing gear=30/tilt gear=6)에서 어느
축을 언제 구동하는지만 바꿔 4개 조건을 비교했다. **협응 시점이 실제로 결과를
바꾼다** — `staggered`(몸통이 팔보다 0.12s 먼저 트리거)가 같은 목표 각도를 쓰는
`simultaneous`(동시 트리거)보다 비거리 점수 5.4배(3.64m vs 0.67m), 접촉점 속도도
더 높았다(8.30 vs 7.80 m/s). 그러나 **몸통 단독(`torso_only`)은 최선의 타이밍에서도
유효 타구를 만들지 못했다** — 몸통 추가가 항상 이득이라고 가정하지 않는다.
모든 조건은 기존 B1과 동일하게 ±5ms 트리거 오차에서 유효 판정이 뒤집혔고,
`staggered`의 결과는 물리 timestep을 절반으로 줄이면 무효로 바뀌었다(수렴 실패) —
비거리가 가장 컸던 조건이 가장 덜 강건하다는 것도 그대로 보고한다.

## 1. 조건별 비교표

| 조건 | 유효 타구 | 표시 점수(m) | 접촉점 vx (m/s) | exit_speed (m/s) | 발사각(°) | 재접촉 | 장시간접촉 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `arm_only` | ✅ | 2.63 | 7.32 | 9.30 | -11.7 | 0 | 아니오 |
| `torso_only` | ❌ | 0.0 | 4.86 | 19.21 | +13.1 | 0 | 아니오 |
| `simultaneous` | ✅ | 0.67 | 7.80 | 10.66 | -52.1 | 0 | 아니오 |
| `staggered` | ✅ | **3.64** | **8.30** | 11.12 | -6.7 | 0 | 아니오 |

`torso_only`는 접촉은 발생했고(`contact_occurred=true`, `recontact_count=0`) exit_speed
자체는 오히려 가장 높지만(19.21 m/s) 방향이 전방 부채꼴을 벗어나 `scoring_valid=false`다
— 빠르게 빗맞은 파울성 타구에 가깝다. "몸통이 세게 밀어내면 무조건 유리하다"는
가정이 틀렸음을 보여주는 사례다.

## 2. 기계적 일·피크 출력/토크 (모터 추가 효과와 협응 효과 분리)

관절별 (양의 일 / 음의 일 / 피크 |출력|), 단위 J와 W. "비참여 축"도 컨트롤러의
유지 P제어가 반작용을 억제하려고 실제로 일을 한다 — 0이 아니다(§3의 관성 결합과
같은 현상).

| 조건 | torso | swing | tilt | 순 액추에이터 일(J) | 점수/양의 일 |
| --- | --- | --- | --- | --- | --- |
| `arm_only` | +3.53/-4.90J, 46.3W | +23.68/-3.88J, 410.8W | +0.87/-1.07J, 10.0W | 18.23 | 0.0935 |
| `torso_only` | +15.57/-7.23J, 102.8W | +44.93/-30.76J, 169.2W | +7.75/-8.42J, 30.6W | 21.84 | 0.0000 |
| `simultaneous` | +4.53/-8.88J, 95.5W | +32.94/-4.45J, 482.7W | +0.38/-0.46J, 7.1W | 24.05 | 0.0177 |
| `staggered` | +12.99/-6.98J, 140.2W | +40.34/-1.30J, 601.1W | +0.95/-1.41J, 11.5W | 44.59 | **0.0671** |

(피크 토크는 네 조건·모든 관절에서 각 축의 최대 gear×ctrl 한계인 30/30/6 N·m에
도달한다 — 모든 조건이 동일 하드웨어 한계를 실제로 쓰고 있다는 뜻이다.)

**해석**: `staggered`가 가장 큰 순 액추에이터 일(44.6J)과 가장 큰 두 축의 피크
출력을 쓴다 — 더 많은 일을 했으니 결과가 좋은 것은 당연해 보일 수 있다. 그러나
`simultaneous`도 거의 같은 하드웨어로 비슷한 총 일을 하지만(24.0J, 오히려 더
적음) 점수는 `staggered`의 1/5에 불과하다 — **투입 에너지량이 아니라 트리거
시점(협응)이 이 차이를 만든다는 것**을 "점수/양의 일" 비율이 보여준다:
`staggered`≈0.067, `simultaneous`≈0.018점/J — 약 3.8배 차이. `torso_only`는
양의 일을 가장 많이 하고도(68.25J, torso+swing+tilt 합) 점수가 0이다 — 일을
많이 한다고 유효 타구가 보장되지 않는다는 것도 함께 보여준다. 이는 "모터가
커져서 좋아진 것"과 "타이밍이 좋아서 좋아진 것"을 분리하려는 원래 설계 의도가
실제로 관측됨을 뜻한다.

## 3. 무공 검증 (`docs/records/evidence/KC-01a-noball-validation.json`)

- **관절 방향**: torso/swing/tilt 모두 ctrl=+1에서 양의 각속도로 반응(부호 오류 없음).
- **관성 결합**: swing만 전력 구동(torso ctrl=0)했는데도 torso 각도가 0.285rad까지
  끌려갔다 — 두 축이 실제로 역학적으로 결합돼 있다는 직접 증거(디커플링 버그 아님).
- **에너지 수지**: 비참여 축도 액추에이터 일이 0이 아니다(예: `arm_only`의
  torso도 +3.53/-4.90J를 한다, §2) — 유지 P제어가 반작용을 억제하려고 실제로
  토크를 낸다는 뜻이며, 무공 검증의 관성 결합 결과와 같은 현상이다. 모든 조건의
  양/음의 일이 유한하고 부호가 물리적으로 타당해 무한 에너지 생성은 없다.
- **정착(0.5s + 연속 0.2s 유지 기준)**: **네 조건 모두 착지 전 episode 길이 안에서
  이 기준을 확정적으로 채우지 못했다.** 착지가 상대적으로 빨라(타구 비거리가
  짧을수록 비행시간도 짧다) 접촉 후 관찰 창이 부족했다 — `staggered`는 종료
  시점 속도가 이미 임계값(0.2rad/s) 근처까지 떨어져 있었고(torso 0.10rad/s대,
  swing 0.02rad/s대) 사실상 수렴 중이었지만, `simultaneous`는 종료 시점에도 여전히
  빠르게 움직이고 있었다(torso 2-3rad/s, swing 5-9rad/s) — 두 조건의 실질 수렴
  양상이 다르다는 것 자체가 유의미한 차이다. **정착 여부를 임의로 통과 처리하지
  않고, 착지 후에도 물리를 계속 진행하는 확장 관찰이 필요하다는 것을 다음 단계로
  남긴다.**

## 4. 타이밍(±5ms)·물리 timestep 민감도

| 조건 | -5ms | 기준 | +5ms | dt 절반 |
| --- | --- | --- | --- | --- |
| `arm_only` | 무효 | **유효(2.63)** | 무효 | (미측정) |
| `torso_only` | 무효 | 무효 | 무효 | (미측정) |
| `simultaneous` | 무효 | **유효(0.67)** | 무효 | 유효(0.51, 값 변화) |
| `staggered` | 무효 | **유효(3.64)** | 무효 | **무효(0.0)** |

B1에서 이미 확인된 "±5ms 한 제어주기 차이로 유효/무효가 뒤집히는" 취약성이
KC-01a의 네 조건 모두에서 재현된다 — **몸통을 추가해도 이 취약성이 해결되지
않는다.** 물리 timestep을 절반(0.000125s)으로 줄이면 `simultaneous`는 유효를
유지하되 점수가 바뀌고(0.672→0.510), 가장 성적이 좋았던 `staggered`는 **무효로
뒤집힌다** — 가장 좋아 보였던 결과가 dt 수렴 확인을 통과하지 못했다는 것을
숨기지 않는다.

## 5. 그립 오류 확인 (`docs/records/evidence/KC-01a-grip-reach-check.json`)

네 조건 모두 전체 episode 동안 `FrontLegGripOverlay`의 `reach_error`가 **항상
0m**였다(팔을 늘리거나 그립을 놓친 프레임 없음). 몸통 회전이 상당한 각도
(`torso_only`는 +0.6rad 한계 근처까지)에 이르러도 앞다리 자연 길이(K=400, 3구간
합 0.580m)로 그립을 계속 따라갈 수 있었다.

## 6. 성공·실패 원인

- **`staggered`가 이긴 이유(가설, 완전 증명 아님)**: 몸통이 먼저 움직이기 시작해
  팔이 트리거될 때 이미 몸통이 상당히 회전한 상태이고, 접촉 시점에 두 축의
  운동량이 "겹쳐서" 배트 끝 속도가 더 커진다(§1의 vx 8.30 vs `simultaneous`의
  7.80). 단, 근본 원인을 관절별 속도-시간 그래프 이상으로 더 분해하지는
  않았다(다음 단계 후보).
- **`torso_only`가 실패한 이유**: 몸통(35kg)의 관성이 배트(0.9kg)보다 압도적으로
  커서, 같은 gear=30이라도 도달 가능한 각가속도(11.4rad/s²)가 swing(134.4rad/s²)의
  1/12 수준이다. 배트 끝까지의 모멘트암이 더 길어도(§1) 각속도 부족을 상쇄하지
  못했다 — **저관성 말단 관절(팔)이 고관성 몸통보다 배트 끝 속도를 내는 데
  구조적으로 유리하다**는 것이 이번 비교의 가장 명확한 음성 결과다.
- **`simultaneous`가 약했던 이유**: 몸통(자연 완료 시간 ≈0.3s)과 swing(≈0.14s)의
  소요 시간이 크게 달라, 같은 순간 트리거하면 접촉이 swing 위주로 일찍
  끝나버려 몸통 기여가 온전히 실리지 못한다 — 이것이 "협응 시점"이 성능에
  실제로 영향을 준다는 구조적 근거다.

## 7. 다음 단계 제안 (이번 정리에 포함하지 않음)

1. **타이밍 취약성**은 KC-01a에서도 해결되지 않았다 — 사용자 지시대로 이번
   작업에 포함하지 않았고, 몸통 도입과 별개로 다뤄야 한다.
2. 정착(§3) 확인을 위해 착지 이후에도 물리를 일정 시간 더 진행하는 확장
   관찰이 필요하다.
3. `staggered`의 dt 비수렴(§4)은 재료/트리거 재탐색 없이 원인(접촉 시점 자체가
   dt에 따라 이동하는지, 후속 궤적만 갈라지는지)을 더 분해해야 한다.
4. KC-01b(뒷다리 접지·실제 지지)로 진행하기 전에, `torso_only`의 실패가 "몸통
   관성이 근본적으로 너무 크다"는 것인지 "이 gear/트리거 조합의 한계"인지
   추가 gear 스윕으로 구분하면 좋다(이번엔 하지 않음, `docs/research/
   BATTING-KINETIC-CHAIN.md`가 이미 KC-01b를 별도 설계로 요구).
5. 8코스 확대·변화구·RL·실제 뒷다리 지지는 이번 작업 범위 밖(사용자 지시).

## 8. 산출물 경로

- 구조도: `runs/kc01a-comparison/kc01a_structure_diagram.png`
- 각도/속도 비교 그래프: `runs/kc01a-comparison/kc01a_angle_velocity_comparison.png`
- 제어 신호 비교 그래프: `runs/kc01a-comparison/kc01a_control_signals_comparison.png`
- 동일 카메라(park_wide/batter_side) 비교 영상:
  `runs/kc01a-comparison/video/{arm_only,torso_only,simultaneous,staggered}/*.mp4`
  (+ `manifest.json`, `comparison_manifest.json`)
- 원자료(추적됨): `docs/records/evidence/KC-01a-comparison.json`,
  `KC-01a-noball-validation.json`, `KC-01a-grip-reach-check.json`,
  `KC-01a-timelines/*.json`, `docs/design/KC-01a-calibration.json`

`runs/`는 `.gitignore` 대상이라 영상·그림 파일 자체는 커밋되지 않는다(기존
프로젝트 관례와 동일) — 수치 원자료는 위 `docs/records/evidence/`에 추적된다.

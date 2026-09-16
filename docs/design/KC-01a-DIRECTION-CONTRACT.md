# KC-01a — 회전 방향 계약 (torso/swing 부호와 실제 월드 방향)

id: KC-01a-DIRECTION-CONTRACT · status: adopted · version: 0.1 · 2026-09-17 ·
근거: 사용자 지적("simultaneous/staggered는 몸통 음의 회전, 배트 양의 회전으로
접촉 직전까지 서로 반대로 구동된다") · 관련: `docs/design/
KC-01a-TORSO-BAT-COORDINATION.md`, `docs/records/KC-01a-VALIDATION.md`,
`controllers/baseball_kc01a.py`

## 1. 기구학적 사실 (수정 불가능한 전제)

`envs/assets/baseball_park_kc01a.xml`: `torso_yaw`(`axis="0 0 1"`, world Z)와
`bat_hinge`(`axis="0 0 1"`, torso_body 로컬 Z — 두 힌지 모두 같은 축이므로
torso_yaw의 회전과 무관하게 같은 방향을 가리킨다)는 **같은 world Z축에 대한
연속 회전**이며 `bat_hinge`는 `torso_body`의 자손이다. 같은 축에 대한 연속
회전은 교환·가산적이므로:

```
world_bat_angle(t) ≈ torso_yaw(t) + swing(t) + const
world_bat_angular_velocity(t) = torso_yaw_vel(t) + swing_vel(t)
```

**즉 torso와 swing의 부호가 같으면 두 축의 각속도가 배트 끝 월드 각속도에
더해지고(가산적 kinetic chain), 부호가 반대면 서로를 상쇄한다.** 이는 근사가
아니라 이 두 힌지가 같은 축이라는 사실에서 바로 나오는 등식이다(제3항인
tilt는 다른 축(`axis="0 -1 0"`)이라 이 등식에 들어가지 않는다).

## 2. 현재 4개 조건의 실제 부호 (재확인, 수정 없음)

`prep_swing=-1.96`은 모든 조건에서 공통이며 swing은 항상 `target > prep`이므로
swing_dir은 **항상 +1**(증가 방향)이다. torso는 조건마다 다르다:

| 조건 | prep_torso | torso_target | torso_dir | swing_target | swing_dir | 두 축 관계 |
| --- | --- | --- | --- | --- | --- | --- |
| `arm_swing_with_torso_hold` | 0.0 | 0.0(고정) | — | -1.298 | +1 | torso 미참여 |
| `torso_swing_with_arm_hold` | 0.0 | **+0.496** | **+1** | -1.96(고정) | — | swing 미참여 |
| `simultaneous_swing_and_torso` | 0.0 | **-0.4** | **-1** | -0.726 | +1 | **역방향(상쇄)** |
| `staggered_swing_and_torso` | 0.0 | **-0.4** | **-1** | -0.726 | +1 | **역방향(상쇄)** |

`torso_swing_with_arm_hold`(단독 축)가 스스로 찾은 부호는 **+**(swing과 같은
부호)인데, `simultaneous`/`staggered`의 목표각은 `scripts/kc01a_calibrate.py`
`step1_geometry`의 `shared` 탐색이 `tt in (-0.2, -0.3, -0.4, -0.5)`로 **음수만
훑었기 때문에** 찾아진 값이다(코드 상 하드코딩된 탐색 범위 제한이지 물리적
근거가 있는 제한이 아니다). 그 결과 `simultaneous`/`staggered`가 요구하는
swing 이동량(Δ=1.234rad, prep -1.96→target -0.726)은 `arm_swing_with_torso_hold`
혼자(Δ=0.662rad, prep -1.96→target -1.298)의 거의 두 배다 — torso가 도와주는
게 아니라 **swing이 torso의 역회전분까지 추가로 메워야 했다**는 정량적
증거다. 이것이 이전 비교에서 `simultaneous`/`staggered`의 협응 "이득"이
실제로는 존재하지 않았거나 과대평가됐을 수 있다는 구조적 근거이며, dt
민감도(§KC-01a-VALIDATION.md A2)가 유독 이 두 조건에서 심한 것과도 무관하지
않을 수 있다(상쇄에 가까운 배치는 작은 섭동에 더 민감할 수 있다는 가설 —
아직 검증 안 됨, §5).

## 3. 이 발견을 다루는 방식

- **기존 4개 조건(위 표)은 진단용 기록으로 그대로 보존한다.** 수치·XML
  기본값·컨트롤러 코드를 바꾸지 않는다 — "무엇이 잘못됐는지"를 보여주는
  유효한 데이터다.
- **준비(prep) 동작과 가속(accelerate) 구간을 구분한다.** 현재 컨트롤러
  구조(`controllers/baseball_kc01a.py`의 `_Axis`)에는 별도의 "감아넣기(windup)"
  하위 상태가 없다 — `prepare`에서 곧장 `accelerate`로 가서 `accel_target`까지
  간다. 즉 지금 `simultaneous`/`staggered`의 torso 역회전은 생물학적 "코킹
  동작"이 아니라 **탐색 범위 제한이 만든 우연한 목표각**이다. 새 조건을
  설계할 때 "준비 자세 자체가 반대 방향인 것"과 "가속 구간이 반대 방향으로
  구동되는 것"을 같은 문제로 섞지 않는다 — 후자만 실제 결함이다.
- **가속(hitting) 구간의 방향 규칙**: torso와 swing 모두 **양(+)의 부호**로
  가속해 배트 월드 각속도에 가산적으로 기여해야 "협응"이라고 부를 수 있다.
  torso가 먼저 트리거되고(`torso_ct > swing_ct`, `staggered`류 타이밍) swing이
  이어받는 배치(근위→원위 순서, proximal-to-distal sequencing)가 실제 운동
  사슬과 일치한다.
- **제동(brake) 토크의 부호 ≠ 실제 회전 방향.** `_Axis.act`의 `brake` 상태는
  `_damped(follow_through_target, angle, vel, kp, kd)`로, 목표(`accel_target`
  보다 살짝 더 간 지점)를 향한 PD 제어다 — 각도가 이미 목표를 넘었다면
  `ctrl`은 감속을 위해 음(-)이 될 수 있지만, 이는 "액추에이터가 반대 방향
  토크를 낸다"는 뜻이지 "관절이 반대 방향으로 회전한다"는 뜻이 아니다.
  각도(`qpos`)와 각속도(`qvel`)의 부호가 실제 회전 방향이며, 리포트/그래프는
  항상 `ctrl`(토크 명령)과 `qpos`/`qvel`(실제 운동)을 별도 계열로 그린다
  (§4의 타임라인 스키마).

## 4. 새 "동방향(same-direction)" 조건 설계 규칙

`docs/records/evidence/KC-01a-same-direction-search.json`(구현은
`scripts/kc01a_same_direction_search.py`)이 실제로 따르는 규칙:

1. torso_target은 **양수**(swing_dir=+1과 같은 부호)만 탐색한다 — §2의 하드코딩
   제한을 제거하고 `torso ∈ (0, +0.6]`(관절 한계 이내) 범위를 훑는다.
2. 준비각(prep_torso, prep_swing)은 바꾸지 않는다(0.0, -1.96 그대로) — 코킹
   단계 자체를 새로 설계하는 것은 이번 범위 밖이다(§3의 구분에 따라, 지금
   필요한 것은 가속 구간의 부호 수정이지 새로운 준비 동작이 아니다).
3. 접촉 자세(목표점까지의 거리)와 swing/tilt 목표각은
   `scripts/kc01a_calibrate.py`의 `grid_refine`을 그대로 재사용해 torso_target
   마다 다시 계산한다(목표각 부호만 뒤집고 swing/tilt를 그대로 두지 않는다).
4. 그립 도달성(`envs/fly_visual.py`의 `FrontLegGripOverlay.update` 반환값)을
   후보 궤적 전 구간에서 확인하고, 도달 불가 구간이 있으면 그 후보를 버린다.
5. 트리거 시각(torso_ct, swing_ct)은 새 목표각에 맞춰 다시 탐색한다(옛 조건의
   트리거 값을 재사용하지 않는다) — torso가 swing보다 먼저 트리거되는 배치를
   우선 탐색한다(`torso_ct > swing_ct`).
6. 새 조건에도 `docs/records/KC-01a-VALIDATION.md` A2와 동일한 사전 등록
   기준으로 timestep 수렴을 확인하기 전에는 "협응이 개선됐다"고 결론 내리지
   않는다(`scripts/kc01a_same_direction_dt_convergence.py`).

## 5. 남은 가설 (이번에 검증하지 않음)

- "역방향(상쇄) 배치가 dt 민감도를 키운다"는 것은 아직 가설이다 — 새
  동방향 조건의 dt 수렴 결과(§4-6)가 실제로 더 안정적인지 확인해야 뒷받침
  된다. 새 조건도 발산하면 이 가설은 기각된다.
- torso가 swing보다 훨씬 크게(혹은 작게) 기여하는 배치들 사이의 상대적
  우열은 이번 범위에서 다루지 않는다 — 첫 번째로 "부호가 맞는" 배치 하나를
  찾아 같은 검증 절차를 적용하는 것이 이번 목표다.

## 6. "선행(lead)"을 실제로 측정하는 방법 — 명령 트리거 vs raw qvel (후속)

`docs/records/KC-01a-VALIDATION.md` A9-A14에서 검증한 결과, §4에서 채택한
`same_direction_staggered`(torso_ct가 swing_ct보다 10ms 이른 **고정 시간차**)는
실제로는 "선행"이라 부를 수 없다는 것이 드러났다: torso와 swing의 raw
qvel이 임계값(0.05rad/s)을 넘는 시각이 **완전히 같은 제어주기**였다. 원인은
§1의 기구학적 사실과 같은 곳에서 나온다 — `bat_hinge`가 `torso_yaw`의
자손이므로, torso가 가속하면 그 관성 반작용이 swing 자유도의 raw qvel을
즉시(반작용 각속도로) 흔든다. **swing 자신의 액추에이터가 켜지기 전에도
swing_qvel은 반작용만으로 임계값을 넘을 수 있다** — 이 사슬 구조 위에서는
"두 축의 raw 각속도가 언제 움직이기 시작했는가"로 선행을 측정하는 것 자체가
근본적으로 신뢰할 수 없다.

**정정된 계약**: "선행"은 반드시 **각 축 자신의 컨트롤러 트리거**
(`TorsoBatController`의 `_torso_triggered`/`_swing_triggered`, 즉 그 축이
"prepare"/hold에서 "accelerate"로 전환되는 시각)로 정의한다. raw qvel
임계값 교차 시각은 참고 자료로만 보고하고(반작용 오염 가능성을 항상 함께
표기), "선행" 주장의 근거로 단독으로 쓰지 않는다.

## 7. Motion-triggered handoff 모드 (고정 시간차 대신)

작은 고정 시간차(10ms)는 torso의 낮은 최대 각가속도(11.41rad/s², swing의
134.4rad/s²보다 약 12배 작음) 때문에 실제 운동에서 무의미해진다 — torso가
그 10ms 안에 얻는 각속도가 너무 작아 swing의 반작용 흔들림에 묻힌다. 진짜
의미 있는 선행을 만들려면 "고정 시간"이 아니라 "torso가 실제로 얼마나
움직였는가"에 swing의 트리거를 거는 것이 필요하다는 결론에 따라
`controllers/baseball_kc01a.py`에 새 모드 `"torso_lead_handoff"`를
추가했다: swing은 torso의 각변위가 자기 목표의 `handoff_fraction`에 도달할
때까지 순수 P-hold만 하고, 그 전까지는 최대 토크로 가속하지 않는다(§4 규칙
2의 "모든 축을 최대 입력으로 몰지 않는다" 요구와 §5의 "선행 시간을 늘리면
항상 낫다고 가정하지 않는다" 요구를 함께 만족 — 실제로 60개 조합 중
2개, 확장 탐색 140개 중 10개만 유효했고 handoff_fraction이 클수록 항상
좋아지지도 않았다). 기존 4개 모드(`arm_only`/`torso_only`/`simultaneous`/
`staggered`)의 동작은 이 추가로 전혀 바뀌지 않는다(코드·테스트로 확인).

가장 좋았던 것으로 보고했던 결과(torso_target=0.5, torso_ct=0.33,
handoff_fraction=0.5, 225ms 선행, production dt 6.78m)는 **철회한다**
(`docs/records/KC-01a-VALIDATION.md`의 "정정" 항목, A11-A14는 참고 기록으로
보존). 방향(torso +, swing −)이 반대였고, swing의 명령 변위가 사실상 0
(−0.004rad)이었으며, 양 축 follow-through 목표가 모두 자기 관절 범위
밖이었다 — "동방향" 조건도, "팔이 스윙하는" 조건도 아니었고, torso 정착은
관절 하드 스톱에 눌린 결과였다. 탐색·검증 어디에서도 방향/변위/범위를
사전에 확인하지 않은 것이 원인이다.

## 8. 유효성 검사 정정 (사용자 지시)

위 문제를 막기 위해 `controllers/baseball_kc01a.py`에
`validate_same_direction_candidate(prep_torso, prep_swing, torso_target,
swing_target, min_swing_displacement_rad=0.3, joint_margin_rad=0.02)`를
추가했다 — 어떤 후보든 시뮬레이션 전에 (1) torso/swing 가속 방향 일치,
(2) 최소 팔 스윙 변위, (3) 양 축 prep/target/follow-through의 관절 범위
여유를 검사하고, 실패 이유를 전부(첫 번째에서 멈추지 않고) 보고한다.

`torso_lead_handoff`의 인계 조건도 고쳤다: swing의 트리거가 원래
`abs(torso_angle - prep_torso) >= handoff_target_disp`(절대 각변위)를
썼는데, 이러면 torso가 **의도한 반대 방향**으로 그만큼 움직여도 인계가
발생할 수 있었다(사용자 지적, 실제로 이 버그가 발현된 사례는 아직 없었지만
잠재적 결함이었다). **의도한 방향으로의 부호 있는 진행량**
`(torso_angle - prep_torso) * torso_dir >= handoff_target_disp`으로
수정했다. `tests/test_baseball_kc01a_controller.py`에 두 정정 모두의
회귀 테스트를 추가했다 — 기존 4개 모드의 동작은 무변경(같은 테스트 파일의
`TestExistingModesUnaffected`, 그리고 기존 99개 테스트가 그대로 통과)이며,
"기존 테스트가 통과한다"는 사실 자체는 새 모드/새 함수의 검증으로 쓰지
않는다(새로 추가한 10개 테스트가 새 동작을 검증한다).

이 검사를 적용해 재탐색한 결과(`scripts/kc01a_torso_lead_handoff_search_v2.py`)
torso_target=0.25/swing_target=−1.644/torso_ct=0.16/handoff_fraction=0.1이
방향·변위·범위 검사와 양 축 능동 제동 정착·그립 도달성을 모두 통과했지만,
**timestep 수렴에는 실패한다**(`docs/records/KC-01a-VALIDATION.md` A17) —
유효성 검사를 고친 것과 dt 수렴은 별개의 문제였다. 접촉 침투(−0.055~
−0.057m)도 §A9와 같은 이유로 미해결로 남긴다. "방향·변위·범위가 맞고,
능동 제동으로 정착하고, 동시에 dt 수렴하는" 몸통 선행 후보는 아직 없다.

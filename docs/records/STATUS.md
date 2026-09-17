# 현재 상태

2026-09-17 갱신(VM-01 방향 전환: 시각·파리 몸 기반 학습). 이 문서는
**지금** 무엇이 검증됐고 무엇이 막혀 있는지만 담는다. 시행착오·정정 경위·과거
수치는 [상태 이력](STATUS_HISTORY.md)에, 실행 명령·원자료는
[검증 기록 색인](VALIDATION_LOG.md)에 있다. 다음 작업 배정은
[구현 작업표](../implementation/WORK_PACKAGES.md)를 따른다.

## VM-01 — 시각·파리 몸 기반 학습 전환 (현재 배정, 사용자 승인 2026-09-17)

[작업 명세](../tasks/VISUOMOTOR-PIVOT.md), [전체 보고](VM01-REPORT.md).
KC-01a 후보 추가 탐색과 gear 재보정은 이 전환으로 **보류**됐다(아래 KC-01a
절은 그 시점까지의 기록으로 그대로 보존).

- **V1(눈 영상·공 추적) — PASS(한계 명시)**: `envs/assets/
  fly_visual_body.xml`의 Head body에 실제 카메라(`eye_cam`)를 부착했다
  (기존 `fly_pov`는 world 고정이라 재사용하지 않음, 위치/방향을
  `mj_forward` 직후 직접 읽어 검증). 정답 공 좌표를 전혀 읽지 않는 색상
  기반 고전 검출기(`vision/ball_detector.py`)와 추적기(`vision/
  tracker.py`)를 구현했고, AST 기반 정적 검사로 정책 경로 모듈이 평가자
  모듈(`vision.evaluator`)이나 `envs.*`를 import하지 않는다는 것을
  확인했다. 실측(`docs/records/evidence/VM01-vision-baseline.json`):
  해상도/FOV 4개 조합 중 320px/FOV60°가 최고 검출률(96.4%), 128px/
  FOV90°가 최저(17.2%) — `docs/design/VISION-01.md` §3이 가설로 남겼던
  "서브픽셀 구간은 검출 어려움"을 처음 실측으로 확인했다. 릴리스 지터·
  가림·동결·지연 진단(`docs/records/evidence/VM01-vision-diagnostics.json`)
  모두 예상대로 동작(가림 시 검출률 0%, 지터에도 검출률 유지). 한계:
  그레이스케일 전용 검출은 미검증, 시간적 예측(칼만류) 없음.
- **P1(독립 충돌 검증) — FAIL**: 배트·몸통 제어를 완전히 제거한 분리
  실험(`envs/assets/contact_validation_p1.xml`)에서 관통 깊이(0.046~
  0.048m)와 반발계수(고정 타격면 -0.298, 자유 배트 0.294) 모두 사전
  등록 기준을 통과하지 못했다(`docs/records/VM01-P1-CONTACT.md`). 가장
  중요한 발견: 고정 타격면의 음의 반발계수는 dt를 production 대비
  1/256까지 세분화해도 변하지 않는다 — 이산화 오차가 아니라 이 접촉
  재료가 정면 충돌에서 실제로 반발하지 않는다는 dt-수렴된 결과다.
  운동량 보존은 중력 기여를 보정하면 기계정밀도 수준으로 확인됨(초기
  "12% 위반"은 관측 창에 걸친 중력의 정상적 효과였음). **이 검증이
  통과할 때까지 학습 개시를 보류한다.**
- **B1(파리 관절 최소 몸체) — NOT-RUN(설계만, 지시된 범위)**:
  `docs/design/VM01-B1-MINIMAL-BODY.md`. flygym==1.2.1 원본(스트립 전)
  MJCF를 직접 받아 확인해, 다리당 7개 능동 자유도(Coxa yaw/pitch/roll,
  Femur pitch/roll, Tibia pitch, Tarsus1 pitch)와 위치(P) 제어라는
  사실을 확보했다. 절대 질량/토크 단위는 raw XML 질량 합(≈1.0)과 컴파일된
  모델의 실제 질량 합(≈0.00026)이 불일치해 **미해결로 명시**했다(임의
  숫자 없음). 최소안으로 "지지된 몸통 + 앞다리 1개(7DOF) + 도구 부착"을
  제안하고, 공/도구 크기는 정식 야구공이 아니라 현재 앞다리 도달거리
  (0.580m)의 10~20%로 줄일 것을 제안했다 — 인간식 직립·고정 스윙 순서는
  요구하지 않는다.
- **연구 트랙 구분**: 위 세 작업은 모두 일반 정책(환경 기준선) 트랙이다.
  `encoders/retina_encoder.py`(정답 좌표 직접 사용하는 초기 스켈레톤)나
  EXP-001의 실제 MaleCNS 회로 학습과는 독립이며, 이번에 수정하지 않았다.

## 두 개의 독립 트랙(신경회로/물리, KC-01a까지의 기록 — VM-01 전환 이전)

이 프로젝트는 서로 독립적으로 진행되는 두 트랙을 갖는다(`docs/PLAN.md` D08).
하나가 막혀도 다른 하나는 계속 진행할 수 있다.

### 1. 신경회로 트랙(연구 본류) — 착수 전

`docs/PLAN.md`/`docs/design/DATA_MODEL.md`/`docs/experiments/EXP-001-associative-learning.md`의
규약(1.0)은 확정됐지만 **실제 구현은 아직 없다.** `encoders/`·`train/`·`analysis/`는
여전히 처음의 toy scaffold이고(`train/train_stdp.py`는 실행하면 명시적으로
"구현 안 됨" 오류를 낸다), MaleCNS 실제 데이터는 취득하지 않았으며, `tests/`에는
신경회로 테스트가 하나도 없다.

**문서 정리 중 발견한 부정확한 기록**: `docs/implementation/WORK_PACKAGES.md`의 이전
버전은 I-04/I-05/I-06을 "완료: T03~07"/"완료: T08"/"완료: T09"로 표시하고 있었다.
위 실제 코드/테스트 현황과 대조한 결과 이 표시는 근거가 없다 — 실행된 적 없는
작업을 완료로 표시한 문서 결함이며, 이번 정리에서 I-02/I-04/I-05/I-06을 전부
"미착수"로 정정했다. 새 신경회로 구현/실험은 이번 정리 범위가 아니다(비목표).

### 2. 물리 환경 트랙(ENV-001 → ENV-002) — mid_mid까지 검증

- **ENV-001**(초파리 단순 타격 과제): I-03b에서 초기 관통·구동 보정·사건 순서
  결함을 수정하고 시험 시드(n=100) 기준을 충족했다. 회귀 fixture로 유지 중.
- **ENV-002 B0**(야구장·고정 직구): I-07a/I-07a-1에서 구장 배치를 공식 PDF와
  대조하고 접촉창 수렴(dt=0.00025s)·보상(`b0-contact-v1`)을 확정했다.
- **ENV-002 B1**(조준·9코스, `docs/design/BASEBALL-SPEC.md`): 틸트 축(2번째
  조준 축)과 9코스 좌표는 구현·기하학적 도달성 확인까지 끝났다. **실제 야구
  타격(공을 +x 인필드로 보내 착지까지 추적)은 `mid_mid` 코스 하나만 재보정·검증됐다.**
  나머지 8코스는 이전(접촉-only, 역방향 스윙) 시절 값 그대로 남아 있고 사용
  금지로 코드/문서에 명시돼 있다.
- **파리 외형**(`docs/design/FLY-VISUAL-SPEC.md`): NeuroMechFly 메시를 물리와
  분리된 시각 레이어로 적용했다. 앞다리 2개 그립·뒷다리 2개 접지·중간다리 접기,
  전신 동일 배율, 옆선 자세(머리만 투수 방향), 원본 부위별 색상까지 검증됨.
- **타구 거리 점수**(`forward-carry-v1`): 구현·검증 완료. 기본 `reward_version`은
  여전히 `batted-ball-v1`이다 — 의도적으로 조용히 바꾸지 않았다(순수 정리 원칙).
- **mid_mid 최종 수치**(`OracleAimController`, `docs/records/evidence/R00-baseline-mid_mid-before-after.json`에
  qpos/qvel까지 고정): 접촉점 속도 7.62m/s, exit_speed 8.61m/s, 발사각 41.2°,
  carry 8.48m(`batted-ball-v1` 기준 old 5.82m 대비 +46%), scoring_valid=true,
  재접촉 0.
- **KC-01a**(`docs/design/KC-01a-TORSO-BAT-COORDINATION.md`, B1과 별도 모델·XML·
  env, B1은 무변경): 고정 기반 위 실제 유한 관성 몸통 회전(`torso_yaw`)을 추가해
  배트 swing/tilt를 그 위에 얹었다. **조건 간 우위 비교는 아직 결론 낼 수
  없다** (`docs/records/KC-01a-VALIDATION.md`) — dt 수렴 검증(A2)을 4개 조건 중
  `torso_swing_with_arm_hold`(구 `torso_only`) 1개만 통과했고, 그 1개는
  일관되게 유효 타구 실패다. 이전에 "최고 성적"으로 보고했던
  `staggered_swing_and_torso`(구 `staggered`, score 3.64m)는 물리 timestep을
  정밀화하면 **무효로 뒤집힌다** — 그 결론은 철회됐다(`docs/records/
  KC-01a-COMPARISON.md` 상단에 정정 링크 추가, 원본은 보존). 정착은 착지 후
  관찰을 1.2s 이상 연장하자 3개 조건에서 명확히 확인됐고(`torso_swing_with_arm_hold`의
  torso만 실제로 미정착), 에너지 잔차는 관절한계 반력(`qfrc_constraint`)을
  포함하자 대부분(잔차 0.5~4.2%) 설명됐다 — `simultaneous`의 5.7~10.8%도
  후속 확인(아래)에서 평범한 절단오차로 밝혀졌다. 시각 정책 통합(`docs/design/
  VISION-01.md`, 설계만 완료)은 이 결과를 근거로 보류한다.
- **후속 원인 분리와 방향 계약**(`docs/records/KC-01a-VALIDATION.md` A6-A8,
  `docs/design/KC-01a-DIRECTION-CONTRACT.md`): dt 발산의 원인이 구동/적분이
  아니라 **접촉 계산 자체**임을 구동-전용·접촉-전용(동일 사전상태 재생) 분리로
  직접 확인했다(더 이상 "추정" 아님). 또한 `simultaneous_swing_and_torso`/
  `staggered_swing_and_torso`(옛 이름 `simultaneous`/`staggered`)의 torso
  목표각(-0.4)이 swing과 **반대 부호**로, `torso_yaw`/`bat_hinge`가 같은
  world Z축이라 배트 월드 각속도가 상쇄되고 있었다는 것을 발견했다 — 물리적
  근거가 아니라 탐색 범위 제한(torso 음수만 훑음)이 만든 값이었다. 이 두
  조건은 진단 기록으로 보존하고, 부호를 맞춘 새 조건 `same_direction_staggered`
  (torso_target=+0.3, swing_target=-1.710)를 탐색해 그립 도달성을 만족하며
  접촉점 속도에 torso/swing이 **같은 부호로 가산**(43%/57%)함을 확인했고,
  A2와 동일한 사전 등록 기준으로 dt 수렴도 **통과**했다(기존 4개 조건 중
  실제 타구가 나면서 수렴한 최초 사례).
- **`same_direction_staggered` 수용 검증과 몸통 선행 메커니즘**(`docs/records/
  KC-01a-VALIDATION.md` A9-A14): 수용 검증 결과 torso 축이 정착 기준을
  충족하지 못해 이 설정 그대로는 시각 기준선으로 채택하지 않는다. 에너지
  재계산 중 XML이 `integrator="RK4"`인데 이전 보고가 "semi-implicit Euler
  절단오차"라 잘못 설명한 것을 정정했다 — 실제 원인은 분석 스크립트 자신의
  work 적분(quadrature) 오차이며 RK4 상태 적분 자체는 이미 거의 완전히
  수렴해 있다. 사용자가 영상에서 지적한 "배트가 먼저 움직인다"는 인상은
  데이터로 확인됐다: `same_direction_staggered`의 "10ms 몸통 선행"은 raw
  qvel 기준 실제 선행이 0초다 — `bat_hinge`가 `torso_yaw`의 자손이라 torso
  가속이 swing 자유도에 즉시 반작용 각속도를 유도해 raw qvel 기반 측정을
  오염시키기 때문이다. 컨트롤러 자신의 트리거 시각으로 재정의하고,
  motion-triggered handoff라는 새 컨트롤러 모드(`torso_lead_handoff`)를
  추가해 재탐색한 결과 torso_target=0.5/torso_ct=0.33/handoff_fraction=0.5
  조건이 225ms의 진짜 제어 수준 선행, dt 수렴, 양 축 정착, 그립 도달성을
  모두 통과한 것처럼 보였다(production dt 6.78m) — **이후 철회했다.** 이
  조건은 실제로 몸통(+)과 팔(−)이 반대 방향으로 가속하는 명령이었고 팔의
  명령 변위는 사실상 0(−0.004rad), 양 축 팔로우스루 목표가 모두 자기
  관절 범위 밖이라 "정착"은 관절 하드 스톱에 눌린 결과였다 — 방향/변위/
  범위를 사전에 검사하지 않은 것이 원인이다. `controllers/baseball_kc01a.py`에
  `validate_same_direction_candidate`(방향 일치·최소 팔 변위·관절범위 여유
  사전 검사)를 추가하고 인계 조건도 절대 각변위 대신 부호 있는 진행량으로
  고친 뒤(회귀 테스트 10개 추가) 재탐색한 새 후보(torso_target=0.25,
  swing_target=−1.644)는 이 검사와 양 축 능동 제동 정착·그립 도달성을
  모두 통과하지만, **timestep 수렴에는 실패한다** — 유효성 검사를 고친
  것과 dt 수렴은 별개였다. 접촉 침투(약 −0.05m, 기존과 같은 수준)는 계속
  미해결로 남긴다. "협응 우위" 결론이나 시각 기준선 확정 채택은 아직 하지
  않는다.

## 알려진 한계 (임의로 고치지 않고 그대로 보고)

- **타이밍 취약성**: mid_mid의 스윙 트리거가 단 한 제어주기(5ms)만 어긋나도
  `forward_flight_success`가 뒤집힌다. 새/구 준비각 모두에서 확인된 기존 구조적
  문제이며 이번 정리에서 손대지 않았다. 이후 별도 실험(강건성 기준 수립)에서 다룬다.
- **틸트 축 정착 미충족**: 접촉 후 0.5s 이내 정착 목표를 gear=6의 실제 구동력
  한계로 채우지 못한다(약 0.6~0.9s 소요). 게인 튜닝이 아니라 gear 재보정이
  필요하며 보류 중이다.
- **8코스 미보정**: mid_mid 외 코스는 도달성(oracle 100%)만 확인됐고 실제 타구
  성공은 미검증. 사용 금지.
- **I-08b(전신 역학 통합) 미착수**: 현재 파리는 물리적으로는 단순 강체 배트
  기구이고 NeuroMechFly 메시는 순수 시각 오버레이다.
- **KC-01a는 고정 기반**: 뒷다리 지면 반력·균형 제어·실제 전신 역학은 KC-01b(다음
  단계, 미착수)다.
- **KC-01a는 dt 미수렴**: 4개 협응 조건 중 1개(`torso_swing_with_arm_hold`,
  일관되게 유효 타구 실패)만 timestep 수렴을 통과했다. 나머지 3개의 점수/유효
  여부는 물리 이산화에 민감해 신뢰할 수 없다 — 특히 `staggered_swing_and_torso`는
  정밀 dt에서 무효로 뒤집힌다. 원인은 접촉의 이산화 민감도로 **확인됐다**(더
  이상 추정 아님 — 구동-전용은 완벽히 수렴, 동일 충돌 직전 상태에서 접촉만
  재생해도 같은 패턴으로 발산), 재료/gear를 바꾸지 않고 진단만 했다
  (`docs/records/KC-01a-VALIDATION.md` A2/A6). 부호를 맞춘 새 조건
  `same_direction_staggered`는 dt 수렴을 통과했다(§A8) — 아직 정착/에너지/
  타이밍 미검증이라 협응 결론에는 쓰지 않는다.

## 테스트·린트

`python -m pytest`/`pytest` 두 진입점 모두 **125 passed**로 일치(B1/B0/
ENV-001 87개 + KC-01a 22개 무변경 + VM-01 V1 16개 신규). lint 클린
(`vision/` 포함). 비editable wheel 설치로 모델 로드까지
확인(`docs/records/evidence/R03-wheel-install-check.txt`) — `vision`
패키지 추가로 `pyproject.toml`의 `packages` 목록을 갱신하고 재설치했다.

## 다음 작업

[VM-01](../tasks/VISUOMOTOR-PIVOT.md)의 V1/P1/B1을 모두 완료해 보고했다
([전체 보고](VM01-REPORT.md)) — V1 PASS(한계 명시), P1 **FAIL**, B1
설계만(NOT-RUN). **P1이 FAIL이므로 학습 개시는 계속 보류한다.** 다음은
사용자가 명시적으로 지정한다: (1) P1 실패 원인 진단(충돌각 스윕,
`docs/records/VM01-P1-CONTACT.md`의 제안) 및 최소 수정안 적용 여부,
(2) B1 미해결 항목(질량/단위 규약 확정, 자연 관절범위 통계화) 해결 후
실제 구현, (3) KC 후보 탐색/gear 재보정은 이 전환으로 계속 보류. 기존
실패/철회 기록은 그대로 보존한다.

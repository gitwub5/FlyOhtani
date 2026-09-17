# VM-01 완료 보고 — V1/V2(눈 영상·추적), P1/P2(독립 충돌 검증), B1/B2(최소 몸체 설계)

2026-09-17 갱신(V2/P2/B2 후속 추가) · 기준: `docs/tasks/VISUOMOTOR-PIVOT.md`,
사용자 후속 지시(P2/B2/V2) · 세 갈래는 서로 독립 결과이며 하나로
뭉뚱그리지 않는다(작업 지시 4항).

## V1 — 눈 영상과 공 추적: **PASS**(조건부, 한계 명시)

구현: `vision/`(`eye_camera.py`, `ball_detector.py`, `tracker.py`,
`observation.py`, `evaluator.py`), `envs/assets/fly_visual_body.xml`의
`eye_cam`(Head body에 실제로 부착된 카메라, `fly_pov`가 아님), 스크립트
`scripts/vm01_vision_{baseline,diagnostics}.py`, 테스트
`tests/test_vision_v1.py`(16개, 전부 통과).

- **카메라**: Head body의 실제 자식으로 부착(`eye_cam`), 위치/방향을
  `mujoco.mj_forward` 직후 `data.cam_xpos/cam_xmat`에서 직접 읽어
  렌더와 대조 검증했다(위치는 torso_yaw 축에 거의 있어 회전해도 거의
  이동하지 않고, 방향만 torso_yaw만큼 정확히 회전 — 실측, 가정 아님).
- **검출/추적**: 정답 공 좌표를 전혀 읽지 않는 고전 컴퓨터 비전(색
  임계값 기반, `vision/ball_detector.py`)만 사용. 정적 검사
  (`tests/test_vision_v1.py::TestNoForbiddenChannelLeak`)로 정책 경로
  모듈이 평가자 모듈(`vision.evaluator`)이나 `envs.*`를 import하지
  않는다는 것을 AST로 확인했다.
- **실측 결과**(`docs/records/evidence/VM01-vision-baseline.json`,
  읽기 전용·비접촉, KC 타격 수렴을 기다리지 않음): 해상도/FOV 4개 조합
  비교 결과 **검출률(recall)이 조합에 크게 좌우된다** — 320px/FOV60°가
  최고(96.4%), 128px/FOV90°가 최저(17.2%). 정밀도(precision)는 모든
  조합에서 100%(오탐 없음 — 아래 버그 수정 후). 검출됐을 때의 위치
  오차는 항상 작다(0.8~1.1px 평균) — **한계는 검출 여부이지 정밀도가
  아니다.** 거리별 분해(근/중/원 3구간)에서 원거리(초반 비행)일수록
  검출률이 급격히 낮아지는 것을 확인해, `docs/design/VISION-01.md`
  §3이 "가설"로만 남겨뒀던 "서브픽셀 구간은 검출 어려움"을 **처음으로
  실제 렌더 실험으로 확인**했다.
- **발견하고 고친 버그**: 첫 버전은 색상 코사인 유사도로 "붉은 정도"를
  판정해, 흰색 파울라인(채도 없음)이 임계값을 넘어 오탐(FOV90°에서
  평균 오차 66~167px)을 냈다 — "초과 적색"(R − (G+B)/2) 방식으로
  교체해 해결(`vision/ball_detector.py`의 코드 주석에 근거 남김,
  회귀 테스트 `test_white_object_is_not_falsely_detected_as_red`).
- **진단 profile**(`docs/records/evidence/VM01-vision-diagnostics.json`):
  릴리스 위치/속도를 매 시드 무작위로 흔들어도(±10cm, ±2%) 정상 구간
  검출률 93.5% 유지(고정 시간표 암기가 아님을 시사). 가림(occlusion)
  구간은 검출률 0%로 정확히 억제됨. 동결(freeze) 구간은 검출률
  100%(정지 프레임 기반 단일-프레임 검출기의 당연한 결과이며, 이것만으로
  "시각 미사용"을 단정하지 않는다는 주의를 코드 주석/보고서에 명시).
  지연(0/1/3 tick) 조건 간 검출률 차이는 미미(93.3~92.7%).
- **한계(숨기지 않음)**: 이번 검출기는 정지-프레임 색 임계값뿐이며 시간적
  기억(칼만 필터 등)이 없다 — `vision/tracker.py`가 나이/불확실성은
  관리하지만 진짜 예측(prediction)은 하지 않는다. 그레이스케일 전용
  검출(VISION-01의 "기준선")은 이번에 구현/검증하지 않았다(RGB 색
  기반만 확인) — 명시적 한계로 남긴다.

### V2 — 시간적 추적·예측 추가: **PASS**(개선 확인, 비용도 확인)

구현: `vision/kalman_tracker.py`(등속도 칼만 필터, 픽셀 공간), 스크립트
`scripts/vm01_vision_v2_tracking.py`, 테스트 `tests/test_vision_v2.py`
(7개, 전부 통과). 기존 `vision/tracker.py`(마지막 위치를 그대로
유지하는 방식)는 **삭제하지 않고** 비교 기준으로 남겼다.

- **예측 동작**: 미검출 구간에서도 마지막으로 학습한 속도로 위치를
  전진 추정한다(정지해 있던 기존 방식과 다름) — 회귀 테스트
  (`test_prediction_extrapolates_position_during_a_gap`)가 위치가 실제로
  전진하는지, 불확실성이 시간에 따라 커지는지 확인한다. 지연(latency)
  적용 시 내부 상태는 마지막으로 처리한 캡처 시각에 머물고, 반환값만
  `now_s`까지 앞서 추정한다(내부 상태 오염 없음, 테스트로 확인).
- **정답 상태 분리**: `vision/kalman_tracker.py`도 `vision.evaluator`나
  `envs.*`를 import하지 않는다는 것을 AST로 정적 검사했다(V1과 동일한
  방식) — 정답 공 좌표는 이 스크립트의 평가 코드(`scripts/
  vm01_vision_v2_tracking.py`)에서만 읽는다.
- **실측 개선**(`docs/records/evidence/VM01-V2-tracking-comparison.json`,
  가림 구간 0.35~0.42s, 시드 5개): 가림 구간 평균 위치 오차가 기존
  방식(마지막 위치 고정) 42.2px에서 칼만 예측 30.3px로 **28% 감소**했다
  — 시간적 예측이 실제로 도움이 된다는 것을 정답 대비로 직접 측정했다.
  **비용도 숨기지 않는다**: 정상(비가림) 구간에서는 칼만 방식이 오히려
  약간 더 나쁘다(0.91px → 1.21px, 필터의 매끄럽게-하기 지연 때문으로
  추정) — 시간적 예측이 항상 공짜로 좋아지는 것은 아니라는 것을 그대로
  보고한다.

## P1 — 독립 충돌 검증: **FAIL**

전체 보고: `docs/records/VM01-P1-CONTACT.md`. 사전 등록 spec:
`docs/design/CONTACT-VALIDATION-P1-SPEC.md`. 요약: 배트·몸통 제어를
완전히 제거한 분리 실험(`envs/assets/contact_validation_p1.xml`,
`scripts/p1_contact_isolated.py`)에서 관통 깊이(0.046~0.048m, 기준
≤0.0075m)와 반발계수(고정 타격면 -0.298, 자유 배트 0.294, 기준
0.3~0.7) 모두 사전 등록 기준을 통과하지 못했다. **가장 중요한 발견**:
고정 타격면의 음의 반발계수는 dt를 production 대비 1/256까지 세분화해도
변하지 않는다 — 이산화 오차가 아니라 이 접촉 재료가 정면 충돌 기하에서
실제로 반발하지 않는다는, dt-수렴된 결과다. 운동량 보존은 초기에 12.1%
위반처럼 보였으나 60ms 관측 창에 걸친 중력의 정상적 기여였음을 확인,
보정 후 기계정밀도 수준(1e-16)으로 잘 보존된다 — 자유 충돌 자체의
solver는 건전하다. 5cm 침투가 기존 KC-01a/B1에도 있었다는 사실은 통과
근거로 쓰지 않았다(spec 지시대로). **원인/최소 수정안**은
`docs/records/VM01-P1-CONTACT.md`에 있다 — 다음 진단은 충돌각 스윕
(정면 vs 스윙에 가까운 비스듬한 각도)이며, 이번에 수행하지 않았다.
**학습 개시는 이 검증이 통과할 때까지 보류한다**(spec 5항).

### P2 — 원인 분리: 완료 (기하 문제와 재료 문제를 분리)

전체 보고: `docs/records/VM01-P2-CONTACT.md`. 구현: `scripts/
p2_contact_diagnosis.py`, `envs/assets/contact_validation_p2.xml`, 회귀
테스트 `tests/test_p2_contact.py`(6개, 전부 통과).

- **얇은 판 통과 확인**: 공(반지름 0.0366m)이 판(두께 0.02m)보다 굵어서,
  접촉이 끊기지 않은 채로 공 중심이 판 뒷면을 지나간다 — 그 한 접촉
  구간 안에서 **접촉 법선의 부호가 직접 뒤집히는 것을 관측**했다(추론
  아님). 이것이 P1의 음의 반발계수의 실제 메커니즘이다.
- **두꺼운 블록/평면과 비교**: 같은 재료를 공보다 두꺼운 블록이나 진짜
  평면(무한 반공간)에 쓰면 법선이 뒤집히지 않고 반발계수가 **양수로,
  세 dt에서 서로 수렴**한다(0.29 부근) — 기하를 고치는 것만으로 부호
  문제가 사라진다는 것을 직접 확인했다.
- **비스듬한 충돌이 정면 실패를 면제하지 않는다**: 자유 배트에 0°/20°/
  35° 입사각으로 충돌시켜도 법선 방향 반발계수는 0.28~0.29로 각도와
  거의 무관하다 — 사전 등록 기준(0.3~0.7)에 정면과 똑같이 근소하게
  못 미친다. 좋아 보이는 비스듬한 결과를 근거로 정면 실패를 덮지
  않았다(사용자 지시대로).
- **남은 문제**: 침투 깊이(~0.05m)와 반발계수(~0.29)는 기하·각도와
  무관하게 안정적이지만 여전히 기준 미달이다 — 이것은 재료 자체의
  특성이며 이번에 해결하지 않았다. 다음 단계는 새 진단 profile에서
  solref/solimp 후보 비교(비거리 기준 선택 금지, spec 유지)다.

## B1 — 파리 관절을 쓰는 최소 몸체: **NOT-RUN**(설계 완료, 구현 미착수 — 지시된 범위)

전체 설계: `docs/design/VM01-B1-MINIMAL-BODY.md`. 사용자 지시대로
"이번에는 설계/타당성 조사"만 수행했다 — 구현/테스트가 없으므로
pass/fail이 아니라 not-run으로 보고한다. 요약: 실제 flygym==1.2.1 원본
MJCF/포즈 데이터를 직접 받아 확인한 결과, 현재 리포의 앞다리
(`fly_visual_front_legs.xml`)는 관절·질량이 전혀 없는 순수 시각 IK
오버레이임을 재확인했고, 원본은 다리당 7개 능동 자유도(Coxa yaw/pitch/
roll, Femur pitch/roll, Tibia pitch, Tarsus1 pitch)를 위치(P) 제어로
구동한다는 사실을 확인했다. 절대 질량/토크 단위 규약은 raw XML의 질량
합(≈1.0, 정규화 추정)과 컴파일된 모델의 실제 질량 합(≈0.00026)이 서로
맞지 않아 **미해결로 명시**했다(임의 숫자로 채우지 않음). 최소 구현안은
"지지된 몸통 + 앞다리 1개(7DOF) + 도구 부착"(양손 그립은 불필요한 초기
병목으로 보류)을 제안했고, 공/도구 크기는 정식 야구공이 아니라 현재
앞다리 도달거리(0.580m, 기존 시각 자산 척도 재사용)의 10~20%로 줄이는
것을 제안했다. 인간식 직립·고정 스윙 순서는 요구하지 않는다.

### B2 — 단위 불일치 해결, 구현 명세 확정: 완료

전체 내용: `docs/design/VM01-B1-MINIMAL-BODY.md` §1.4/§8(갱신). 원본
FlyGym 로더(`flygym/fly.py`, `dm_control.mjcf.from_path` 사용 확인)를
추적한 결과 Python 쪽 질량 재조정 코드는 없었고, **B1이 보고한 "raw
질량 합≈1.0" 자체가 측정 오류**였음을 발견했다(정규식이 물리량이 아닌
`<statistic meanmass="1.0">` 메타데이터까지 집어 더함). 오염을 제거한
실제 geom 질량 합은 0.001이며, NeuroMechFly 공식 문서
([neuromechfly.org](https://neuromechfly.org/tutorials/1b_advanced_model_composition/))가
"길이는 mm, 질량은 g를 기본 단위로 쓴다(힘은 자동으로 μN)"고 명시적으로
확인해준다 — 더 이상 임의 숫자가 아니라 출처가 있는 확정 단위다. 이
단위로 앞다리 세그먼트 질량 비율(Coxa 32.6% : Femur 45.3% : Tibia
14.9% : Tarsus1 3.3% : Tarsus2-5 3.9%)과 원본 위치제어 파라미터
(kp=4.5×10⁻⁸ N·m/rad, 토크한계 ±6.5×10⁻⁸ N·m)를 SI로 환산해 구현
명세 표(§8)를 확정했다. **절대 질량(%)과 실제 gear/토크는 여전히
미확정**으로 남겼다 — 원본 파리 스케일(mm)을 이 리포의 K≈365~400배
확대 척도에 제1원리 스케일링 법칙으로 억지로 늘리지 않고, KC-01a가 썼던
것과 같은 방식(무공 스윕 캘리브레이션)으로 실제 구현 시 정하도록
명시했다 — 검증되지 않은 스케일링 법칙으로 숫자를 만들지 않는다.

## 회귀·테스트·lint

`python -m pytest`/`pytest` 두 진입점 모두 **138 passed**(KC-01a 22개
무변경 + vision V1 16개 + P2 6개 + V2 7개 신규). `ruff check envs
controllers encoders train analysis demos scripts tests vision` 클린.
`envs/assets/fly_visual_body.xml`의 카메라, `envs/assets/
contact_validation_p2.xml`(신규 자산)은 물리 자유도가 아니거나 완전히
분리된 자산이라 기존 B1/KC-01a 회귀에 영향이 없음을 테스트로
재확인했다.

## 산출물 경로

- 코드: `vision/*.py`(`kalman_tracker.py` 포함), `scripts/
  vm01_vision_{baseline,diagnostics,v2_tracking}.py`, `scripts/
  p{1,2}_contact_{isolated,diagnosis}.py`, `envs/assets/
  contact_validation_p{1,2}.xml`, `tests/test_{vision_v1,vision_v2,
  p2_contact}.py`.
- 설계: `docs/design/CONTACT-VALIDATION-P1-SPEC.md`,
  `docs/design/VM01-B1-MINIMAL-BODY.md`(B1+B2 통합).
- 원자료(작은 결과표, git 추적): `docs/records/evidence/VM01-vision-
  {baseline,diagnostics}.json`, `docs/records/evidence/VM01-P{1,2}-
  contact-{isolated,diagnosis}.json`, `docs/records/evidence/
  VM01-V2-tracking-comparison.json`.
- 큰 영상/프레임(gitignored, `runs/`): `runs/vm01-vision/<candidate>/
  frame_*.png`(사후 눈으로 확인할 소수 샘플, 전체 녹화 아님).
- B1/KC-01a 기존 output/profile과 물리적으로 분리된 새 경로만 썼다
  (작업 지시 2항 유지, "기존 환경은 보존").

## 다음 단계 (사용자 승인 필요, 이번에 시작하지 않음)

1. P2가 재료 자체의 특성(반발계수 ~0.29, 침투 ~0.05m, 기하·각도
   무관)으로 좁힌 문제를, 새 진단 profile에서 solref/solimp 후보 비교로
   더 진단 — 비거리 기준 선택은 여전히 금지. 학습 개시는 계속 보류.
2. B2가 확정한 명세(§VM01-B1-MINIMAL-BODY.md §8)의 남은 미확정 항목
   (절대 질량 %, 관절 하드 리밋 여부, gear/토크 캘리브레이션, 도구
   길이, 몸통 지지 방식)을 정한 뒤 실제 구현.
3. B1/B2 구현 후 무공 관절 구동 검증 → 시각·접촉 통합 검증 → 그 다음에야
   "크고 느린 공"부터 시각→행동 정책 학습을 시작한다(이번에도 RL 훈련도
   전신 균형 제어도 시작하지 않았다 — 작업 지시 4항).
4. V2의 칼만 예측이 정상 구간에서 보인 작은 성능 저하(0.91→1.21px)의
   원인(필터 지연)을 원한다면 별도로 더 조사할 수 있다 — 이번엔 보고만
   하고 더 튜닝하지 않았다.
5. 이 문서의 마지막 절(연구 트랙 구분)에 명시한 대로, 초기 일반 정책
   학습(환경 기준선)과 실제 초파리 회로 내부 학습(EXP-001 계열)은 계속
   분리해 기록한다.

## 일반 정책 학습 vs 실제 초파리 회로 학습 (기록 구분, 사용자 지시)

`docs/tasks/VISUOMOTOR-PIVOT.md` 자체가 이미 이 구분을 규약으로 못박고
있다: "초기 일반 정책 학습은 환경 기준선이다. 실제 초파리 회로 학습
주장은 별도 연결망/가소성·입출력 매핑과 frozen/재배선/비생물학적 정책
대조를 갖춘 후에만 한다." 이번 V1/V2/P1/P2/B1/B2는 **전부 환경/관측/충돌
기반**(일반 정책 트랙에 속함)이며, `encoders/retina_encoder.py`(현재
정답 좌표를 직접 읽는 초기 스켈레톤, 이번에 수정하지 않음)나 EXP-001의
실제 MaleCNS 회로 학습과는 **독립**이다 — KC→MBON11을 시각-운동
제어기로 바로 취급하지 않는다는 지시를 그대로 지켰다. 이 구분은
`docs/records/STATUS.md`의 "두 개의 독립 트랙"(D08)과 이미 일치한다.

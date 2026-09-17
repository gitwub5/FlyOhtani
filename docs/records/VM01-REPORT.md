# VM-01 완료 보고 — V1(눈 영상·추적), P1(독립 충돌 검증), B1(최소 몸체 설계)

2026-09-17 · 기준: `docs/tasks/VISUOMOTOR-PIVOT.md` · 세 작업은 서로 독립
결과이며 하나로 뭉뚱그리지 않는다(작업 지시 4항).

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

## 회귀·테스트·lint

`python -m pytest`/`pytest` 두 진입점 모두 **125 passed**(KC-01a 22개
무변경 + 새 vision 16개). `ruff check envs controllers encoders train
analysis demos scripts tests vision` 클린. `envs/assets/
fly_visual_body.xml`에 카메라 element를 추가한 것은 물리 자유도가 아니라
순수 렌더 부착물이라 기존 B1/KC-01a 회귀에 영향이 없음을 테스트로
재확인했다(125개 그대로 통과).

## 산출물 경로

- 코드: `vision/*.py`, `scripts/vm01_vision_{baseline,diagnostics}.py`,
  `scripts/p1_contact_isolated.py`, `envs/assets/contact_validation_p1.xml`,
  `tests/test_vision_v1.py`.
- 설계: `docs/design/CONTACT-VALIDATION-P1-SPEC.md`,
  `docs/design/VM01-B1-MINIMAL-BODY.md`.
- 원자료(작은 결과표, git 추적): `docs/records/evidence/VM01-vision-
  {baseline,diagnostics}.json`, `docs/records/evidence/
  VM01-P1-contact-isolated.json`.
- 큰 영상/프레임(gitignored, `runs/`): `runs/vm01-vision/<candidate>/
  frame_*.png`(사후 눈으로 확인할 소수 샘플, 전체 녹화 아님).
- B1/KC-01a 기존 output/profile과 물리적으로 분리된 새 경로만 썼다
  (작업 지시 2항).

## 다음 단계 (사용자 승인 필요, 이번에 시작하지 않음)

1. P1 실패 원인 진단(충돌각 스윕) 후 최소 수정안 적용 여부 결정 —
   그 전까지 학습 개시 보류.
2. B1 설계의 미해결 항목(§VM01-B1-MINIMAL-BODY.md §8: 질량/단위 규약,
   자연 관절범위 통계화) 해결 후 실제 구현.
3. B1 구현 후 무공 관절 구동 검증 → 시각·접촉 통합 검증 → 그 다음에야
   "크고 느린 공"부터 시각→행동 정책 학습을 시작한다(이번엔 RL 훈련도
   전신 균형 제어도 시작하지 않았다 — 작업 지시 4항).
4. 이 문서의 마지막 절(연구 트랙 구분)에 명시한 대로, 초기 일반 정책
   학습(환경 기준선)과 실제 초파리 회로 내부 학습(EXP-001 계열)은 계속
   분리해 기록한다.

## 일반 정책 학습 vs 실제 초파리 회로 학습 (기록 구분, 사용자 지시)

`docs/tasks/VISUOMOTOR-PIVOT.md` 자체가 이미 이 구분을 규약으로 못박고
있다: "초기 일반 정책 학습은 환경 기준선이다. 실제 초파리 회로 학습
주장은 별도 연결망/가소성·입출력 매핑과 frozen/재배선/비생물학적 정책
대조를 갖춘 후에만 한다." 이번 V1/P1/B1은 **전부 환경/관측/충돌
기반**(일반 정책 트랙에 속함)이며, `encoders/retina_encoder.py`(현재
정답 좌표를 직접 읽는 초기 스켈레톤, 이번에 수정하지 않음)나 EXP-001의
실제 MaleCNS 회로 학습과는 **독립**이다 — KC→MBON11을 시각-운동
제어기로 바로 취급하지 않는다는 지시를 그대로 지켰다. 이 구분은
`docs/records/STATUS.md`의 "두 개의 독립 트랙"(D08)과 이미 일치한다.

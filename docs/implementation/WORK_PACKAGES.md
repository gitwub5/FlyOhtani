# 구현 작업표 — Claude 인계

2026-09-16 · 계획/검토는 Codex, 구현/테스트/본 실험은 사용자와 Claude. 기존 작업 ID를 유지한다. 현재 실적은 [STATUS](../records/STATUS.md), 최신 코드 검토는 [REVIEW](../records/REVIEW_2026-09-16.md).

## 현재 순서

**물리 문제: I-03b 우선. 신경 연구: I-02 → I-04 → I-05. 시각화: I-04의 실제 데이터 후 I-06a, I-05 기록 후 I-06b.** 두 경로는 독립이며 신경 조건화에 물리환경이 필요 없다.

| ID | 내용 | 현황 |
| --- | --- | --- |
| I-01 | 환경·lock·패키징 | Claude 완료 기록 있음 |
| I-02 | 설정·기록·상태 계약 | 미구현 |
| I-03 | 최초 물리 오류 수정 | 일부 수정/8테스트 통과; 전체 수용 기준은 미완료 |
| I-03b | 초기 겹침·구동·기하·사건 순서 보완 | Claude 완료(2026-09-16): ENV-001 정비 기준 + T10, 시험 시드 baseline 통과. `docs/records/VALIDATION_LOG.md` 참고 |
| I-04 | 실제 데이터·LIF·가소성 | 미구현 |
| I-05 | EXP-001 | 수치 규약1.0 완료, 실행 전 |
| I-06a/b | 연결 구조/스파이크·기억 시각화 | 새 명세, 구현 전 |
| I-07a/b/c | 야구장 B0 / 코스·속도 / 변화구·선구안 | I-07a Claude 완료(2026-09-16): B0 구장·고정직구·구동재보정·baseline·영상. b/c 구현 전 |

## I-01 환경

기존 `.venv`와 `requirements-lock.txt`를 활용한다. 설치를 다시 성공했다고 보고하지 않고 실제 lock과 runtime을 확인한다. NumPy/PyArrow/PyYAML/Matplotlib/pytest가 신경 경로의 필요 패키지이며 PyArrow 등 미설치 의존성을 추가할 때 버전을 검증해 lock에 반영한다. 신경 실행이 MuJoCo/torch/Brian2에 불필요하게 의존하지 않게 패키지 extras를 분리한다. 명시적 setuptools 패키지 목록에 새 모듈을 포함한다. 변경 시 wheel 검사를 갱신한다.

## I-02 설정·기록

[구조 계약](../design/ARCHITECTURE.md)과 [설정](../../configs/README.md)을 구현한다. legacy default.yaml을 EXP-001 기본값으로 쓰지 않는다. deterministic seed streams, fast/slow/trace reset, 독립 probe, 중단/재개, 해시·manifest·사건/trial 기록을 구현한다. T02/T07 통과와 연속/재개 동일성 증거가 완료 조건이다.

## I-03b 물리 보완

[ENV-001](../design/ENV-001-interception.md)을 순서대로 적용한다.

1. reset 관통과 연결부 자기충돌 처리. 기존 +1.1rad 자세의 의도를 근거로 관통을 유지하지 않는다.
2. zero_torque/held_pose/actuated를 분리해 구동력을 재측정. gear 후보 절차 적용.
3. 외곽 목표·낮은 포물선·유효 준비각을 설정화. controller와 종료 경계 공유.
4. substep 최초 terminal·동시 사건 우선순위·terminated/truncated·nominal timing·시간적분 비용 보완.
5. 새 결정적 테스트와 고정된 개발/시험 baseline 비교. q(t)/공 궤적/최초 contact를 저장.

현재8테스트 재사용에 T10을 추가한다. 기준 미달 시 원자료와 원인을 기록한다. ‘11개 시작각에서 hit’는 정지각의 전수검증이 아니므로 과거 주석·기록도 최신 진단으로 연결한다. 과거 측정값 자체를 지우지는 않는다. **완료: ENV-001 모든 정비 기준 + T10**. 제어·신경 학습 성과로 보고하지 않는다.

**완료 (2026-09-16, Claude):** 1~5 모두 구현. 22개 테스트(`tests/test_fly_batter_env.py`)로 T10 포함 VALIDATION.md의 물리 회귀 8항목을 커버. gear=0.08로 재보정(`docs/design/ENV-001-calibration.json`). 시험 시드(1000-1099, n=100)에서 zero_torque=0%, held_rest=0%, scripted=100%, scripted-random=100pp로 ENV-001 첫 정비 통과 기준 충족. 상세는 `docs/records/VALIDATION_LOG.md`, 남은 문제는 같은 문서 하단 참고(자유낙하 dt=2ms 오차 일부 seed 초과, best_constant_angle의 고정목표 한계 재확인, held_rest 근사 구현). 제어·신경 학습 성과로 보고하지 않는다 — 이 결과는 환경 정합성 검증이다.

## I-04 실제 회로와 신경 모델

[DATA_MODEL](../design/DATA_MODEL.md)의 snapshot·필터·수식이 구현 기준이다. 공식 두 파일 취득/해시/schema/ID검증 → 파생 회로 → sparse KC spike 입력 → MBON LIF → 효능 갱신 순서로 구현한다. fixture와 실제 데이터를 구분한다. 최초 실제 데이터 schema 차이는 근거 있는 adapter로 처리하고 결과 manifest에 기록한다.

**완료: T03~07, 실제 C/P/a와 ID를 역추적 가능.** 원 논문 MATLAB 재현은 현재 EXP-001의 선행 조건이 아니며 별도 S2다. 실제 회로 선택을 했다는 이유로 추가한 동역학·가소성이 검증된 생물학이라는 설명을 붙이지 않는다.

## I-05 조건화와 독립 평가

[EXP-001 1.0](../experiments/EXP-001-associative-learning.md)의 시드·일정·비교군·점수·판정을 그대로 구현한다. 파일럿/본 평가를 구분하고 수치 유효성/예산 확인 후 진행한다. 한 seed만 예쁘게 보이는 그림을 전체 결과로 대신하지 않는다.

**완료:** T08, 모든 조건·분기·시드 원자료와 재분석 일치, 긍정/음성/무효 판정 및 한계. 역전 진단의 실패를 숨기지 않는다. 생물학적 주장은 최소 범위로 제한한다.

## I-06 시각화

[VIZ-001](../design/VISUALIZATION.md) 적용. I-06a=실제 ID/접점 수/모델효능을 구분한 회로도. I-06b=주입 KC/생성 MBON raster·막전압·조절 신호·학습 전후/개입 비교. 먼저 재현 가능한 정적 SVG/PNG/PDF, 이후 읽기 전용 HTML 재생. 3D 해부학은 실제 좌표·등록 자료 확보 후 별도 단계다.

**완료:** T09 및 VIZ 산출물. 보기만 해도 부분회로/외부입력/가정한 모델임을 알 수 있어야 한다.

## I-07 야구장과 다양한 투구

[ENV-002](../design/ENV-002-baseball.md)를 따른다. I-03b의 초기충돌·구동·사건 순서 기반을 재사용한다. 기존 짧은 거리 수치 과제는 회귀용이며 새 야구장 스케일과 혼합하지 않는다. I-07a는 구장/릴리스/타자 박스/확대한 파리/고정 직구, I-07b는 조준 도달성 후 코스·속도, I-07c는 공기력 검증 후 변화구·선구안이다. 시각화·정답 로그가 정책에 미래 정보를 전달하지 않는지도 검증한다. 각 단계의 완료 조건은 ENV-002를 따른다.

**I-07a 완료 (2026-09-16, Claude):** `envs/baseball_env.py`(`BaseballB0Env`) + `envs/assets/baseball_park.xml`. 구장 배치(ENV-002 §1 좌표계, 투수판/플레이트/우타자 박스/파울라인), 릴리스 마커-spawn 일치, 고정 직구, 배트 gear 재보정(12, ENV-001 값 재사용 안 함), held_rest substep 정확화, physics_dt 후보 수렴 검사, zero_torque/held_rest/random/scripted baseline(ENV-002 §8 smoke 기준 충족: held/zero 접촉0%, scripted 100%), 4카메라 영상(`runs/env002-b0-demo/video/`). 부수적으로 I-03b의 "양자화 잔차" 설명이 실은 공 자유관절의 누락된 armature 오버라이드 때문이었음을 발견해 ENV-001/ENV-002 양쪽 다 수정했다(`docs/records/VALIDATION_LOG.md` 참고). 테스트 35개(신규13+기존22) 통과. B1(코스·속도)/B2/B3(공기력·변화구)/RL 훈련은 범위 밖(사용자 지시). 상세: `docs/records/VALIDATION_LOG.md`.

## 인계 결과 형식

작업 ID, 변경 이유·파일, 소스/환경/data hash, 정확한 명령, pass/fail/skip 수, 실제 산출물 경로, 기준별 충족 여부, 미검증 항목, 다음 작업. 상태와 검증 기록을 갱신한다. 실험 설계가 바뀌면 PLAN과 규약 버전도 함께 갱신한다.

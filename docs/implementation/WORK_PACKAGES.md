# 구현 작업표 — Claude 인계

2026-09-16 갱신(R-01 문서 정리, `docs/implementation/REFACTOR-PLAN.md`). 완료된
작업의 상세 인계문은 제거하고 [완료 작업 색인](../records/INDEX.md) 링크로
대체했다. **미착수/진행중 작업만 아래에 상세 설명이 있다.** 계획/검토는 Codex,
구현/테스트/본 실험은 사용자와 Claude. 현재 실적은
[STATUS](../records/STATUS.md), 다음 작업 배정은 사용자가 명시적으로 지정한다
(독립적인 두 트랙 중 무엇을 먼저 할지는 자동으로 정하지 않는다).

## 현재 배정 (2026-09-17)

[KC-01a 검증 보완 + VISION-01 설계](../tasks/KC-01a-VALIDATION-AND-VISION.md)의
A절(dt 수렴/정착/에너지/타이밍 검증)과 B절(VISION-01 설계), 후속 원인 분리
(발산 원인을 구동/접촉으로 분리, 관절한계 타이밍·구속종류/적분오차 구분),
[회전 방향 계약](../design/KC-01a-DIRECTION-CONTRACT.md)과
`same_direction_staggered`의 수용 검증·몸통 선행 메커니즘 검증(A9-A14,
motion-triggered handoff 모드 추가)까지 완료했다
([검증 결과](../records/KC-01a-VALIDATION.md), [VISION-01](../design/VISION-01.md)).
`staggered_swing_and_torso`의 이전 "최고 성적" 결론은 철회됐다.
`torso_lead_handoff`(torso_target=0.5)가 dt 수렴·양 축 정착·그립 도달성을
모두 통과하며 production dt 6.78m을 냈지만, torso 정착이 관절한계 하드
스톱에 의존해 "협응 우위"나 "시각 기준선 확정"으로는 아직 쓰지 않는다.
다음 배정은 사용자가 명시적으로 지정한다 — `torso_lead_handoff`의 구동/
접촉 분리 재검증, 그 정착 방식의 최소 수정안, `torso_swing_with_arm_hold`의
gear 재보정, 공통 에너지 예산 비교, VISION-01 구현 여부 결정 중 무엇을
먼저 할지 자동으로 정하지 않는다.

## 상태 표

| ID | 내용 | 상태 |
| --- | --- | --- |
| I-01 | 실행환경·lock·패키징 | 완료 |
| I-02 | 설정·기록·상태 계약 | **미착수** |
| I-03 | ENV-001 최초 물리 오류 수정 | 완료(이후 I-03b가 재정정) |
| I-03b | ENV-001 초기 겹침·구동·기하·사건 순서 보완 | 완료 |
| I-04 | 실제 회로·LIF·가소성 구현 | **미착수** (이전 작업표가 "완료: T03~07"로 잘못 표시했던 항목 — 실제 코드/테스트 없음, 문서 정리 중 정정) |
| I-05 | EXP-001 실행 | 규약 1.0 확정, **실행은 미착수** (이전 작업표가 "완료: T08"로 잘못 표시했던 항목) |
| I-06a/b | 연결 구조/스파이크·기억 시각화 | **미착수** (이전 작업표가 "완료: T09"로 잘못 표시했던 항목) |
| I-07a | ENV-002 B0(야구장·고정 직구) | 완료 |
| I-07a-1 | B0 수용 검토(접촉 수렴·보상·구장 대조) | 완료 |
| I-07b | B1 조준·9코스 구현 | 완료(이후 I-07b-fix가 성공 판정을 재정의) |
| I-07b-fix | 스윙 방향·타구 판정 수정 | 완료 — **mid_mid만** |
| I-07b-followthrough | 팔로우스루 안정화·접촉 재료 정정 | 완료 |
| I-07b(잔여) | 구속(속도) 변화, 나머지 8코스 재보정 | **미착수** |
| I-07c | 공기력·변화구·선구안(B3/B4) | **미착수** |
| I-08a | NeuroMechFly 시각 모델 도입 | 완료(이후 I-08a-fix가 좌표 버그 정정) |
| I-08a-fix | 외형 좌표 버그 수정·자세 재정의 | 완료 |
| I-08a-style + I-07c-score/swing | 옆선 자세·색상, 거리 점수, 스윙 개선 | 완료 — **mid_mid만** |
| I-08b | 실제 전신 역학 통합 | **미착수** |
| KC-01a | 몸통-배트 협응 최소 역학 모델 | 시제품 구현 완료. dt 수렴 검증 완료 — 4개 조건 중 1개만 통과(그마저 유효 타구 실패), 나머지 우위 비교는 무효로 철회 |
| KC-01a-validation | dt 수렴·정착·에너지·타이밍 보완 + VISION-01 설계 | 완료 — [검증 결과](../records/KC-01a-VALIDATION.md), [VISION-01](../design/VISION-01.md) |
| KC-01a-direction-contract | 회전 방향 계약 + 동방향(same-direction) 조건 설계 + motion-triggered handoff | 완료 — [계약](../design/KC-01a-DIRECTION-CONTRACT.md), 역회전(상쇄) 발견, `same_direction_staggered`는 정착 미충족으로 기준선 보류, `torso_lead_handoff`(torso_target=0.5)가 dt/정착/그립 모두 통과(6.78m, 협응 우위 미결론) |
| KC-01b | 뒷다리 지지·실제 전신 전달 | **미착수** |

완료 항목의 근거·수치·시행착오는 [완료 작업 색인](../records/INDEX.md)에서
작업 ID로 찾는다.

## I-02 설정·기록 (미착수)

[구조 계약](../design/ARCHITECTURE.md)과 [설정](../../configs/README.md)을
구현한다. legacy `docs/archive/configs-default.yaml`(구 `configs/default.yaml`, R-04에서 archive로 이동)을 EXP-001 기본값으로 쓰지 않는다.
deterministic seed streams, fast/slow/trace reset, 독립 probe, 중단/재개,
해시·manifest·사건/trial 기록을 구현한다. T02/T07 통과와 연속/재개 동일성
증거가 완료 조건이다.

## I-04 실제 회로와 신경 모델 (미착수)

[DATA_MODEL](../design/DATA_MODEL.md)의 snapshot·필터·수식이 구현 기준이다.
공식 두 파일 취득/해시/schema/ID검증 → 파생 회로 → sparse KC spike 입력 →
MBON LIF → 효능 갱신 순서로 구현한다. fixture와 실제 데이터를 구분한다. 최초
실제 데이터 schema 차이는 근거 있는 adapter로 처리하고 결과 manifest에
기록한다. 완료 조건: T03~07, 실제 C/P/a와 ID를 역추적 가능. 원 논문 MATLAB
재현은 현재 EXP-001의 선행 조건이 아니며 별도 S2다.

## I-05 조건화와 독립 평가 (규약 확정, 실행 미착수)

[EXP-001 1.0](../experiments/EXP-001-associative-learning.md)의 시드·일정·
비교군·점수·판정을 그대로 구현한다. 파일럿/본 평가를 구분하고 수치 유효성/예산
확인 후 진행한다. 한 seed만 예쁘게 보이는 그림을 전체 결과로 대신하지 않는다.
완료 조건: T08, 모든 조건·분기·시드 원자료와 재분석 일치, 긍정/음성/무효 판정
및 한계. 역전 진단의 실패를 숨기지 않는다.

## I-06 시각화 (미착수)

[VIZ-001](../design/VISUALIZATION.md) 적용. I-06a=실제 ID/접점 수/모델효능을
구분한 회로도. I-06b=주입 KC/생성 MBON raster·막전압·조절 신호·학습 전후/개입
비교. 먼저 재현 가능한 정적 SVG/PNG/PDF, 이후 읽기 전용 HTML 재생. 완료 조건:
T09 및 VIZ 산출물. 보기만 해도 부분회로/외부입력/가정한 모델임을 알 수 있어야
한다.

## I-07(잔여) 야구장 나머지 코스·구속 변화 (미착수)

[BASEBALL-SPEC](../design/BASEBALL-SPEC.md)을 따른다. mid_mid 외 8코스는
I-07b-fix 이전(접촉-only, 역방향 스윙) 값이 남아 있어 재보정이 필요하다.
구속(속도) 변화(B2)는 아직 설계만 있고 구현 전이다. 타이밍 ±5ms 취약성 개선을
먼저 별도 실험으로 다루는 순서를 사용자가 지정했다(`docs/records/STATUS.md`
"알려진 한계").

## I-07c 공기력·변화구·선구안 (미착수)

[BASEBALL-SPEC](../design/BASEBALL-SPEC.md) §13 로드맵의 B3/B4. 중력+공기저항+
스핀(Magnus) 모델, 계수는 문헌 검토 후 별도 AIR-001 규약으로 고정한다.

## I-08b 실제 전신 역학 통합 (미착수)

NeuroMechFly의 관절/질량/접촉/감각을 그대로 쓰는 통합은 별도 embodied
환경이다. 원 스케일에서 보행·자세·감각 baseline부터 재현하고 신경회로-운동
제어 매핑을 설계한다. 확대 시 관성/힘/시간을 재검토해야 하며 mm 모델을 사람
크기로 키우고 질량만 유지하지 않는다.

## KC-01b 뒷다리 지지·실제 전신 전달 (미착수)

`docs/research/BATTING-KINETIC-CHAIN.md`가 KC-01a 다음 단계로 제안한 항목.
몸통의 world 고정을 해제하고 뒷다리 2개의 관절과 유한 면적 발 접촉으로
지지한다. 다리 힘→몸통→앞다리/배트 전달을 구현하고, 두 앞다리를 실제 부하
전달 관절 사슬로 바꿔 배트와의 폐루프 구속/그립 힘을 설계한다. 먼저 직립
균형→무공 체중 이동/몸통 회전→무공 스윙→저속 공→현재 중앙 직구 순서로
검증한다(정상 지지 검증 전 고속 타격부터 튜닝하지 않음). KC-01a에서 발견된
"비참여 축도 반작용 억제에 실제 토크를 쓴다"·"정착 판정에 착지 후 관찰
창이 더 필요하다"는 점을 설계에 반영한다(`docs/records/KC-01a-COMPARISON.md`).

## 인계 결과 형식

작업 ID, 변경 이유·파일, 소스/환경/data hash, 정확한 명령, pass/fail/skip 수,
실제 산출물 경로, 기준별 충족 여부, 미검증 항목, 다음 작업. STATUS와
`docs/records/validation/`에 새 파일을 추가하고 이 문서·VALIDATION_LOG 색인·
records/INDEX를 갱신한다. 실험 설계가 바뀌면 PLAN과 규약 버전도 함께 갱신한다.

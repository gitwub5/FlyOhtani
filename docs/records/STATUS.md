# 현재 상태

2026-09-17 갱신(KC-01a 몸통-배트 협응 모델). 이 문서는
**지금** 무엇이 검증됐고 무엇이 막혀 있는지만 담는다. 시행착오·정정 경위·과거
수치는 [상태 이력](STATUS_HISTORY.md)에, 실행 명령·원자료는
[검증 기록 색인](VALIDATION_LOG.md)에 있다. 다음 작업 배정은
[구현 작업표](../implementation/WORK_PACKAGES.md)를 따른다.

## 두 개의 독립 트랙

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
  포함하자 대부분(잔차 0.5~4.2%, 단 `simultaneous`는 5.7~10.8%로 원인 미상)
  설명됐다. 시각 정책 통합(`docs/design/VISION-01.md`, 설계만 완료)은 이
  결과를 근거로 보류한다.

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
  정밀 dt에서 무효로 뒤집힌다. 원인은 접촉의 이산화 민감도로 추정되며 재료/gear를
  바꾸지 않고 진단만 했다(`docs/records/KC-01a-VALIDATION.md`).

## 테스트·린트

`python -m pytest`/`pytest` 두 진입점 모두 **99 passed**로 일치(B1/B0/ENV-001은
87개로 무변경, KC-01a 12개 추가). lint 클린. 비editable wheel 설치로 모델 로드까지
확인(`docs/records/evidence/R03-wheel-install-check.txt`).

## 다음 작업

[KC-01a 검증 보완과 시각 입력 설계](../tasks/KC-01a-VALIDATION-AND-VISION.md)의
A절(물리 검증)과 B절(VISION-01 설계)은 완료했다. 남은 것: (1) dt 미수렴 3개
조건의 원인을 더 분해하고 최소 수정안을 사용자 승인 후 진행, (2) A2 수렴 후
공통 에너지 예산 비교 재개, (3) VISION-01의 실제 구현 여부는 물리가 수렴한
뒤 결정. [구현 작업표](../implementation/WORK_PACKAGES.md)에서 다음 배정을
받는다. KC-01b/8코스/RL/시각 제어 구현은 사용자가 명시적으로 지정하기 전에는
시작하지 않는다.

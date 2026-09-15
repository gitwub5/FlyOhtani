# 검증 명세

2026-09-16 · 구현자가 수행할 기준. 실제 완료 증거는 [검증 기록](../records/VALIDATION_LOG.md)에만 기록한다.

## 검증 계층

| ID | 대상 | 확인과 통과 기준 |
| --- | --- | --- |
| T01 | 설치·배포 | Python/OS/lock 기록, wheel에 새 패키지와 XML 포함, 신경 실험은 MuJoCo import 없이 실행 |
| T02 | 설정 | 필수 항목/단위/알 수 없는 키/지원하지 않는 dt 거부. 적용 설정 저장 후 같은 설정 재실행 |
| T03 | loader | 작은 fixture로 필터/중복합산/ID정렬/타입오류 확인. 실제 데이터 별도 실행으로 원본-파생 C 합·행 검산 |
| T04 | LIF | 일정 전류 I=2, 초기0에서 첫 역치 도달이 tau_m·ln2의 올림 tick과 일치; 불응기2tick, 무입력 누설의 해석값과 오차≤1e-12 |
| T05 | 전달·가소성 | 단일 spike 지연1tick 확인. d=0 효능 불변. 고정 e,d 입력에서 a의 지수 감소를 독립 해석값과 비교(오차≤1e-12); 하한 보존; 비대상 연결 불변 |
| T06 | 수치 분해능 | 개발3seed의 저장된1ms 입력 spike 시각을0.5ms 격자에 그대로 재생. delay1ms/불응2ms는 물리시간 유지. W0/W1의 집단 평균 rate 차이≤max(1Hz,기준의5%), S 차이≤0.05. 실패 시 본 평가 보류·dt 재설계 |
| T07 | 상태 | 같은 입력/상태에서 연속 실행과 중간 checkpoint 재개가 상태·spike까지 동일. probe 실행 순서를 바꿔도 동일. 평가 중 a/P/readout 불변 |
| T08 | 실험 | CS별노출/조절량/paired입력 동일성, 평가에 d=0, 시드/분기누락 거부; EXP-001 판정 독립 재계산 |
| T09 | 시각화 | spike 수·표시 연결·ID·bin 집계가 원자료와 일치, injected/simulated 분리, viewer 전후 run 불변 |
| T10 | 물리 | ENV-001의 초기충돌/구동/시간순서/기준성능 검증 |

T04는 입력 필터를 우회해 LIF 적분 kernel을 검사한다. T05도 고정 e를 주는 plasticity kernel과 동적 e 통합검사를 구분한다. 구현 함수 자체를 그대로 복사한 기대값 테스트는 피한다. T06의 Bernoulli 입력을 dt별로 다시 뽑지 않는다.

## 물리 회귀의 필수 추가 항목

- 모든 reset 후보·관절 범위에서 금지한 초기 관통 검사. 지면 clearance와 의도한 연결부 collision exclude 확인.
- ball 접촉 없이 actuator 최대입력과 zero torque q(t)를 비교. held_pose는 별도 진단.
- frame_skip=5의 중간 substep에서만 끝나는 접촉을 검출. ground 후 limb를 hit로 처리하지 않음. 동일 substep은 ENV-001 우선순위 적용.
- 지나감은 terminated, timeout은 truncated; terminal 뒤 step 오류. terminal 이후 추가 물리 적분·중복 보상 없음.
- 정상 hit에서 nominal timing값이 존재하고 `hit_time−planned_arrival`과 일치. 인위적으로 공을 순간이동시킨 테스트만으로 대체하지 않음.
- 비용은 같은 action 시간적분에서 control_dt5/10/20ms가 같은 값(절대오차1e-9 이내). 초기 자유낙하 목표 오차는 dt2ms→1ms 감소 시 악화하지 않으며 목표 오차≤0.01m. 충돌과 분리해 측정.
- 한 joint축의 알려진 접촉점 속도는 ω×r 해석값과 각 성분 오차≤1e-8 m/s. 충돌 직전/이후 의미를 혼동하지 않음.
- baseline은 개발/시험 시드를 분리하고 한 controller의 RNG 사용량이 다른 controller 환경 입력을 바꾸지 않음.

## 실행 절차

1. 작은 결정적 unit/통합 테스트 → 실제 회로 추출 검증 → 개발 pilot → 규약 고정 → 본 평가 → 저장 자료 재분석.
2. 설치·테스트·추출·pilot·본실행마다 정확한 명령/버전/소스 해시/시각/exit code/결과경로 기록.
3. synthetic fixture의 통과와 실제 데이터 실험을 분리한다. 테스트 통과를 학습 성공으로 보고하지 않는다.
4. 실패 시 마지막 상태·원자료를 보존하고 invalid/interrupted/negative를 구분한다. 임의 seed 교체, fixture 실패 skip, 설정 fallback으로 성공 처리하지 않는다.
5. 본 평가 이후 파라미터 조정은 탐색 연구로 분류한다. 새 버전·새 holdout이 필요하다.

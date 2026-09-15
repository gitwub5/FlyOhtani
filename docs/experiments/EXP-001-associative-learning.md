# EXP-001 — 연합 반응과 가중치 기억의 최소 검증

규약1.0 · 2026-09-16 · 구현 전 실행 명세. 0.2 초안을 대체한다. 수치는 공학적 기본값이며 생물학적 측정값이 아니다. [데이터·모델](../design/DATA_MODEL.md)의 회로와 tick 수식을 그대로 사용한다.

## 질문과 해석 범위

MaleCNS KC→MBON11 연결에서 국소 효능 감소가 자극별 반응 차이를 저장하는가? 외부 readout은 고정한다. 입력 KC 활동과 도파민 신호를 외부에서 주입하므로 전체 감각/도파민 회로의 자율 학습이나 행동 선호를 입증하지 않는다. 점수 이름은 ‘연합 반응 대비’다.

## 입력·시드·반복

- 개발 시드0,1,2; 본 평가100~129(30개). seed가 독립 반복 단위이며 trial은 반복 측정이다.
- I의 정렬된 KC ID를 seed별 순열로 섞고 K=max(1,floor(0.1N))개를 A, 다음K개를 B에 배정한다. 겹침0. 배열을 저장한다. 본 평가30개 중 짝수 seed는 A가 CS+, 홀수는 B가 CS+다.
- 자극 동안 해당 KC만 rate20Hz. tick별 Bernoulli 확률 `1−exp(−20dt)`; 나머지 KC는0. 이를 이산 spike 입력이라고 표기한다.
- NumPy PCG64, SeedSequence([seed, stream_code, trial_index]) 사용. stream 1=입력집합, 2=훈련입력, 3=평가입력, 4=unpaired 배정, 5=역전입력. 각 trial은 ID 정렬 순서·시간 순서로 추출하며 상태/seed를 보존한다. condition별 RNG를 따로 뽑지 않는다.
- 훈련 A/B 노출·spike realization은 paired/frozen/unpaired 사이에 같다. 평가 입력은 학습과 독립이고 W0/W1/기억 개입/비교군에서 동일하게 재사용한다.

## 일정

trial 길이2s. [0,1)s에 자극, [1,2)s에 무입력. 각 trial 시작 때 v/x/e/불응기/지연 큐를0으로 하고 a는 유지한다. 따라서 trial 간 신경 잔류 상태는 학습 저장 수단이 아니다.

1. a0=1 저장. 평가 A/B 각각10trial, 교대로 A0,B0,...,A9,B9. d=0, learning=false. 측정창은 자극 시작 기준[0.1,1.0)s. 모든 선택 MBON의 총 spike/(MBON 수·0.9s)를 trial Hz/neuron으로 기록한다.
2. 초기 a0에서 훈련20쌍=40trial. 각 쌍은 A 다음 B; CS+ 정체는 seed별 반전. paired의 CS+ trial만 d=1을[0.5,1.0)s에 준다. d는 나머지0.
3. a1과 전체 상태 저장. 각 probe는 그 checkpoint에서 독립 분기한다. 평가마다 fast/trace 초기화, d=0, learning=false.
4. a1의 즉시 reset probe, 10s 무입력 대기 후 reset probe, a0 복원 probe, 새 모델에 a1 이식 probe를 수행한다. 대기 중에도 learning=false. 평가 입력은1단계와 동일.

모든 시간 경계는 dt의 정수배. tick spike 시각은 모델 명세대로 t+dt이며 위 반열린 측정창으로 집계한다. 입력 끝 경계의 출력 포함 여부를 구현마다 바꾸지 않는다.

## 필수 비교군

| condition | 훈련 조절 | 가소성 |
| --- | --- | --- |
| paired | CS+의20trial에0.5s pulse | 켬 |
| frozen | paired와 동일 | 끔 |
| unpaired | A20회 중10회, B20회 중10회를 stream4로 균등 무복원 선택하여 같은 pulse | 켬 |
| modulation_only | paired와 같은 pulse이나 훈련 KC 입력 없음 | 켬 |

네 조건 모두 초기 a0와 평가 입력이 같다. modulation_only는 비특이적 변화 확인용이며 노출량을 맞춘 주 비교군은 아니다. 주 추론은 paired−frozen 및 paired−unpaired다. 재배선과 학습 readout 비교는 다음 실험으로 분리한다. 현재 실험으로 실제 배선의 우월성을 주장하지 않는다.

## 점수와 사전 판정

시드별 W0의 평균 반응을 r0A/r0B, 각 branch 반응을 rA/rB라 한다. `B0=(r0A+r0B)/2`, `S=(rCS−−rCS+)/B0`, `Δ=S_after−S_before`. B0는 모든 조건·분기에 같은 W0 기준이며 각 결과에서 재정규화하지 않는다. Hz 원자료도 함께 보존한다.

- 유효성: W0의 각 자극 평균이 각각1~250Hz/neuron, 모든 상태 finite, 비허용 연결·P/readout 불변, 평가 전후 a byte-identical. 벗어나면 해당 seed는 `model_invalid`; 점수를0으로 채우지 않는다.
- 모든30seed 유효해야 확증 판정을 한다. 무효가 있으면 전체는 `inconclusive`, 유효 subset 기술통계와 무효 원인을 함께 보고한다. 불리한 유효 seed를 제외하지 않는다.
- E1=Δpaired−Δfrozen, E2=Δpaired−Δunpaired. 각각 평균≥0.20, paired seed bootstrap95% percentile 구간 하한>0이면 연합 효과 기준 충족. bootstrap은 seed 인덱스30개를 복원추출,10000회, PCG64 seed20260916. 두 비교가 모두 만족해야 하므로 하나만 골라 성공 선언하지 않는다.
- 기억 구현 검증: a0 복원은 W0와, a1 이식과10s 대기 probe는 a1 reset probe와 spike count/score가 정확히 같아야 한다(같은 backend·입력). 다르면 기억 실패라는 과학 결론 이전에 구현 오류로 분류한다.
- frozen/modulation_only의 a는 a0와 정확히 같아야 한다. frozen Δ는 동일 평가 입력에서0이어야 한다.

판정: `supported`(유효성·두 주효과·개입 검증 충족), `not_supported`(유효하고 구현 검증 통과했으나 효과 기준 미달), `inconclusive`(데이터/수치/실행/구현 오류). 완료 여부와 결과 판정은 별도 필드다.10초 기억은 가중치에 감쇠가 없는 모델 가정 아래의 저장 검증이며 실제 장기기억 수명 근거가 아니다.

## 보상 반전: 부차 진단

paired a1에서 별도 분기해 CS+/CS−를 바꿔40쌍(80trial) 추가 훈련한다. pulse/입력 규칙은 같다. 원래 CS+ 부호로 점수를 보고하고 새 대응 부호도 병기한다. 이 모델은 감소만 가능해서 양쪽 효능이 바닥에 붙고 역전이 안 될 수 있다. 반전 성공을 필수 기준으로 삼지 않으며 결과를 학습 유연성의 한계로 보고한다. 양방향 가소성/회복을 넣으려면 새 모델·실험 버전이 필요하다.

## 실행 예산과 실패

NumPy float64 CPU, worker1. 먼저 개발3seed를 최대20분, RSS2GiB, 결과파일1GiB 내에서 수행한다. 본 평가 예상시간이2시간 또는 결과5GiB를 넘으면 본 실행 전에 `budget_exceeded` 보고서를 남긴다. 숫자를 몰래 줄이지 말고 기록량/계산 최적화 후 재예측하거나 예산 변경을 기록한다. 데이터 저장은 별도 여유공간5GiB를 확인한다. 부하·RAM 가용량은 I-01 환경 기록에서 확인한다.

본 평가 중 예산 초과/중단은 checkpoint 후 interrupted로 저장한다. 재개는 같은 소스/설정/데이터 해시에서만 허용한다. 개발 결과를 보고 수치를 바꾸면 버전을 올리고 본 평가 전에 확정한다.

## 완료 산출물

manifest, 적용설정, 입력집합/일정/spike seed, 모든 trial 원 반응, seed별 Δ/E1/E2, CI, 유효성 목록, W0/W1/각 분기 checkpoint, [시각화](../design/VISUALIZATION.md), 보고서. 보고서는 사용 데이터/가정/대조군/무효 및 음성 결과/한계를 포함한다. 다른 에이전트가 원자료만으로 점수와 판정을 다시 계산할 수 있어야 한다.

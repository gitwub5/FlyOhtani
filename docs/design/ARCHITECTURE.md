# 구조와 데이터 계약

상태: 2026-09-16 설계 기준. 아래 모듈·계약은 **신경회로 트랙**의 구현 목표이며
현재 존재하는 API가 아니다(신경회로 트랙은 아직 미착수, `docs/records/STATUS.md`).
기존 파일 경로는 필요한 작업을 수행할 때 점진적으로 정비한다.

**물리 환경 트랙(`envs/`)의 실제 현재 모듈 경계**는 이 설계와 별도로 이미
구현돼 있다: `envs/baseball_b1_env.py`가 reset/step과 substep 사건 순서를
조정하고, 독립적인 코스 기하/타이밍 설정은 `envs/baseball/courses.py`, 순수
채점/보상 계산은 `envs/baseball/reward.py`로 분리했다(R-02,
`docs/implementation/REFACTOR-PLAN.md`). 규칙 자체는 여기가 아니라
[BASEBALL-SPEC](BASEBALL-SPEC.md)에 있다 — 이 문서는 아직 신경회로 쪽
목표 구조만 다룬다.

## 1. 모듈 경계

| 모듈 | 책임 | 입력 → 출력 | 의존성 경계 |
| --- | --- | --- | --- |
| `connectomes/` | 읽기·선택·ID 매핑·출처 | 원본+선택 규칙 → 회로 명세 | 물리·학습 라이브러리에 의존하지 않음 |
| `circuits/` | 신경 동역학·전달 지연 | 회로+입력+시간 → 신경 반응 | MuJoCo 없이 실행 가능 |
| `plasticity/` | 제한된 연결의 가소성 | 신경 활동+조절 신호 → 가중치 변화 | 행동 점수로 가중치를 몰래 직접 갱신하지 않음 |
| `encoders/` | 감각 표현·노이즈·지연 | 관측/자극 → 신경 입력 | 시험 레이블·미래 보상에 접근하지 않음 |
| `controllers/` | 출력 해석과 비교 정책 | 신경 반응/동일 관측 → 행동 | 고정 readout과 학습 정책을 구분 |
| `envs/` | 물리 상태·접촉 사건 | 행동+시간 → 관측·사건 | 특정 신경 모델에 의존하지 않음 |
| `experiments/` | 자극 일정·시계·조건·평가·저장 | 적용 설정 → 실행 결과 | 전체 흐름을 조율하는 단일 책임 |
| `train/`, `demos/` | 사용자 실행 진입점 | 실행 인자 → 공통 실행기 | 과학 로직·평가 규칙 중복 금지 |
| `analysis/` | 저장한 원자료의 요약 | 실행 결과 → 표·그래프 | 분석 중 학습 상태를 변경하지 않음 |

새 모듈의 첫 구현 시 패키징 설정도 함께 반영한다. 빈 Python 클래스나 대형 프레임워크를 미리 만들 필요는 없다.

## 2. 공통 데이터

| 개념 | 필수 항목 |
| --- | --- |
| 회로 명세 | dataset/version/checksum, 원본 neuron ID→내부 index, 유형·구획, source/target, 접점 수, 부호·조절 규칙, 선택/경계 처리 |
| 신경 입력 | 시작 시각·기간·단위, 대상 ID, 입력 종류(전류/스파이크/발화율), 값, 난수 식별자 |
| 신경 반응 | 실제 진행 시간, 기록 대상, 단위, spike/event 또는 집계값, 발화 안정성 지표 |
| 보상 사건 | 발생 시각, 원인 사건 ID, 값, 조절 뉴런에 전달하는 매핑, 지연 |
| 물리 사건 | substep 시각, 물체 쌍, 최초 접촉, 접촉점 상대 선속도, 실패/종료 이유 |
| 평가 결과 | experiment ID/version, condition, seed, phase, stimulus/trial ID, 원점수·변환점수·결측 이유 |

단위를 필드 이름 또는 명세에 명시한다. 프로젝트 교환 시간은 초(s), 물리는 m/kg/N 기반으로 하고, 논문의 ms/mV 등 신경 단위는 경계에서 명시적으로 변환한다. 데이터의 큰 뉴런 ID를 부동소수점으로 변환하지 않는다.

## 3. 상태 관리

| 상태 | 내용 | 초기화 정책 |
| --- | --- | --- |
| 구조 | 뉴런·연결·ID·출처 | 실행 중 고정, 변경 시 새 모델 식별자 |
| 느린 학습 상태 | 가중치와 선택한 모델의 장기 가소성 변수 | 학습 지속/기억 제거 조건에 따라 선택 |
| 빠른 신경 상태 | 막전압·전류·불응기·진행 중인 전달 지연 | probe 조건에서 명시적으로 초기화 |
| 학습 trace | eligibility·도파민 trace 등 | probe 시작에 보존/제거 정책 명시 |
| 외부 상태 | 물리·인코더·readout 필터·난수·학습기 | checkpoint와 실험 조건에 포함 |

모델마다 변수의 빠름/느림 분류를 문서화한다. 단일 `reset()`으로 모든 상태를 암묵적으로 지우는 설계를 피한다. 가중치만 제거하는 실험은 ‘가중치 기반 기억’에 대한 주장으로 한정하고 다른 장기 변수가 있다면 별도 통제한다.

기억 probe는 저장한 학습 종료 상태에서 각각 분기한다. 유지 시험, 가중치 제거 시험, 역전학습을 같은 객체에 순서대로 누적하여 비교하지 않는다.

## 4. 실행 순서와 시계

1. 실험 규약과 적용 설정을 검증하고 실행 ID를 만든다.
2. 회로·인코더·출력 해석·난수를 초기화한다.
3. 자극과 보상 사건을 예정된 신경 시간에 전달한다.
4. 신경계를 적분하고 허용된 연결만 갱신한다.
5. 정해진 구간의 반응을 집계하고 출력 해석을 적용한다.
6. 물리 과제라면 행동을 유지하며 물리 substep과 모든 접촉 사건을 기록한다.
7. 각 phase 종료 상태·지표를 저장하고 독립 평가를 수행한다.

`neural_dt`, `physics_dt`, `control_dt`, `sensory_dt`, 반응 집계 구간을 각각 설정한다. 정수배가 아닌 주기는 누적 오차 없이 처리할 정책을 정하거나 지원하지 않는 설정으로 거부한다. 신경 시뮬레이션 시간, 물리 시간, 실제 계산 시간을 각각 기록한다. 폐루프에서는 관측·적용 행동의 순서와 지연을 고정한다.

평가 모드에서는 학습 연산과 보상 자극을 비활성화하고 전후 학습 상태가 같은지 확인할 수 있어야 한다. 일반 trial 종료와 학습 종료, checkpoint 복원, 기억 probe reset은 서로 다른 사건이다.

## 5. 실행 결과 형식

초기에는 로컬 파일로 충분하다. 아래 이름은 구현 시 사용할 설계 기준이다.

```text
runs/<run_id>/
  manifest.json         실험·조건·소스·환경·데이터 식별자와 실행 상태
  config.resolved.yaml  기본값·인자 적용 후 실제 사용 설정
  events.jsonl          자극·보상·접촉·phase·실패 사건
  metrics.csv           trial별 원점수·평가값
  checkpoints/          학습 전후 및 probe 분기 상태
  artifacts/            선택적 그래프·영상·신경 기록
```

manifest는 설정 형식 버전, 소스 revision(없으면 파일 checksum), 변경 파일 여부, Python/의존성/OS/backend, seed 묶음, 시작·종료, success/failed/interrupted를 포함한다. 중단한 실행을 성공으로 기록하지 않는다. 대형 원자료와 실행 결과는 소스 저장소에서 제외하는 정책을 구현 시 추가한다.

## 6. 설정과 오류 정책

[설정 명세](../../configs/README.md)를 따른다. 미정인 값은 명시적인 미정 상태로 남기고 실행 요청 시 필요한 값만 검증한다. 형식 오류·지원하지 않는 조합은 조용한 기본값 대체 없이 설명한다. 작은 합성 회로는 인프라 테스트에 사용할 수 있지만 실제 연결망 실험과 명확히 분리한다.


## 7. 첫 구현의 호출 계약과 실행 파일

아래는 **새로 구현할 목표 인터페이스**다. 현재 존재하는 명령으로 오해하지 않는다.

- `connectomes.build(source_manifest, selection) -> CircuitSpec`: sorted IDs, C/P, provenance.
- `Circuit.step(input_spikes, modulation, learning_enabled) -> SpikeEvents`: 정확히1 neural tick, clock은 정수tick으로 보존. 바뀐 상태는 명시적 checkpoint API로 저장.
- `Circuit.snapshot()/restore(state)`, `reset_fast()`, `reset_trace()`, `replace_efficacy(a)`: 각 독립 기능. snapshot 배열은 사본이다.
- `Experiment.run(resolved_config)`는 일정과 branch를 조율한다. scorer와 viewer는 저장 결과만 읽는다.

구현할 CLI 계약:

```bash
python -m connectomes.prepare --config configs/exp001.yaml
python -m experiments.run --config configs/exp001.yaml --stage pilot
python -m experiments.run --config configs/exp001.yaml --stage confirmatory
python -m experiments.run --resume runs/RUN_ID
python -m analysis.report --run runs/RUN_ID
python -m analysis.visualize --run runs/RUN_ID
```

`configs/exp001.yaml`도 아직 없다. stage의 시드 집합은 규약에서 고정한다. confirmatory 명령은 pilot 검증 기록·소스/설정/데이터 고정 여부를 확인한다. 기존 실행 ID가 있으면 overwrite하지 않고 새 ID를 만든다. resume은 같은 ID의 마지막 완료 trial에서 시작하며 해당 trial 기록을 중복 추가하지 않는다. atomic checkpoint로 partial write를 탐지한다.

## 8. 파일 필드와 분석 계약

실험1회 run은 stage의 모든 seed/condition/branch를 포함한다. trial을 유일하게 식별하는 키는 `(seed,condition,branch,phase,trial_id)`다. branch별 경로는 `checkpoints/<seed>/<condition>/<branch>/`를 사용한다.

- manifest: schema_version=1, protocol_id/version, run_id, stage, created/ended_utc, execution_status(running/completed/failed/interrupted), inference_status(supported/not_supported/inconclusive/null), source commit+dirty diff hash(없으면 source manifest), config hash, dependency lock hash, dataset/derived hashes, RNG 알고리즘·stream표, backend/OS/Python/CPU/RAM, duration/storage, 파일 index.
- metrics.csv: 식별키, stimulus_id, cs_role, measurement_start/end_s, neuron_count, spike_count, rate_hz_per_neuron, score, validity, missing_reason. 빈값은 결측이며 숫자0과 구분한다. seed 요약은 별도 summary.csv.
- events.jsonl: 식별키, event_id, tick, event_type, payload. stimulus_start/end, modulation_start/end, checkpoint, reset, error, terminal을 기록한다. schema_version은 manifest와 연결.
- checkpoints: 배열은 NPZ(pickle 없이), metadata JSON에 시간/RNG state/배열명·shape·dtype/구조 해시. fast(v,x,refractory,delay), trace(e), slow(a)를 독립 배열로 저장. 모델/P/C는 공유 manifest 참조.
- spikes/trace/그림: [VIZ-001](VISUALIZATION.md)의 식별키·origin·시간 규약을 따른다. 출력별 source hash로 출처 연결.

예측 가능한 오류는 invalid 설정/schema·data_invalid·numerical_invalid·budget_exceeded로 명확히 구분한다. CLI의 성공 exit code는 실행/기록의 정상 완료를 뜻하며 연구 가설 성공을 뜻하지 않는다. negative 실험도 정상 완료일 수 있다.

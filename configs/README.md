# 설정 계약

현재 default.yaml은 기존 toy 타격 초안이며 실행기에 연결되지 않았다. 아래는 구현할 신규 설정의 계약이다. 실제 YAML·로더는 Claude가 I-02에서 작성한다.

## exp001.yaml

필수 최상위 키는 schema_version(1), experiment, dataset, circuit, plasticity, stimulus, evaluation, seeds, runtime, recording. 알려지지 않은 키와 단위 없는 시간 입력은 거부한다. manifest 경로는 프로젝트 root 기준으로 해석하고 resolved 설정에는 절대경로도 저장한다.

| 구획 | 넣을 내용 / 기본값의 단일 출처 |
| --- | --- |
| experiment | id=EXP-001, protocol_version=1.0, stage, conditions=[paired,frozen,unpaired,modulation_only] |
| dataset | name=MaleCNS, version=1.0, raw_manifest, derived_manifest, circuit_id=mcns-kc-mbon11-v1 |
| circuit | dtype=float64, backend=numpy_cpu, dt_s/tau_m_s/tau_s_s/refractory_s/delay_s/G/reset/threshold: [DATA_MODEL](../docs/design/DATA_MODEL.md) |
| plasticity | rule=dopamine_gated_depression, tau_e_s/eta_per_s/a_min/a_max/a_initial: DATA_MODEL |
| stimulus | active_fraction=0.1, rate_hz=20, trial_s=2, stimulus_window_s=[0,1], modulation_window_s=[0.5,1], train_pairs=20 |
| evaluation | probe_trials_per_stimulus=10, rate_window_s=[0.1,1], retention_s=10, reversal_pairs=40, effect_min=0.20, bootstrap_count=10000, bootstrap_seed=20260916 |
| seeds | pilot=[0,1,2], confirmatory=100..129, PCG64 stream표는 [EXP-001](../docs/experiments/EXP-001-associative-learning.md) |
| runtime | workers=1, pilot_wall_seconds=1200, confirmatory_wall_seconds=7200, rss_limit_bytes=2147483648, pilot_output_limit_bytes=1073741824, confirmatory_output_limit_bytes=5368709120 |
| recording | output_root=runs, checkpoints=각 phase/trial 경계, spike/trace 규약은 [VIZ-001](../docs/design/VISUALIZATION.md) |

모든 기본값은 명시적으로 resolved 파일에 써서 누락값 추론 없이 재현 가능하게 한다. experiment/profile의 기본값 → 파일 → 명시적 CLI 순으로 적용한다. 시드·수치·규약 변경은 새 버전이 필요하다. 외부 readout 학습은 EXP-001에서 거부한다. 평가의 learning_enabled=false/d=0은 사용자 override할 수 없는 규약 조건이다.

물리 과제는 별도 `configs/env001.yaml`로 [ENV-001](../docs/design/ENV-001-interception.md)의 target/launch/rest/joint/actuator/clock/terminal/reward를 작성한다. exp001에 물리 옵션을 섞지 않는다. 종전 하드코딩·새 설정의 이중 기준을 남기지 않는다.

야구장은 향후 별도 `configs/baseball_b0.yaml`에서 scene/body/pitch/aerodynamics/observation/reward/curriculum을 고정한다. ENV-002 좌표계를 사용하며 ENV-001 설정을 묵시적으로 상속하지 않는다.

# FlyOhtani

실제 초파리 연결망 기반 회로의 새로운 과제 학습과 기억을 연구하는 프로젝트.

## 현재 방향

**연합학습 → 기억 검증 → 시간 맞추기 → 공 가로채기** 순서로 연구한다. 회로 내부의 학습을 핵심으로 보고, 출력층만 학습하는 모델과 기존 강화학습 모델은 대조군으로 사용한다.

현재는 연구 계획과 설계 정리 단계다. Codex와는 계획·구조·실험 규약을 정리하고, 실제 코드 구현·테스트는 사용자와 Claude가 진행한다. 기존 코드는 MuJoCo 타격 환경과 toy 제어기의 초기 뼈대이며, 실제 연결망·내부 가소성 학습·검증된 타격 성능은 아직 없다.

### 먼저 읽을 문서

1. [연구 계획](docs/RESEARCH_PLAN.md) — 연구 질문과 단계별 목표.
2. [설계 결정](docs/DECISIONS.md) — 확정 사항, 제안, 미결정 사항.
3. [구조와 데이터 계약](docs/ARCHITECTURE.md) — 모듈 책임과 실행·상태·기록 규약.
4. [첫 실험 규약 초안](docs/experiments/EXP-001-associative-learning.md) — 학습·기억 평가 설계.
5. [Claude 구현 인계](docs/IMPLEMENTATION_HANDOFF.md) — 착수 가능한 작업과 검증 기준.

[현황 진단](docs/PROJECT_AUDIT_2026-09-16.md)과 [리서치](docs/RESEARCH_REVIEW_2026-09-16.md)에 근거와 한계를 기록했다.

## Project Layout

```text
docs/
  README.md
  RESEARCH_PLAN.md
  ARCHITECTURE.md
  DECISIONS.md
  IMPLEMENTATION_HANDOFF.md
  experiments/
    EXP-001-associative-learning.md
  PROJECT_PLAN.md
  STATUS.md
  TEST_LOG.md
  RESEARCH_SOURCES.md
envs/
  fly_batter_env.py
  assets/
    fly_batter.xml
controllers/
  mlp_policy.py
  snn_policy.py
  brian2_stdp_controller.py
encoders/
  retina_encoder.py
  ball_state_encoder.py
train/
  train_ppo.py
  train_stdp.py
analysis/
  plot_rewards.py
  spike_raster.py
  weight_heatmap.py
demos/
  record_episode.py
configs/
  default.yaml
```

## 기존 코드 실행 예시 — 실행 검증 전

아래는 초기 뼈대의 실행 경로다. 환경 구성과 실행 검증은 [구현 인계](docs/IMPLEMENTATION_HANDOFF.md)의 I-01에서 진행한다. 현재 환경에는 필요한 의존성이 설치되어 있지 않다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m demos.record_episode --episodes 3 --render none
```

수치 검증을 먼저 수행하고 운영체제별 렌더링 설정은 별도로 검증한다. `human` 창 표시와 영상 녹화는 현재 구현되지 않았다. [설정 안내](configs/README.md)의 기본값은 기존 toy 환경용이며 연구 프로토콜로 확정된 값이 아니다.

## Environment

`FlyBatterEnv` is a Gymnasium-compatible MuJoCo environment.

- Observation: ball position, ball velocity, swing angle, swing velocity, time-to-impact estimate, and previous contact signal.
- Action: one scalar torque command for the swing hinge.
- Reward terms:
  - hit success bonus
  - timing error penalty
  - contact velocity bonus
  - energy cost penalty
  - miss penalty near the plate

현재 자산은 1관절 추상 타격 장치다. 실제 초파리의 신체 치수·질량을 재현하지 않는다. 위 보상 항목은 기존 코드의 이름이며, 물리적 의미와 접촉 검사는 [수정 항목](docs/IMPLEMENTATION_HANDOFF.md)의 I-03에서 정비한다.

## Baselines

The first available controller is scripted:

```python
from controllers import ScriptedSwingController

controller = ScriptedSwingController(trigger_distance=0.45)
```

NumPy MLP와 SNN은 toy 추론 코드다. PPO 실행 파일은 SB3의 별도 MLP 정책을 사용하며, SNN 학습과 Brian2 가소성은 아직 연결되지 않았다. 인터페이스는 [구조 문서](docs/ARCHITECTURE.md)에 따라 구현 단계에서 정비한다.

## Project Memory

Detailed project context is tracked in `docs/`:

- `docs/RESEARCH_PLAN.md` keeps the active research plan; `docs/PROJECT_PLAN.md` preserves the historical scaffold roadmap.
- `docs/STATUS.md` records current state and decisions.
- `docs/TEST_LOG.md` records validation commands and results.
- `docs/RESEARCH_SOURCES.md` tracks connectome sources, citations, and license notes.

## Research Sources and Data Licenses

This repository currently contains no FlyWire or Janelia hemibrain connectome data. The current SNN and retina-like components are hand-written scaffolds for future experiments.

Candidate connectome references:

- FlyWire public release data is listed by FlyWire as `CC BY-NC 4.0`; cite the FlyWire papers before using derived connectivity data.
- Janelia FlyEM hemibrain is listed by Janelia as `CC-BY`.

See `docs/RESEARCH_SOURCES.md` before importing external neural connectivity, morphology, annotation, or derived data files. Code license and external data licenses should be treated separately.

## Roadmap

1. 재현할 학습 논문·회로·평가 규약을 선택한다.
2. 실제 연결 데이터와 신경 동역학을 단독 검증한다.
3. 조건화와 기억 유지·제거를 비교 실험으로 확인한다.
4. 시간 과제에서 공 가로채기로 확장한다.

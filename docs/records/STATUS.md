# Status

## 2026-09-16 — 문서 정리: 폴더 재구성과 결정 동기화 (latest)

- 사용자 요청으로 `docs/`를 정리했다. 정리 전 조사에서 `docs/PLAN.md`와 `docs/design/DATA_MODEL.md`(당일 00:30, 가장 최근 배치)가 그때까지 `docs/DECISIONS.md`·`docs/experiments/EXP-001-associative-learning.md`(0.1-draft)가 "미정"으로 표시하던 Q-01~06 중 다수를 이미 구체값(D01~D09: MaleCNS v1.0, KC→MBON11 회로 `mcns-kc-mbon11-v1`, `dopamine_gated_depression` 가소성 규칙, Python 3.11/NumPy CPU/본 평가 30 시드)으로 확정해 둔 상태였음을 발견했다. 이 확정이 CLAUDE.md·DECISIONS.md·STATUS.md·EXP-001 문서에 반영되지 않아 두 세대의 문서가 불일치 상태로 공존했다.
- 사용자에게 확인한 뒤 PLAN.md/DATA_MODEL.md를 유효한 최신 연구 결정으로 채택하고, `docs/README.md`가 이미 전제하고 있던 하위 폴더 구조(records/, design/, implementation/, research/)로 마이그레이션을 완료했다: `STATUS.md`→`records/STATUS.md`, `TEST_LOG.md`→`records/VALIDATION_LOG.md`, `ARCHITECTURE.md`→`design/ARCHITECTURE.md`, `IMPLEMENTATION_HANDOFF.md`→`implementation/WORK_PACKAGES.md`, `PROJECT_AUDIT_2026-09-16.md`→`records/PROJECT_AUDIT_2026-09-16.md`.
- 대체된 이전 세대 문서(`PROJECT_PLAN.md`, `RESEARCH_PLAN.md`, `RESEARCH_REVIEW_2026-09-16.md`)는 삭제하지 않고 `docs/archive/`로 옮겼다(이력 보존, 사유는 `docs/archive/README.md` 참고).
- `docs/DECISIONS.md`의 Q-01~06 표와 `docs/experiments/EXP-001-associative-learning.md`(0.1-draft → 0.2)를 PLAN.md/DATA_MODEL.md의 실제 결정에 맞춰 갱신했다. Q-05 중 자극 A/B 배정·시점·강도의 구체 수치와 통과 기준 숫자는 여전히 미정으로 정확히 남겨뒀다(임의 수치로 채우지 않음).
- `docs/implementation/VALIDATION.md`는 아직 통합된 내용이 없어 관련 문서 위치를 가리키는 미작성 스텁으로만 만들었다.
- 저장소에 `.git`이 없어 재구성 전 상태를 baseline commit으로 스냅샷한 뒤 이동·편집을 진행했다.
- 이 작업은 문서 재구성·상호 참조 정합성 작업이며, 코드 실행·의존성 설치·데이터 임포트·연구 실행은 하지 않았다.

## 2026-09-16 — Architecture and Claude handoff

- User confirmed the division of work: Codex handles planning and structure; Claude and the user handle implementation and tests.
- Updated the root README to the active research direction and removed the obsolete sequential PPO→SNN roadmap from the main entry point.
- Added `CLAUDE.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `IMPLEMENTATION_HANDOFF.md`, `configs/README.md`, and the draft `experiments/EXP-001-associative-learning.md`.
- Defined module responsibilities, clock/unit boundaries, fast/slow/trace state handling, independent memory probes, configuration and run records.
- Handoff work I-01/I-02 and the independent physics fixes I-03 can proceed with Claude. Dataset/model implementation and EXP-001 scientific execution depend on the listed research choices.
- Scientific paper, dataset, circuit extent, detailed parameters, evaluation thresholds, and compute budget remain pending; the draft is not an executable experiment.
- Existing Python, XML, TOML and YAML implementation/configuration are intentionally unchanged. No application tests, installs, data imports or model runs were performed in this documentation task.

## 2026-09-16 — Planning-first research

- User direction: planning before implementation; investigate whether real fruit-fly circuits can learn new tasks.
- References supplied by the user: Stonkfly, Doom/Smash Bros., Minecraft, NeuroMechFly-based demos, and FLM.
- Added a dated source audit and primary-source research review. The active proposal is `RESEARCH_PLAN.md`; the previous implementation roadmap is historical.
- Proposed sequence: select a literature-backed mushroom-body learning protocol; verify actual connectivity and neural dynamics; test conditioning, retention, and memory removal; extend to timing and then interception.
- Output-layer-only learning is a comparison condition, not the main evidence for internal circuit learning.
- Source concerns: gravity missing from launch calculation; contact checked after frame skipping; metric definitions; neural/physics timing; disconnected configuration and experiment records.
- Current shell: macOS arm64, Python 3.14.0; major runtime/learning packages absent in that interpreter. Python AST checks passed for 19 files. Runtime physics and learning remain unvalidated.
- No implementation, dependency installation, external data import, or training was performed. Documentation only.
- Pending planning choices: reference paper/protocol, dataset and circuit scope, whether whole-brain scale is essential, available hardware and budget. The older implementation next actions below are deferred.

## 2026-09-15

### Current State

- Repository scaffold exists directly at the project root.
- Python package metadata exists in `pyproject.toml`.
- Minimal MuJoCo environment exists in `envs/fly_batter_env.py`.
- MuJoCo XML asset exists in `envs/assets/fly_batter.xml`.
- Scripted swing baseline exists in `controllers/scripted.py`.
- Placeholder MLP, SNN, and Brian2 STDP controller interfaces exist.
- Retina-like and compact ball-state spike encoders exist.
- Demo, training, analysis, and config entry points exist.
- Documentation folder added to track project plan, status, test results, and research sources.

### Decisions

- Start with a deliberately simple agent: one body and one actuated swing limb.
- Use MuJoCo for contact and rigid-body physics.
- Use Gymnasium-style environment APIs for compatibility with PPO tooling.
- Treat external connectome datasets as data dependencies with separate citation and license requirements.
- Do not import FlyWire or hemibrain data until the project explicitly needs it.

### Known Limitations

- The current local environment did not have `mujoco` or `gymnasium` installed during initial validation.
- The MuJoCo environment has passed Python syntax checks and XML syntax checks, but not runtime physics validation yet.
- Scripted swing parameters are initial guesses and should be tuned after MuJoCo runtime is installed.
- The SNN and Brian2 controllers are scaffolds, not finished learning systems.

### Next Actions

1. Install runtime dependencies with `pip install -e ".[dev]"`.
2. Run `python demos/record_episode.py --episodes 3`.
3. If contact does not occur, tune:
   - ball target point
   - flight time range
   - swing hinge torque gear
   - swing trigger distance
   - limb length and collision capsule radius
4. Add first real metrics to `docs/TEST_LOG.md`.
5. Add tests once environment runtime behavior is confirmed.

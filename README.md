# FlyOhtani

실제 초파리 연결망 기반 회로의 새로운 과제 학습과 기억을 연구하는 프로젝트.
2026-09-16 갱신(R-01 문서 정리, `docs/implementation/REFACTOR-PLAN.md`) —
아래는 실제 실행 입구다. 연구 배경·결정은 `docs/PLAN.md`, 전체 문서 지도는
`docs/README.md`를 본다.

## 두 개의 독립 트랙

**신경회로 트랙(연구 본류)**: 연합학습 → 기억 검증 → 시간 맞추기 → 공
가로채기 순서로, 실제 초파리 연결망에서 내부 가소성 학습을 검증한다.
`docs/experiments/EXP-001-associative-learning.md` 규약(1.0)은 확정됐지만
**구현은 아직 시작하지 않았다** — `encoders/`·`train/`·`analysis/`는 여전히
초기 toy scaffold다.

**물리 환경 트랙(ENV-001 → ENV-002)**: MuJoCo 기반 타격 환경. ENV-001(단순
타격 과제)과 ENV-002 B0(야구장 고정 직구)는 물리 검증까지 끝났고, ENV-002
B1(야구장 9코스 타격)은 `mid_mid` 코스 한 곳만 실제 전방 타구 성공까지
검증됐다. 두 트랙은 독립적으로 진행되며(`docs/PLAN.md` D08) 야구 성능이
신경회로 학습의 증거는 아니다. 현재 상태와 남은 한계는
`docs/records/STATUS.md`.

## 설치와 실행

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,video]"

# 테스트 (두 진입점 모두 87 passed로 일치)
pytest tests/ -q
python -m pytest tests/ -q

# lint
ruff check envs controllers encoders train analysis demos scripts tests

# ENV-002 B1 mid_mid 코스 영상/수치 재생성
python -m demos.record_baseball_b1_mid_mid_fix
python -m demos.record_i07c_before_after   # 스윙 개선 전/후 비교
```

셸의 기본 `python3`가 이 프로젝트용이 아닐 수 있으므로 버전을 명시해 venv를
만든다. `human` 창 표시는 아직 구현되지 않았다(`render_mode="rgb_array"` 또는
`None`만 지원).

## Project Layout

```text
docs/            연구 계획·설계 규약·상태·검증 기록 (docs/README.md가 지도)
envs/            MuJoCo 환경: fly_batter_env(ENV-001), baseball_env(B0),
                 baseball_b1_env(B1), baseball/(코스·보상 설정),
                 fly_visual*(파리 외형), assets/(XML·메시)
controllers/     scripted/oracle 제어기, toy SNN/MLP 정책
encoders/        신경회로 트랙용 감각 인코더 (toy scaffold, 미착수)
train/           PPO/STDP 학습 진입점 (STDP는 미구현, 실행 시 명시적 오류)
analysis/        결과 분석·수렴 진단 스크립트
demos/           episode 실행·영상 기록 CLI
scripts/         파리 외형 자산 생성·스윙 진단 CLI (설치 패키지 아님)
tests/           pytest 스위트 (87개, envs 전체)
configs/         legacy toy 설정 (연구 프로토콜로 확정된 값 아님)
```

## 신경회로 트랙 상세

`FlyBatterEnv`는 Gymnasium 호환 MuJoCo 환경이다 (ENV-001, `envs/fly_batter_env.py`).

- Observation: ball position, ball velocity, swing angle, swing velocity, time-to-impact estimate, and previous contact signal.
- Action: one scalar torque command for the swing hinge.
- `info["end_reason"]` distinguishes `hit` / `ground_contact` / `passed_no_contact` / `timeout`.

NumPy MLP와 SNN은 toy 추론 코드다. PPO 실행 파일은 SB3의 별도 MLP 정책을
쓰며, SNN 학습과 Brian2 가소성은 아직 연결되지 않았다. 인터페이스는
[구조 문서](docs/design/ARCHITECTURE.md)에 따라 구현 단계에서 정비한다.

## 야구 환경 트랙 상세

[BASEBALL-SPEC](docs/design/BASEBALL-SPEC.md): 구장·투구·2축 배트·타구 추적·
채점·보상의 현행 규칙. [FLY-VISUAL-SPEC](docs/design/FLY-VISUAL-SPEC.md):
NeuroMechFly 메시 기반 파리 외형(물리와 분리된 시각 레이어). 둘 다 mid_mid
코스에서 검증됐고 나머지 8코스는 재보정 전이라 사용 금지다.

## Research Sources and Data Licenses

This repository currently contains no FlyWire or Janelia hemibrain
connectome data (신경회로 트랙). `envs/assets/mesh_neuromechfly/`는 NeuroMechFly
(flygym==1.2.1, Apache-2.0)에서 가져온 파리 외형 mesh이며 connectome 데이터가
아니다 — 출처/해시는 `docs/RESEARCH_SOURCES.md`와 `THIRD_PARTY_NOTICES.md`.

- FlyWire public release data is listed by FlyWire as `CC BY-NC 4.0`; cite the FlyWire papers before using derived connectivity data.
- Janelia FlyEM hemibrain is listed by Janelia as `CC-BY`.

See `docs/RESEARCH_SOURCES.md` before importing external neural connectivity,
morphology, annotation, or derived data files. Code license and external
data licenses should be treated separately.

`docs/PLAN.md`와 `docs/design/DATA_MODEL.md`는 현재 EXP-001 기본값
(MaleCNS v1.0, KC→MBON11 회로, LIF/가소성 식)을 모델링 선택으로 기록하며
검증된 생물학적 사실이라고 주장하지 않는다.

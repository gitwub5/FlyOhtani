# 현재 상태

2026-09-17 갱신 (Phase 0 완료). 이 문서는 **지금** 무엇이 검증됐고 무엇이
막혀 있는지만 담는다. 결정은 [PLAN](../PLAN.md), v1에서 넘어온 사실은
[선행 발견](PRIOR-FINDINGS.md), 실행 근거는 [검증 기록](VALIDATION_LOG.md).

## Phase 0 — 보존하고 정리: 완료

- v1 전체를 git 태그 `archive/human-scale-v0`(및 동명 브랜치)로 고정했다.
  작업 트리에서 삭제한 것은 전부 거기서 복구할 수 있다.
- 삭제: `envs/ controllers/ encoders/ demos/ analysis/ train/ scripts/
  configs/` 및 v1 문서 87개 중 84개. 사람 크기 구장·3축 강체 배트·KC-01a
  협응 탐색 코드 약 15,000줄.
- 이관: NeuroMechFly STL 45개 + Apache-2.0 라이선스 + provenance manifest →
  `flyohtani/assets/mesh_neuromechfly/`. 시각 모듈 6개 → `flyohtani/sense/`.
- 신규: `flyohtani/units.py`(mm·g·μN 규약과 원본 실측 상수),
  `docs/PLAN.md`, `docs/records/PRIOR-FINDINGS.md`.

## 지금 실제로 동작하는 것

| 대상 | 상태 |
| --- | --- |
| `flyohtani/units.py` | SI 환산이 v1에서 검증된 값과 일치함을 확인(9.81 m/s², kp 4.5e-8 N·m/rad, forcerange ±6.5e-8 N·m, 질량 1 mg, 세그먼트 비율 합 1.0, 능동 DOF 7개) |
| `flyohtani/sense/` 검출·추적 | 합성 프레임 기준 회귀 테스트 통과. **실제 렌더 대상이 없어 렌더 기반 검증은 현재 불가** |
| 입력 누출 방지 | AST 정적 검사 통과. 금지 prefix를 `flyohtani.world`/`flyohtani.task`로 미리 등록해 뒀다(그 모듈이 생기기 전에 검사가 먼저 존재) |
| 테스트·린트 | `python -m pytest`/`pytest` 두 진입점 모두 **20 passed**, `ruff check .` 클린 |

## 알려진 한계 (임의로 고치지 않고 그대로 보고)

- **렌더 기반 시각 검증이 비어 있다.** v1의 실제 렌더 추적·카메라 head 추종
  테스트 3개는 대상 rig가 삭제되면서 함께 제거됐다. Phase 1/3에서 새 몸체에
  대해 복원해야 하며, 그 전까지 검출률 수치를 보고하지 않는다.
- **`VisionObservation`의 자기감각 필드가 죽은 이름이다.** `torso/swing/tilt`는
  v1의 3축 기구 관절이다. Phase 3에서 NeuroMechFly 앞다리 관절로 교체한다.
  임의로 새 이름을 지어내지 않고 그대로 두었다.
- **`BallDetector`의 공 색(`BALL_COLOR_RGB`)이 v1 씬의 재질값이다.** Phase 2의
  새 공 재질과 맞추거나 상수를 바꿔야 한다. "화면에 그 색 물체가 하나뿐"이라는
  전제도 새 씬에서 다시 확인해야 한다.
- **접촉 수용 기준 미달이 해결되지 않은 채 넘어왔다.** v1에서 반발계수 ≈0.29
  (기준 0.3~0.7), 침투 0.04~0.05 m(기준 30%×반지름)로 FAIL이었다. 원인은
  재료(solref/solimp)로 좁혀졌고 기하 결함은 분리·설명됐다
  ([선행 발견](PRIOR-FINDINGS.md) §3). **게이트 G2를 통과하기 전에는 학습을
  시작하지 않는다.**
- **커넥톰 데이터가 없다.** MaleCNS에서 루밍 검출 계열 서브그래프를 실제로
  받을 수 있는지 아직 확인하지 않았다(게이트 G4). 뉴런 타입 이름·규모를
  데이터로 확인하기 전까지 가정하지 않는다.
- **파리가 배트를 휘두를 수 있는지 아직 모른다.** v1의 B1/B2는 설계만 했고
  실제 관절 구동은 한 번도 실행되지 않았다. 게이트 G1이 답할 질문이다.

## 다음 작업

[PLAN](../PLAN.md)의 Phase 1(몸)과 게이트 G4(커넥톰 데이터 접근 확인)를
병행한다. G1(무공 스윙 스윕)이 배트 끝 최대 속도를 실측하기 전까지 Phase 2의
공 질량·투구 속도·구장 치수는 정할 수 없다.

# 문서 시작점

2026-09-16 갱신(R-01 문서 정리, `docs/implementation/REFACTOR-PLAN.md`). 목표는
실제 초파리 연결망을 바탕으로 만든 회로에서 경험에 의한 내부 변화와 기억을
검증하는 것이다. 사용자와 Codex는 연구 계획·구조·실험 규약을, 사용자와 Claude는
구현·테스트·실험을 담당한다(`../CLAUDE.md`).

## 필독 (신규 에이전트는 이 3개만 먼저 읽는다)

| 순서 | 문서 | 답하는 질문 |
| --- | --- | --- |
| 1 | `../CLAUDE.md` | 협업 규칙, 문서 읽는 순서, 임의 수치를 채우지 않는 원칙 |
| 2 | [현재 상태](records/STATUS.md) | 지금 무엇이 검증됐고 무엇이 막혀 있는가? |
| 3 | [연구 로드맵과 결정](PLAN.md) | 연구 질문·단계·확정된 설계 결정(D01~D18)은 무엇인가? |

이 3개 + 아래에서 실제로 작업할 spec/task 문서만 읽으면 된다. archive/와
records/(evidence·validation·이 문서의 STATUS_HISTORY 제외)는 과거 회귀
조사가 필요할 때만 연다.

## 작업별로 읽을 문서

| 하려는 일 | 읽을 문서 |
| --- | --- |
| KC 검증·시각 설계(완료, 다음 배정 대기) | [작업 명세](tasks/KC-01a-VALIDATION-AND-VISION.md), [검증 결과](records/KC-01a-VALIDATION.md), [VISION-01 설계](design/VISION-01.md), [회전 방향 계약](design/KC-01a-DIRECTION-CONTRACT.md) |
| 시각·파리 몸 기반 전환(VM-01+후속, 완료 — V1/V2 PASS, P1 FAIL→P2 원인분리, B1 설계+B2 단위확정) | [작업 명세](tasks/VISUOMOTOR-PIVOT.md), [전체 보고](records/VM01-REPORT.md), [P2 원인·수정안](records/VM01-P2-CONTACT.md), [B1/B2 설계](design/VM01-B1-MINIMAL-BODY.md) |
| 야구 환경(구장/투구/배트/타구 판정/보상) 작업 | [야구 규약](design/BASEBALL-SPEC.md) |
| 몸통-배트 협응(KC-01a) 작업 | [KC-01a 규약](design/KC-01a-TORSO-BAT-COORDINATION.md), [잠정 비교(정정됨)](records/KC-01a-COMPARISON.md), [검증 결과](records/KC-01a-VALIDATION.md), [회전 방향 계약](design/KC-01a-DIRECTION-CONTRACT.md) |
| 파리 외형(자세/색상/메시) 작업 | [파리 외형 규약](design/FLY-VISUAL-SPEC.md) |
| 신경회로 회로/수치 모델 작업 | [데이터·수치 모델 계약](design/DATA_MODEL.md) |
| 신경회로 실험(EXP-001) 작업 | [EXP-001](experiments/EXP-001-associative-learning.md) |
| 모듈 경계·데이터 계약(신경회로 트랙) 확인 | [구조 계약](design/ARCHITECTURE.md) |
| ENV-001(초파리 단순 타격) 작업 | [ENV-001](design/ENV-001-interception.md) |
| 시각화(VIZ-001) 작업 | [시각화 계획](design/VISUALIZATION.md) |
| 다음에 뭘 하면 되는지 | [구현 작업표](implementation/WORK_PACKAGES.md) |
| 검증 기준/실행 명령 확인 | [검증 명세](implementation/VALIDATION.md), [검증 기록 색인](records/VALIDATION_LOG.md) |
| 외부 데이터·자산 출처/라이선스 확인 | [연구 출처](RESEARCH_SOURCES.md) |
| 코드 리팩토링/정리 작업 | [R-01 리팩토링 계획](implementation/REFACTOR-PLAN.md) |

명세에 나온 명령과 API는 현재 구현 상태와 다를 수 있다 — 각 spec 문서가 "구현
목표"와 "현재 검증됨"을 구분해 표시하므로 그 표시를 따른다.

## 완료된 작업 찾기

완료 작업의 결과·경위는 [완료 작업 색인](records/INDEX.md)에서 작업 ID로 찾는다.
대체된 과거 문서(로드맵 초안 등)는 [`archive/`](archive/README.md)에 있다.

## 문서 관리 원칙

- 현재 규약은 문서마다 하나만 유지한다. 완료된 "다음 작업" 지시는 해당 spec에
  남기지 않고 STATUS/작업표로 옮긴다. 대체된 문서는 삭제 대신 상단에 대체 경로를
  표시하고 archive/records로 위치를 명확히 한다.
- 문서와 구현이 다르면 차이를 먼저 기록한다. 검증이 실패하면 실제 상태를
  보고하며 합성 자료로 대체하지 않는다.
- 구현 중에는 STATUS를 현재 스냅샷으로 갱신하고, 실행 명령·환경·결과 경로는
  `docs/records/validation/`에 새 파일로 추가한 뒤 VALIDATION_LOG 색인에 한
  줄을 더한다. 긴 원자료는 `runs/`에 둔다(git 추적 제외).
- 각 spec은 id/status/version/대체 문서를 표시해 무엇이 현재인지 한 곳에서
  답할 수 있게 한다.

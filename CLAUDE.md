# FlyOhtani 구현 작업 안내

프로젝트 목표는 실제 초파리 연결망 기반 회로의 새로운 과제 학습과 기억을 연구하는 것이다.

## 읽는 순서

`docs/README.md`의 순서를 따른다:

1. `docs/records/STATUS.md`의 최신 상태
2. `docs/PLAN.md`의 연구 결정 (연구·환경·시각화 결정 D01~D14)
3. `docs/design/DATA_MODEL.md`의 수치·데이터 계약
4. `docs/design/ARCHITECTURE.md`의 모듈·데이터 계약
5. 해당 실험 문서: `docs/experiments/EXP-001-associative-learning.md`
6. `docs/implementation/WORK_PACKAGES.md`의 작업 단위와 완료 기준
7. `docs/implementation/VALIDATION.md`의 검증 명세

결정의 단일 기준은 `docs/PLAN.md`이며 `docs/DECISIONS.md`는 위치 안내다. `docs/archive/`의 `PROJECT_PLAN.md`·`RESEARCH_PLAN.md`·`RESEARCH_REVIEW_2026-09-16.md`는 과거 로드맵/초안이며 각각 `docs/PLAN.md`, `docs/PLAN.md`, `docs/research/REVIEW.md`로 대체되었다. 읽기 경로가 없던 legacy toy 설정 `configs/default.yaml`은 `docs/archive/configs-default.yaml`로 옮겼다(R-04) — 과학적으로 확정된 기본값으로 취급하지 않는다.

## 역할과 작업 원칙

- 사용자와 Codex는 연구 계획·구조·실험 규약을 정리한다. 사용자와 Claude는 실제 구현·테스트를 진행한다.
- 사용자가 지정한 작업 단위를 구현한다. 독립적인 기반 작업은 미결정 연구 항목 때문에 멈추지 않는다.
- 데이터·논문·가소성 식 등 미결정 연구 선택은 임의의 수치로 채우지 않는다. 의존하는 실험만 대기하고 독립 작업을 계속한다.
- 기존 소스는 초기 뼈대다. 설치 성공, 물리 검증, 학습 성능을 가정하지 않는다.
- 실험과 무관한 폴더 이동·전체 재작성보다 책임 분리와 필요한 변경을 우선한다.
- 실행 결과는 `docs/records/VALIDATION_LOG.md`, 상태 변화는 `docs/records/STATUS.md`에 남긴다. 테스트 통과와 연구 가설의 검증을 구분한다.
- 연구 설계 변경은 `docs/PLAN.md`와 해당 규약 버전에 반영한다. 실패·무효 결과도 보존한다.
- 외부 코드·데이터를 사용할 때 출처·버전·체크섬·조건을 `docs/RESEARCH_SOURCES.md`와 데이터 manifest에 기록한다.

이 파일은 인계 안내이며 현재 사용자 지시가 우선한다.

## 다음 작업

`docs/records/STATUS.md`가 지금 검증된 상태와 알려진 한계를,
`docs/implementation/WORK_PACKAGES.md`의 상태 표가 미착수/진행중 작업을 담는다.
과거에는 이 파일에 완료된 작업의 "다음 지시"가 계속 쌓여 이미 끝난 일이 최신
작업처럼 보이는 문제가 있었다(R-01 문서 정리, `docs/implementation/REFACTOR-PLAN.md`,
가 이 파일을 포함해 바로잡았다) — 이제 그런 지시는 여기 남기지 않고 STATUS/
작업표로만 관리한다. 완료된 작업의 경위는 `docs/records/INDEX.md`에서 작업
ID로 찾는다.

현재 야구 환경(ENV-002)의 현행 규칙은 `docs/design/BASEBALL-SPEC.md`, 파리
외형은 `docs/design/FLY-VISUAL-SPEC.md`에 통합돼 있다 — 개별 설계 문서
(`ENV-002-baseball.md`, `ENV-002-B1-courses.md`, `ENV-002-BATTED-BALL.md`,
`BATTING-QUALITY-AND-SWING.md`, `FOLLOWTHROUGH-AND-FLY-MODEL.md`,
`FLY-BATTING-STANCE-AND-COLOR.md`)는 대체됨 표시와 함께 역사적 근거로
보존했다(코드 주석이 여전히 그 경로를 가리킨다).

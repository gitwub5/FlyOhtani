# FlyOhtani 구현 작업 안내

프로젝트 목표는 실제 초파리 연결망 기반 회로의 새로운 과제 학습과 기억을 연구하는 것이다.

## 읽는 순서

1. `docs/STATUS.md`의 최신 상태
2. `docs/DECISIONS.md`의 확정·미결정 구분
3. `docs/ARCHITECTURE.md`의 모듈·데이터 계약
4. `docs/IMPLEMENTATION_HANDOFF.md`의 작업 단위와 완료 기준
5. 해당 실험 문서: `docs/experiments/EXP-001-associative-learning.md`

`docs/PROJECT_PLAN.md`는 과거 로드맵이다. 현재 계획은 `docs/RESEARCH_PLAN.md`다. `configs/default.yaml`은 읽기 경로가 없는 legacy toy 설정이며, 과학적으로 확정된 기본값으로 취급하지 않는다.

## 역할과 작업 원칙

- 사용자와 Codex는 연구 계획·구조·실험 규약을 정리한다. 사용자와 Claude는 실제 구현·테스트를 진행한다.
- 사용자가 지정한 작업 단위를 구현한다. 독립적인 기반 작업은 미결정 연구 항목 때문에 멈추지 않는다.
- 데이터·논문·가소성 식 등 미결정 연구 선택은 임의의 수치로 채우지 않는다. 의존하는 실험만 대기하고 독립 작업을 계속한다.
- 기존 소스는 초기 뼈대다. 설치 성공, 물리 검증, 학습 성능을 가정하지 않는다.
- 실험과 무관한 폴더 이동·전체 재작성보다 책임 분리와 필요한 변경을 우선한다.
- 실행 결과는 `docs/TEST_LOG.md`, 상태 변화는 `docs/STATUS.md`에 남긴다. 테스트 통과와 연구 가설의 검증을 구분한다.
- 연구 설계 변경은 `docs/DECISIONS.md`와 해당 실험 버전에 반영한다. 실패·무효 결과도 보존한다.
- 외부 코드·데이터를 사용할 때 출처·버전·체크섬·조건을 `docs/RESEARCH_SOURCES.md`와 데이터 manifest에 기록한다.

이 파일은 인계 안내이며 현재 사용자 지시가 우선한다.

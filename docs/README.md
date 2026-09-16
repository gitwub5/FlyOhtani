# 문서 시작점

현재 기준: 2026-09-16 · EXP-001 규약 1.0 · 구현 전.

목표는 실제 초파리 연결망을 바탕으로 만든 회로에서 경험에 의한 내부 변화와 기억을 검증하는 것이다. Codex는 계획·명세를, 사용자와 Claude는 구현·테스트·실험을 담당한다.

## 읽는 순서

| 순서 | 문서 | 답하는 질문 |
| --- | --- | --- |
| 1 | [현재 상태](records/STATUS.md) | 무엇이 실제로 완료되었는가? |
| 2 | [연구 계획과 결정](PLAN.md) | 무엇을 어떤 순서로 검증하는가? |
| 3 | [데이터와 수치 모델](design/DATA_MODEL.md) | 어떤 실제 연결과 방정식을 구현하는가? |
| 4 | [구조·설정·저장 계약](design/ARCHITECTURE.md) | 모듈과 파일을 어떻게 연결하는가? |
| 5 | [EXP-001](experiments/EXP-001-associative-learning.md) | 무엇을 입력하고 어떻게 판정하는가? |
| 6 | [구현 작업표](implementation/WORK_PACKAGES.md) | 어디부터 구현하는가? |
| 7 | [검증 명세](implementation/VALIDATION.md) | 구현·실험의 오류를 어떻게 검출하는가? |

[리서치 검토](research/REVIEW.md)는 과학적 배경, [검증 기록](records/VALIDATION_LOG.md)은 실제 수행 증거다. 처음 읽는 에이전트는 위 1~7을 읽고 I-01부터 진행할 수 있다. 명세에 나온 명령과 API는 **구현 목표**이며 현재 동작한다고 가정하지 않는다.

## 부가 문서

위 1~7번 외에 다음 문서를 함께 참고한다: architecture 수준의 결정은 [`DECISIONS.md`](DECISIONS.md), 외부 데이터 출처·라이선스는 [`RESEARCH_SOURCES.md`](RESEARCH_SOURCES.md), 기존 타격 환경 정적 진단은 [`records/PROJECT_AUDIT_2026-09-16.md`](records/PROJECT_AUDIT_2026-09-16.md). 대체된 과거 문서는 [`archive/`](archive/README.md)에 보존한다.

## 문서 관리

- 현재 규약은 문서마다 하나만 유지한다. 중복된 과거 로드맵과 초안은 `archive/`로 옮겨 보존한다(삭제하지 않음).
- 변경한 규칙·이유·영향을 PLAN의 결정 기록에 추가하고 실험 버전을 올린다. 완료된 실행의 설정·결과는 덮어쓰지 않는다.
- 문서와 구현이 다르면 차이를 먼저 기록한다. 데이터를 얻지 못하거나 검증이 실패하면 실제 상태를 보고하며 합성 자료로 본 실험을 대체하지 않는다.
- 구현 중에는 STATUS를 갱신하고 실행 명령·환경·결과 경로를 VALIDATION_LOG에 추가한다. 긴 원자료는 `runs/`에 둔다.
- 첫 실험의 선택값은 결정되어 있다. 후속 연구 단계는 새 실험 규약이 필요한 별도 범위다.


## 현재 물리 문제와 시각화

- [Claude 작업 검토](records/REVIEW_2026-09-16.md):8개 테스트 통과와 별개인 초기 관통·수동운동·구동력/사건 순서 문제.
- [ENV-001](design/ENV-001-interception.md): 다음 구현 작업 I-03b의 수치 후보와 통과 기준.
- [VIZ-001](design/VISUALIZATION.md): 실제 연결 구조와 스파이크 시각화 계획.

- [ENV-002 야구장](design/ENV-002-baseball.md): 투수 릴리스·타자 박스·파리 타자, 코스/구속/변화구 확장.

- **현재 최우선:** [역방향 스윙 검토](records/B1-BATTING-REVIEW.md) → [인필드 타구 규약](design/ENV-002-BATTED-BALL.md), I-07b-fix.

- [팔로우스루 안정화·NeuroMechFly 모델 적용](design/FOLLOWTHROUGH-AND-FLY-MODEL.md): 중앙 타격 다음 작업, I-07b-followthrough/I-08a.

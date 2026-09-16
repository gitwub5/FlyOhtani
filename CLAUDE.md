# FlyOhtani 구현 작업 안내

프로젝트 목표는 실제 초파리 연결망 기반 회로의 새로운 과제 학습과 기억을 연구하는 것이다.

## 읽는 순서

`docs/README.md`의 순서를 따른다:

1. `docs/records/STATUS.md`의 최신 상태
2. `docs/PLAN.md`의 연구 결정 (연구·환경·시각화 결정 D01~D12)
3. `docs/design/DATA_MODEL.md`의 수치·데이터 계약
4. `docs/design/ARCHITECTURE.md`의 모듈·데이터 계약
5. 해당 실험 문서: `docs/experiments/EXP-001-associative-learning.md`
6. `docs/implementation/WORK_PACKAGES.md`의 작업 단위와 완료 기준
7. `docs/implementation/VALIDATION.md`의 검증 명세

결정의 단일 기준은 `docs/PLAN.md`이며 `docs/DECISIONS.md`는 위치 안내다. `docs/archive/`의 `PROJECT_PLAN.md`·`RESEARCH_PLAN.md`·`RESEARCH_REVIEW_2026-09-16.md`는 과거 로드맵/초안이며 각각 `docs/PLAN.md`, `docs/PLAN.md`, `docs/research/REVIEW.md`로 대체되었다. `configs/default.yaml`은 읽기 경로가 없는 legacy toy 설정이며, 과학적으로 확정된 기본값으로 취급하지 않는다.

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


## 다음 작업의 주의점

현재 우선 수정은 `docs/design/ENV-001-interception.md`에 따른 I-03b다. `docs/records/REVIEW_2026-09-16.md`가 이전 ‘모든 각도에서 정지 팔 충돌’ 해석을 정정한다. 무토크와 고정 자세를 구분하고, 초기 지면/몸통 충돌을 제거한 뒤 구동력을 측정한다.

신경 실험은 EXP-001 1.0에 스케줄·점수·판정·예산까지 정해져 있다. 기존 ‘Q-05 미정’ 기록은 과거 상태다. 실제 구조와 spike 시각화는 `docs/design/VISUALIZATION.md`에 따른다. 문서 속 신규 CLI는 구현 목표이지 현재 명령이 아니다.


야구장 확장은 `docs/design/ENV-002-baseball.md`와 I-07a/b/c를 따른다. 기존 환경의 안전한 초기상태·구동/종료 기반 수정 후 B0부터 진행한다. 구장/파리의 스케일과 투구 방향이 기존 ENV-001과 다르므로 좌표·시간·actuator를 그대로 복사하지 않는다.


현재 최우선 작업은 I-07b-fix다. `docs/records/B1-BATTING-REVIEW.md`와 `docs/design/ENV-002-BATTED-BALL.md`를 먼저 읽는다. 기존 접촉9/9를 야구 타격 성공으로 취급하지 않으며, 스윙 방향·타구 추적·채점·영상 시간축을 고치기 전 B2나 RL로 진행하지 않는다.


중앙 타격 이후 최신 순서는 `docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md`를 따른다. 팔로우스루 안정화/실제 contact 파라미터 기록, NeuroMechFly 시각 자산 적용, 나머지8코스 재보정 순이다. 시각 모델 추가가 물리 관성이나 접촉을 바꾸지 않게 검증한다.

## 최신 외형 수정 인계

I-08a 완료 보고보다 `docs/records/FLY-VISUAL-REVIEW.md`의 I-08a-fix를 우선한다. 원본 자산은 확인됐으나 좌표 배치와 비율이 잘못됐다. 앞다리2개 그립·뒷다리2개 접지·중간다리 접기, 전 부위 동일 배율을 적용한다.

추가 사용자 요청: 다음 외형 작업 I-08a-style은 `docs/design/FLY-BATTING-STANCE-AND-COLOR.md`를 따른다. 옆선 타자 자세·머리 방향 분리와 원본 appearance 복원을 포함한다.

최신 통합 작업은 `docs/design/BATTING-QUALITY-AND-SWING.md`: A 자세·색상, B 거리 점수/보상, C 중앙 스윙 개선 순서다. C에서는 제어 변경에 따른 타구 개선을 검증하며 A의 불변 조건과 구분한다. RL 훈련은 진행하지 않는다.

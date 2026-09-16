# R-01 — 연구 맥락과 실행 구조 정리

2026-09-16 · Codex 검토/계획. 사용자 요청에 따라 실제 정리는 Claude가 수행한다. 이 문서만 추가했으며 기존 코드·문서는 이번 검토에서 이동/삭제하지 않았다.

## 판단과 확인 범위

개선 필요. 기능은 발전했지만 현재 규약, 과거 실패 기록, 다음 지시가 같은 파일에 누적되어 현재 상태를 찾기 어렵다. 큰 프레임워크 재작성보다 문서의 단일 기준과 실행 재현성 확보가 우선이다. 아래 수치는 현재 작업 트리 기준이며 미커밋/미추적 파일을 포함한다. HEAD c812766만으로 최신 결과를 복원할 수 없다.

### 완료 보고 재검토

- 기존 runner의 중앙 전후 episode를 직접 실행: 점수5.818990→8.479462, exit_speed8.534296→8.609497m/s, 발사각14.020748→41.213919°, 접촉 전 각변위30.738589→34.258938°. scoring_valid=true, 재접촉0. 비거리 개선은 재현되지만 광범위한 투구에 대한 강건성 증거가 아니다.
- `.venv/bin/python -m pytest tests/ -q`: 87 passed,6.52s.
- `.venv/bin/pytest tests/ -q`: 86 passed/1 failed. 접지 테스트의 `from scripts.fly_mesh_utils import geom_world_vertices`가 ModuleNotFoundError. 실행 진입점/패키지 경로 문제가 실제로 존재한다.
- `.venv/bin/ruff check envs controllers encoders train analysis demos scripts tests`: 7건. scripts3파일의4건 및 test_baseball_b1_env.py의3건. 보고한 lint clean은 현재 전체 범위에서 재현되지 않는다.
- 새 forward-carry-v1은 선택 가능하지만 기본 reward_version은 여전히 batted-ball-v1. 이전 지시의 새 보상 적용과 차이가 있으므로 현재 계약에 명시한다. 이번 순수 정리에서 기본값을 조용히 바꾸지 않는다. 다음 실험은 원하는 버전을 명시해야 한다.
- 이번 검토는 실행/소스/비교 JSON 중심이다. 최신 영상 전체의 시각 수용, ±5ms 민감도와 dt 수렴은 독립 재실행하지 않았다. 기존 보고와 독립 확인을 구분한다.

### 구조 근거

- Markdown29개, 약216,268문자. STATUS 273줄/31,287문자, VALIDATION_LOG 1,010줄/76,800문자. 줄 수보다 중복 역사와 불필요한 필독 범위가 문제다. 문자 수는 토큰 수가 아니다.
- docs/README는 아직 I-07b-fix를 현재 최우선으로 안내하고, PLAN에는 이미 끝난 I-08a-fix가 다음 작업처럼 남아 있다. root README도 최신 구현 상태를 반영하지 못한다.
- Python39개/7,302줄. B1 환경810줄, B1 테스트1,158줄, 자산 generator619줄. 길이 자체가 결함은 아니지만 물리 사건·점수·관측·렌더/진단의 책임 구분이 필요하다.
- scripts/테스트/데모가 전역 CROSSING_TIME_S를 임시 수정/복원한다. try/finally가 있어도 실행끼리 공유되는 설정은 병렬 실행과 이해를 어렵게 한다.
- 과거 B1 recorder는 삭제된 hit 키를 get(...,False)로 읽어 잘못된 요약을 조용히 낼 수 있다. ENV-001/B0의 hit는 별도 유효 계약이므로 전역 치환하지 않는다.
- pyproject는 scripts를 패키지에 포함하지 않고 자산도 assets/*.xml만 지정한다. 중첩 STL/라이선스가 wheel에 빠질 위험이 명세상 확인된다. 실제 배포 wheel 설치 검증은 R-03에서 수행한다.

## 목표와 비목표

목표: 새 에이전트가 작은 현재 문서 묶음만 읽고 현재 동작/한계/실행법/담당 파일을 파악할 수 있다. 완료 이력은 필요할 때 찾고, 보존된 설정으로 이전 결과를 재현할 수 있다.

비목표: 타이밍 민감도 개선, tilt 토크 변경, 신규8코스/변화구/학습, 알고리즘 가속, 새 기능. 성능 최적화는 측정 병목이 있는 경우 별도 작업이다. 수치 적분/사건 순서/난수 호출/제어 주기/기본 보상을 바꾸는 것은 순수 리팩토링이 아니다.

## R-00 — 정리 전 기준점 확보

1. 현재 dirty/untracked 파일 목록과 diff, 실행환경 버전, 소스·XML·자산 해시를 보존한다. 기존 변경을 reset/clean하지 않는다. 최신 구현 체크포인트와 정리 변경을 별도 커밋으로 남긴다(원격 push 불필요).
2. 중앙 before/after의 설정·qpos/qvel·사건시각·보상항 누적합·최종지표를 기준 데이터로 저장한다. 기존 결과표 reward_terms는 마지막 step 값이므로 episode 누적 보상이라고 재명명하지 않는다.
3. 알려진 실패를 목록화한다: 진입점 import, lint7건, stale recorder, 보상 기본값 차이, 타이밍 민감도, tilt 정착, 미보정8코스. 처음부터 모든 것이 통과했다고 기록하지 않는다.
4. 큰 영상은 runs에 유지하고 작은 설정/결과 요약·해시·재실행 명령은 추적 가능한 evidence로 보존한다. 로컬 runs 링크만으로 다른 에이전트가 증거를 가졌다고 간주하지 않는다.

## R-01 — 문서 우선 정리

### 목표 문서 구조

```text
docs/
  README.md                    # 1쪽 길찾기/작업별 읽기 경로
  STATUS.md                    # 현재만: 검증상태/차단점/다음작업/증거 링크
  ROADMAP.md                   # 연구목표·신경회로/야구환경의 독립 진행 단계
  architecture.md              # 현재 구현 모듈지도; 목표 구조는 명시 구분
  specs/
    baseball.md                # 현행 좌표/사건/관측/점수·reward 버전
    fly-visual.md              # 현행 자세/그립/접지/색상/자산 계약
    neural-circuit.md          # 기존 DATA_MODEL의 과학적 수치 계약
  experiments/
    EXP-001-associative-learning.md
  tasks/
    INDEX.md                   # 미착수/진행중만, 다음 읽을 문서 지정
  reference/
    sources.md                 # 출처/라이선스 연결
    validation.md              # 검증 지도; 테스트 파일과 연결
  records/
    INDEX.md                   # 완료 작업 ID→결과/교정/설정/산출물
    I-07c/...                  # 작업별 역사·근거·작은 측정 요약
    I-08a/...
  archive/
    INDEX.md                   # 폐기/대체 초안, 대체 문서 링크
```

경로는 이 구조를 기준으로 하되 독립 가치가 있는 기존 계약을 무리하게 한 파일로 합치지 않는다. calibration/asset manifest는 해당 spec 또는 자산에 인접하게 보존하고 목록화한다.

### 이동/통합 규칙

- PLAN→ROADMAP: 연구 질문과 현재 채택 결정만. 끝난 “다음 작업” 지시를 제거한다.
- STATUS는 최신 스냅샷으로 재작성. 기존 전체 내용은 작업별 records로 분리하고 최초 기록/이후 정정 관계를 보존한다. 매번 위에 새 보고서를 붙이지 않는다.
- VALIDATION_LOG는 작업별 기록으로 나누고 INDEX만 필독 경로에 둔다. 과거 오류 설명은 정정 링크와 함께 남긴다.
- ENV-002-baseball/B1-courses/BATTED-BALL/BATTING-QUALITY의 현재 규칙만 baseball spec으로 통합. 옛 접촉 보상·역방향 스윙 등은 historical로 분리한다.
- FOLLOWTHROUGH/FLY-VISUAL-REVIEW/STANCE-AND-COLOR의 현행 외형 기준은 fly-visual로 통합. 시행착오는 records로 보존한다. 기존 연구 DATA_MODEL/EXP-001의 수식·가소성·대조군·seed·검증 기준은 요약하다 잃지 않는다.
- root README는 실제 실행 입구, CLAUDE.md는 협업 규칙/읽기 경로, docs README는 지도만 담당한다. 세 파일에 상태/수치를 복제하지 않는다. DECISIONS처럼 순수 포인터는 합칠 수 있다.
- 각 규약은 id/status/version/적용범위/구현상태/대체 문서를 표시한다. current와 proposed를 구분한다. 충돌 시 무엇이 현재인지 하나의 곳에서 답해야 한다.
- 기본 필독은 CLAUDE.md + docs/README + STATUS, 합계6,000문자 내외를 목표로 한다. 이후 작업에 필요한 spec/task만 읽는다. scientific contract를 목표 글자 수에 맞추려고 축약하지 않는다. 길어진 계약은 제목/절별로 읽도록 안내한다.
- 완료 task는 records로 이동하고 결과 링크만 INDEX에 둔다. archive/records는 기본 필독/재귀 읽기 대상에서 제외하되 과거 회귀 조사 시 접근 가능해야 한다.
- 모든 경로 이동 시 내부 링크/코드 주석/실행 명령을 함께 갱신한다. 낡은 문서를 통째로 복사해 중복 현재 기준을 만들지 않는다.

## R-02 — 코드 책임 분리, 과한 재구조화 방지

첫 정리에서는 envs/controllers 등 최상위 import를 유지하고 거대한 src/ 전환을 하지 않는다. 외부 사용 entry point는 facade로 유지할 수 있다.

- envs/baseball_b1_env.py: reset/step와 substep 사건 순서의 조정 역할 유지. 독립 계산인 scoring/reward와 타입/설정부터 `envs/baseball/` 하위 모듈로 추출한다. 접촉 상태기계를 무리하게 추상 공통 엔진으로 재작성하지 않는다.
- controllers/baseball_b1.py: swing/tilt 상태기계와 oracle/observed 정책의 책임을 구분한다. 신경회로 정책과 물리 oracle을 혼동하지 않는다.
- envs/fly_visual.py: 시각 pose/IK의 명확한 경계. scripts/fly_mesh_utils의 테스트·실행 공용 계산은 설치 가능한 visual 모듈로 이동한다. runtime이 CLI 스크립트를 import하지 않게 한다.
- scripts/build_fly_visual_asset.py: import 시 파일 쓰기/argv 종료가 없는 main 함수와 입력→변환→출력 단계로 분리. 원본 리그/appearance, 단위/좌표 규칙 및 라이선스 보존. 자산을 재생성할 때 diff와 접지/그립 재검증을 남긴다.
- scripts/analysis/demos: 재사용 episode 실행·기록·카메라/영상 저장 코드를 작은 공용 runner로 모으고 CLI는 얇게 유지한다. 기존 before/after 재현 설정은 이름 있는 immutable profile로 보존한다. 단일 거대 “모든 작업 실행기”를 만들지 않는다.
- 설정 전달: 전역 CROSSING_TIME_S 덮어쓰기 대신 controller 생성자에 명시적 calibration/profile을 전달한다. 환경 기하, 컨트롤러 보정, 보상 버전은 역할이 다르다. XML과 JSON 양쪽에 같은 값의 독립 기본값을 만들지 않고 resolved snapshot을 산출한다.
- ENV-001/B0/B1은 단계별 기준선이다. 코드가 비슷하다는 이유로 하나의 if문 많은 환경으로 합치거나 삭제하지 않는다. 동일 의미가 검증된 순수 유틸리티만 공유한다.
- tests/test_baseball_b1_env.py는 physics/events/scoring/controller/visual로 분리하고 fixture는 공통화한다. 테스트의 입력·검증 의도를 없애거나 정답을 새 실행값으로 덮어써 통과시키지 않는다.

## R-03 — 실행/패키징/의존성

- import 경로 우연에 기대지 않고 editable install 및 wheel 설치 모두 지원하는 패키지 구성을 정한다. sys.path 삽입이나 PYTHONPATH 수동설정으로 실패를 숨기지 않는다.
- pytest와 python -m pytest를 동일 환경에서 모두 실행해 import 실패를 해결한다. lint 범위는 유지되는 Python 전체로 고정한다.
- wheel에 필요한 모든 XML include/STL/자산 라이선스가 포함되는지 임시 디렉터리의 비editable 설치로 실제 모델 로드를 검증한다. 검증 명령/환경을 남긴다.
- 단일 문서에 baseline/evaluation/video/asset rebuild/tests 명령을 정리하고 import/export 의존성을 갱신한다. 연구 계획상의 미구현 명령은 실제 실행 명령과 분리한다.
- 기존 B1 recorder의 hit 기반 잘못된 요약은 현행 schema로 교체하거나 legacy 전용으로 명시적으로 실행 차단한다. 미보정8코스를 조용히 실행하지 않는다. API 동작 교정은 순수 이동과 별도 커밋/검증으로 기록한다.

## R-04 — 삭제와 주석 정리 기준

| 대상 | 처리 |
| --- | --- |
| 실제 미참조 import/변수·중복 helper | 참조/진입점/동적 로드 확인 후 제거 |
| configs/default.yaml 같은 연결 안 된 초안 | 소비자·문서 확인 후 삭제 또는 역사 자료로 보존; 유효 기본 설정처럼 두지 않음 |
| train_stdp placeholder, toy SNN/MLP/encoder | 미사용이라는 이유만으로 즉시 삭제하지 않음. baseline 가치/후속 계약/공개 export 확인 후 examples/legacy로 격리하거나 삭제 근거 기록 |
| 과거 일회용 진단 스크립트 | 재현에 필요하면 명명된 experiment로 보존, 동일 결과를 새 runner가 재현하면 설정/기록을 남기고 삭제 |
| 미사용 STL | source/manifest/생성기 참조까지 확인 후에만 삭제; 라이선스/출처는 유지 |
| 코드의 긴 개발 일지·전후 수치 나열 | records로 이동하고 함수에는 현재 계약과 근거 링크만 남김 |
| 사건 우선순위·좌표/단위·물리적 이유·실패 조건 | 코드 가까이에 짧고 정확하게 유지 |
| 이전 검증 로그·실패 증거·논문/데이터 출처 | 손실 없이 기록/아카이브로 이동; 단순 토큰 절감 목적으로 삭제하지 않음 |

삭제 목록에는 기존 경로/근거/대체 경로/관련 검증을 기록한다. 생성 파일과 소스 파일을 구별한다. 기존 runs와 사용자 작업물은 정리 대상으로 일괄 삭제하지 않는다.

## 완료 기준/검증 순서

1. 문서만 이동/통합→링크와 현재 기준 일치 확인. 새 에이전트가 필독3개와 야구 spec만으로 기본 reward, 현재 유효 코스, 알려진 한계, 재현 명령을 찾을 수 있어야 한다.
2. 작은 책임별 추출마다 관련 회귀, 최종 전체87개 기존 시나리오+필요한 import/packaging 검증. 테스트 파일 분리 후 개수만 같다고 충분하다고 보지 않는다.
3. 동일 backend/버전/설정/제어 일정에서 qpos/qvel·사건순서·접촉시각·착지·점수·누적 보상·난수 결과가 보존됨을 before/after 비교. 기존 수치 허용오차를 느슨하게 하지 않는다. 원래 알려진 민감도/정착 미충족도 상태표에서 사라지면 안 된다.
4. 대표 중앙 before/after와 miss, timeout, 두 reward 버전, 부적격 착지 등을 검증한다. 시각 경로/asset 변경 시 준비·접촉·정착 이미지 및 접지/그립을 점검한다.
5. 전체 lint 통과, 두 pytest 진입점 통과, clean wheel 모델 로드 통과. 새 러너가 last-step reward와 episode return을 명확히 구분한다.
6. 폴더 지도, 이동/삭제 매핑, 기본 읽기 문자 수 전후, 검증 명령/결과, 남은 기술부채를 짧게 보고한다. 정확한 토큰 수는 tokenizer를 특정해 측정한 경우에만 표현한다.

## 완료 후 다음 실험 (이번에는 구현하지 않음)

우선 타이밍 ±5ms 취약성을 별도 실험으로 다룬다. 단일 중앙 고정 투구의 점수 향상과 넓은 성공 시간창을 구분하고, 강건성 기준을 먼저 정한 뒤8코스/학습으로 나아간다. 실제 신경회로의 EXP-001 계획은 야구 환경 정리와 별도 트랙으로 보존한다.

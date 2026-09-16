# 검증 기록 — 색인

R-01 문서 정리(`docs/implementation/REFACTOR-PLAN.md`)로 이 파일은 색인만 남기고
전체 22개 항목을 `docs/records/validation/`으로 옮겼다. 예전 위치를 가리키던
코드 주석·다른 문서의 `docs/records/VALIDATION_LOG.md` 링크는 그대로 유효하며
(파일 경로는 바뀌지 않았다), 실제 실행 명령·수치·원인 설명은 아래 표의 개별
파일에 있다. 내용은 옮기며 잃지 않았고 정정 관계도 보존했다 — 예를 들어
[I-08a](validation/20260916-i-08a.md)의 외형은 이후
[I-08a-fix](validation/20260916-i-08a-fix.md)가 좌표 버그를 정정했다는 관계가
각 파일 안에 그대로 남아 있다.

날짜순 최신이 위. 현재 유효 여부는 [STATUS](STATUS.md)를 따른다 — 이 색인은
"무엇을 언제 실행했는가"의 기록이며 "지금도 유효한가"의 판정이 아니다.

| 날짜 | 작업 | 한줄 결과 | 파일 |
| --- | --- | --- | --- |
| 09-16 | I-08a-style + I-07c-score + I-07c-swing | 옆선 자세·원본 색상 적용, 비거리 점수(`forward-carry-v1`) 추가, 스윙 windup 개선(carry 5.82→8.48m, +46%) — mid_mid만, 87 passed | [파일](validation/20260916-i-08a-style.md) |
| 09-16 | I-08a-fix | 외형 좌표 버그(로컬/월드 z 상쇄 누락, geom origin≠mesh surface) 수정, 뒷다리2접지/앞다리2그립/중간다리 접기로 자세 재정의, 앞다리 3배 확대 제거 — 64 passed | [파일](validation/20260916-i-08a-fix.md) |
| 09-16 | I-08a | NeuroMechFly(flygym==1.2.1) mesh를 시각 전용 레이어로 도입 — 이후 I-08a-fix가 좌표 버그를 발견 | [파일](validation/20260916-i-08a.md) |
| 09-16 | I-07b-followthrough | 접촉 후 반복 토크 반전을 prepare/accelerate/brake/hold 상태기계로 안정화, ball-bat solref 실측값(0.0051,0.505)으로 XML 주석 정정 | [파일](validation/20260916-i-07b-followthrough.md) |
| 09-16 | I-07b-fix | 스윙 방향 반전(prep=1.0→-1.9), 접촉-only 판정을 phase 상태기계(batted_ball 추적)로 교체, gear 12→30 재보정, `batted-ball-v1` 보상 확정 — mid_mid만, 54 passed | [파일](validation/20260916-i-07b-fix.md) |
| 09-16 | Codex 타격 방향 독립 진단 | c812766 기준 9코스 재생: 접촉점/공 vx 전부 음수(포수 방향) — I-07b-fix 착수 근거 | [파일](validation/20260916-codex-swing-direction-diagnosis.md) |
| 09-16 | I-07b B1 | 틸트 힌지(2번째 조준축, gear=6)와 9코스 구현, oracle 9/9·scripted 5/9 도달 — 53 passed | [파일](validation/20260916-i-07b.md) |
| 09-16 | I-07a-1 | 접촉창 수렴 dt=0.00025 채택, `b0-contact-v1` 보상 확정, MLB 공식 PDF와 구장 대조(오차 2건 수정) — 38 passed | [파일](validation/20260916-i-07a-1.md) |
| 09-16 | I-07a | ENV-002 B0(야구장·고정 직구) 구현, gear=12 재보정, armature 결함 발견(ENV-001도 수정) — 35 passed | [파일](validation/20260916-i-07a.md) |
| 09-16 | I-03b | ENV-001 기반 오류(초기 관통·구동·사건 순서) 수정, gear=0.08 재보정, T10 포함 22개 테스트로 전면 교체 | [파일](validation/20260916-i-03b.md) |
| 09-16 | ENV-002 계획 연결 확인 | MLB 공식 자료 대조, 문서 링크 24개 무결성 확인 — 문서만 수정 | [파일](validation/20260916-env002-plan-link-check.md) |
| 09-16 | 문서 정합성 확인 | 상대 링크 23개 무결성, EXP-001/ENV-001/VIZ-001/I-01~I-06/T01~T10 참조 대조 | [파일](validation/20260916-doc-reorg-consistency-check.md) |
| 09-16 | Codex 독립 검토 | e2447bb 기준 8 passed 재확인, reset 직후 관통 재현(ground -0.1449m, thorax -0.0567m) | [파일](validation/20260916-codex-independent-review.md) |
| 09-16 | I-03 follow-up | 팔 정지 자세를 "타자처럼" 변경 시도 — 목표점이 팔 도달반경 안에 항상 있는 기하학적 한계를 발견, 임의로 고치지 않고 대기 | [파일](validation/20260916-i-03-followup-rest-position.md) |
| 09-16 | I-03 physics defect fixes | 초기 물리 결함 8건 수정(중력 보정, damping 제거 등), `test_fly_batter_env.py`(7개) 신규 — 이후 scripted/none/random 전부 hit_rate 100%인 과제 난이도 문제 발견 | [파일](validation/20260916-i-03-physics-fixes.md) |
| 09-16 | I-01 | 프로젝트 전용 venv(Python 3.11.5) 구성, 첫 실제 MuJoCo 런타임 실행 확인 | [파일](validation/20260916-i-01.md) |
| 09-16 | Planning structure review | SHA-256 지문 비교로 문서 정리 전후 코드 무변경 확인, 링크 15개 검사 | [파일](validation/20260916-planning-structure-review.md) |
| 09-15–16 | Planning review | Python 19개 파일 `ast.parse` 문법 검사(런타임 미검증) | [파일](validation/20260915_16-planning-review.md) |
| 09-15 | 초기 스모크 검사 | compileall/pyproject 파싱/XML 구문/의존성 존재 여부 확인(4건 통합) | [파일](validation/20260915-initial-checks.md) |

## 재현 명령(현재 진입점)

```bash
.venv/bin/python -m pytest tests/ -q   # 87 passed (docs/records/evidence/R00-*, R03-* 참고)
.venv/bin/pytest tests/ -q             # 동일 87 passed (R-02/R-03에서 통일)
.venv/bin/ruff check envs controllers encoders train analysis demos scripts tests
```

`docs/records/evidence/`에는 R-01 문서 정리 자체의 근거(전/후 수치 동일성,
lint 결과, wheel 설치 확인)가 있다. 위 표의 각 항목은 그 항목이 실행되던
시점의 명령·수치이며 이후 변경으로 무효화된 값도 정정 없이 원문 그대로
보존했다(예: I-07b의 접촉-only 판정은 I-07b-fix가 대체).

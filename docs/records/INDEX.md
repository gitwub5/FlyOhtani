# 완료 작업 색인

R-01 문서 정리(`docs/implementation/REFACTOR-PLAN.md`)로 추가. 완료된 작업
ID → 결과 요약 → 근거 문서로 찾는다. 실행 명령·수치 자체는
[검증 기록 색인](VALIDATION_LOG.md)을, 지금 유효한 규칙은
[STATUS](STATUS.md)와 각 spec(`docs/design/`)을 본다. 이 색인은 "언제 무엇을
완료 보고했는가"의 지도이며, 그 보고가 여전히 유효한지는 STATUS가 최종 기준이다.

| 작업 ID | 내용 | 결과 | 근거 |
| --- | --- | --- | --- |
| I-01 | 실행환경 확정 | venv(Python 3.11.5) 구성, 첫 MuJoCo 런타임 실행 | [검증](validation/20260916-i-01.md) |
| I-03 | ENV-001 최초 물리 결함 수정 | 8건 수정, 이후 baseline 전부 hit_rate 100%인 난이도 문제 발견 | [검증](validation/20260916-i-03-physics-fixes.md), [follow-up](validation/20260916-i-03-followup-rest-position.md) |
| I-03b | ENV-001 기반 오류 재수정(T10) | 초기 관통·구동·사건 순서 결함 수정, 시험 시드(n=100) 기준 충족 | [검증](validation/20260916-i-03b.md) |
| I-07a | ENV-002 B0 구현 | 야구장·고정 직구, gear=12, armature 결함 발견(ENV-001도 수정) | [검증](validation/20260916-i-07a.md) |
| I-07a-1 | B0 수용 검토 | dt=0.00025 채택, `b0-contact-v1` 확정, 공식 PDF 대조(오차 2건 수정) | [검증](validation/20260916-i-07a-1.md) |
| I-07b | B1 조준·9코스 구현 | 틸트 축(gear=6), 9코스 좌표, oracle 9/9·scripted 5/9 도달(접촉-only 판정, 이후 대체됨) | [검증](validation/20260916-i-07b.md) |
| I-07b-fix | 스윙 방향·타구 판정 수정 | prep_swing 1.0→-1.9, phase 상태기계(batted_ball 추적), gear 12→30, `batted-ball-v1` 확정 — mid_mid만 | [검토](B1-BATTING-REVIEW.md), [검증](validation/20260916-i-07b-fix.md) |
| I-07b-followthrough | 팔로우스루 안정화 | 접촉 후 토크 반복 반전 제거(상태기계 도입), 접촉 재료 solref 실측값 정정 | [검증](validation/20260916-i-07b-followthrough.md) |
| I-08a | NeuroMechFly 시각 모델 도입 | flygym==1.2.1 메시 vendoring, 물리 불변성 확인 — 외형 좌표 버그로 수정 필요 판명 | [검증](validation/20260916-i-08a.md) |
| I-08a-fix | 외형 좌표 버그 수정 | 부모 world offset 상쇄, geom origin→mesh surface 측정, 2접지/2그립/2접기 재정의 | [검토](FLY-VISUAL-REVIEW.md), [검증](validation/20260916-i-08a-fix.md) |
| I-08a-style + I-07c-score + I-07c-swing | 옆선 자세·색상, 거리 점수, 스윙 개선 | 원본 색상 적용, `forward-carry-v1` 추가, carry 5.82→8.48m(+46%) | [검증](validation/20260916-i-08a-style.md) |
| R-01/R-02/R-03 | 문서·코드·패키징 정리 | 문서 통합(baseball/fly-visual spec), B1 course/reward 코드 분리, pytest 진입점 불일치·lint 7건·wheel 자산 누락 수정 | `docs/implementation/REFACTOR-PLAN.md`, `docs/records/evidence/` |
| KC-01a | 몸통-배트 협응 최소 역학 모델 | 고정 기반 실제 관성 torso_yaw 추가(B1은 별도 모델로 보존). 잠정 비교(`KC-01a-COMPARISON.md`)는 dt 미수렴으로 후속 정정됨 | [설계](../design/KC-01a-TORSO-BAT-COORDINATION.md), [잠정 비교(정정됨)](KC-01a-COMPARISON.md) |
| KC-01a-validation | dt 수렴·정착·에너지·타이밍 보완 | 4개 조건 중 1개만 dt 수렴(그마저 유효 타구 실패), `staggered`의 "최고 성적"은 정밀 dt에서 무효로 뒤집힘, 정착 3/4 확인, 에너지 잔차 대부분 관절한계 반력으로 설명. 후속: 발산 원인이 접촉 계산(구동 아님)임을 직접 확인, `simultaneous`/`staggered`의 torso-swing 역회전(상쇄) 발견 → 부호를 맞춘 새 조건이 dt 수렴 통과. 추가 후속: 그 조건의 "10ms 몸통 선행"은 반작용 결합 때문에 raw qvel 기준 실제 선행이 0초임을 확인, motion-triggered handoff 모드로 225ms 진짜 선행 조건(torso_target=0.5)을 찾았으나 이후 방향 불일치·팔 변위 사실상 0·양 축 관절범위 이탈로 무효 판정 후 철회, 유효성 검사(방향/변위/범위)를 컨트롤러에 추가해 재탐색한 새 후보(torso_target=0.25)는 검사·정착·그립은 통과하지만 dt 수렴에는 실패 — 협응 우위 결론은 여전히 보류 | [검증 결과](KC-01a-VALIDATION.md), [방향 계약](../design/KC-01a-DIRECTION-CONTRACT.md) |
| VISION-01 | 눈 카메라 기반 공 추정 입력 계약 설계 | 입력/금지 채널, clock/지연, 관측 schema, oracle 대비표, 수용 기준 제안 — 코드 없음, 통합은 물리 수렴 후로 보류 | [설계](../design/VISION-01.md) |

완료로 표시됐다가 이후 검토에서 정정된 항목(예: I-07b의 "접촉 9/9"는
I-07b-fix가 실제 타격 성공이 아니었음을 밝힘)은 원래 기록을 지우지 않고 이
표와 각 검증 파일에 정정 관계를 남긴다.

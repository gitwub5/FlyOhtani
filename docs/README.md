# 문서 안내

문서는 아래 표의 13개다(이 안내까지 14개 파일). 늘리기 전에 기존 문서에 들어갈 자리가 없는지 먼저 본다.

| 문서 | 역할 | 언제 읽나 |
| --- | --- | --- |
| [PLAN.md](PLAN.md) | **결정의 단일 기준.** 연구 질문, 설계 결정(D01~D24), Phase와 게이트, 리스크 | 항상 먼저 |
| [records/STATUS.md](records/STATUS.md) | **지금** 무엇이 검증됐고 무엇이 막혀 있는지만 | 작업 시작 전 |
| [records/PRIOR-FINDINGS.md](records/PRIOR-FINDINGS.md) | v1에서 확정된 사실과 반복하면 안 되는 실패 | 몸·접촉·시각 작업 전 |
| [records/G1-FORELEG-SWING.md](records/G1-FORELEG-SWING.md) | G1 보고: 앞다리·배트·모델 사실 | 몸·접촉 작업 전 |
| [records/G4-CONNECTOME-ACCESS.md](records/G4-CONNECTOME-ACCESS.md) | G4 보고: MaleCNS 루밍 회로 | 뇌 작업 전 |
| [records/BATTER-SCENE.md](records/BATTER-SCENE.md) | 직립 타자 장면, 야구 축척 규칙, 파리 눈, 충돌 짧은 확인 | 장면·몸·눈 작업 전 |
| [records/G2-CONTACT.md](records/G2-CONTACT.md) | G2 사전 등록·v1 실패·v2 통과, 선택된 접촉 파라미터 | 접촉·dt 작업 전 |
| [records/LIT-01-FLY-LEG-LIMITS.md](records/LIT-01-FLY-LEG-LIMITS.md) | 실제 파리 다리의 속도·힘 상한과 그 출처 | 속도·힘 수치를 쓸 때 |
| [records/VM-01-EYE-RATE.md](records/VM-01-EYE-RATE.md) | 눈 프레임률·투구 가시성 측정(v1 FAIL)과 거기서 나온 설계 제약 | 눈·투구·커리큘럼 작업 전 |
| [records/BRAIN-CIRCUIT.md](records/BRAIN-CIRCUIT.md) | 망막→LIF 회로→트리거 첫 구현, 셔플 대조군 통과 사실 | 뇌·정책 작업 전 |
| [records/LEARNING-01.md](records/LEARNING-01.md) | 첫 학습 실행: 훈련은 됐고 일반화는 실패 | 학습·보상 작업 전 |
| [RESEARCH_SOURCES.md](RESEARCH_SOURCES.md) | 외부 데이터·코드의 출처·버전·라이선스 | 외부 자산을 반입할 때 |
| [records/VALIDATION_LOG.md](records/VALIDATION_LOG.md) | 실행한 명령과 그 결과의 색인 | 결과를 남길 때 |

## 규칙

- **PLAN과 STATUS의 역할을 섞지 않는다.** 결정은 PLAN, 현재 상태는 STATUS,
  실행 근거는 VALIDATION_LOG.
- 완료된 작업의 "다음 지시"를 문서에 쌓지 않는다 — v1에서 이미 끝난 일이
  최신 작업처럼 보이는 문제를 만들었다.
- 테스트 통과와 연구 가설의 검증을 구분해 쓴다.
- 실패·무효 결과를 지우지 않는다.

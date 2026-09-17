# FlyOhtani

실제 초파리 크기의 몸과 실제 연결망에서 유도한 회로로, 눈에 보이는 공을
배트로 쳐내는 것을 학습시키는 연구용 시뮬레이션.

```
눈 카메라 → 망막 인코딩 → [커넥톰 유래 루밍 회로] → 앞다리 운동 명령
                                  ↑                          ↓
                            보상 조절 신호 ←──── 타구 결과(접촉/방향/비거리)
```

**현재 Phase 0 완료.** 몸·세계·뇌·과제·뷰어는 아직 구현되지 않았다.
지금 동작하는 것은 시각 감지/추적 계층과 단위 규약뿐이다.
[계획](docs/PLAN.md) · [현재 상태](docs/records/STATUS.md)

## 이 저장소가 주장하지 않는 것

- 연결망을 넣었다는 이유로 실제 뇌를 재현했다고 주장하지 않는다.
  실제 연결 데이터 + **가정한** 뉴런 동역학 + **가정한** 가소성이다.
- 수작업/RL 컨트롤러는 **환경 기준선**이다. 실제 회로의 우위 주장은
  셔플 배선·고정 회로 대조군을 갖춘 뒤에만 한다.
- 현재 저장소에 커넥톰 데이터는 **없다**. 반입 시 출처·버전·체크섬·
  라이선스를 [RESEARCH_SOURCES](docs/RESEARCH_SOURCES.md)에 기록한다.

## 구조

| 경로 | 내용 | 상태 |
| --- | --- | --- |
| `flyohtani/units.py` | 단위 규약(mm·g·μN), 원본 모델 실측 상수 | 있음 |
| `flyohtani/sense/` | 눈 카메라, 공 검출, 시간 추적, 관측 스키마 | 있음(Phase 3에서 재검증) |
| `flyohtani/assets/` | NeuroMechFly STL 메시 + 라이선스 + provenance | 있음 |
| `flyohtani/body/` | 앞다리 실제 관절 + 배트 | Phase 1 |
| `flyohtani/world/` | 축소 구장, 투구 런처, 접촉 | Phase 2 |
| `flyohtani/brain/` | 커넥톰 로더, LIF 회로, 가소성 | Phase 4 |
| `flyohtani/task/` | Gym env, 보상 버전 | Phase 5 |
| `flyohtani/record/`, `viewer/` | 에피소드 번들, 4분할 재생 | Phase 6 |

## 설치와 실행

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest          # 20 passed
.venv/bin/ruff check .
```

## 이전 버전

사람 크기 구장 + 3축 강체 배트 + 인간식 스윙 협응 탐색으로 진행하던 v1
전체(코드·문서·원자료)는 git 태그 **`archive/human-scale-v0`** 에 보존돼
있다. 거기서 확정된 사실과 반복하면 안 되는 실패는
[선행 발견 요약](docs/records/PRIOR-FINDINGS.md)에 압축해 두었다.

## 라이선스

프로젝트 코드는 MIT. 반입한 서드파티 자산의 별도 라이선스는
[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)에 있다 — NeuroMechFly 메시는
Apache-2.0이며, 향후 커넥톰 데이터는 원 데이터 라이선스를 그대로 따른다.

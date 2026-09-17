# FlyOhtani

실제 초파리 크기의 몸과 실제 연결망에서 유도한 회로로, 눈에 보이는 공을
배트로 쳐내는 것을 학습시키는 연구용 시뮬레이션.

```
눈 카메라 → 망막 인코딩 → [커넥톰 유래 루밍 회로] → 앞다리 운동 명령
                                  ↑                          ↓
                            보상 조절 신호 ←──── 타구 결과(접촉/방향/비거리)
```

**현재 Phase 1 진행 중.** 게이트 G1(앞다리 스윙)과 G4(커넥톰 접근)를
통과했다. 세계·과제·뷰어는 아직 없다.
[계획](docs/PLAN.md) · [현재 상태](docs/records/STATUS.md)

## 이 저장소가 주장하지 않는 것

- 연결망을 넣었다는 이유로 실제 뇌를 재현했다고 주장하지 않는다.
  실제 연결 데이터 + **가정한** 뉴런 동역학 + **가정한** 가소성이다.
- 수작업/RL 컨트롤러는 **환경 기준선**이다. 실제 회로의 우위 주장은
  셔플 배선·고정 회로 대조군을 갖춘 뒤에만 한다.
- 커넥톰 **배선**은 들어와 있지만(MaleCNS v1.0, CC-BY) 그 회로가 루밍에
  어떻게 반응하는지는 전혀 확인하지 않았다. 배선을 받은 것과 기능을 검증한
  것은 다르다.

## 구조

| 경로 | 내용 | 상태 |
| --- | --- | --- |
| `flyohtani/units.py` | 단위 규약(mm·g·μN), 원본 모델 실측 상수 | 있음 |
| `flyohtani/sense/` | 눈 카메라, 공 검출, 시간 추적, 관측 스키마 | 있음(Phase 3에서 재검증) |
| `flyohtani/assets/` | NeuroMechFly STL 메시 + 라이선스 + provenance | 있음 |
| `flyohtani/body/` | 원본 MJCF에서 빌드한 실제 앞다리 관절 + 배트, G1 스윕 | 있음 |
| `flyohtani/brain/connectome.py` | MaleCNS 루밍 부분회로(311→12 뉴런) 로더 | 있음 |
| `flyohtani/world/` | 축소 구장, 투구 런처, 접촉 | Phase 2 |
| `flyohtani/brain/` (LIF·가소성) | 회로 시뮬레이션, 운동 디코딩 | Phase 4 |
| `flyohtani/task/` | Gym env, 보상 버전 | Phase 5 |
| `flyohtani/record/`, `viewer/` | 에피소드 번들, 4분할 재생 | Phase 6 |

## 설치와 실행

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest          # 54 passed
.venv/bin/ruff check .
```

## 이전 버전

사람 크기 구장 + 3축 강체 배트 + 인간식 스윙 협응 탐색으로 진행하던 v1
전체(코드·문서·원자료)는 git 태그 **`archive/human-scale-v0`** 에 보존돼
있다. 거기서 확정된 사실과 반복하면 안 되는 실패는
[선행 발견 요약](docs/records/PRIOR-FINDINGS.md)에 압축해 두었다.

## 뇌 시각화 뷰어

`viewer/`의 3D 뇌 뷰어는 fly-connectome-template을 가져와 수정한 것이다.

Built with [fly-connectome-template](https://github.com/cobanov/fly-connectome-template) by [Mert Cobanov](https://github.com/cobanov).

이 부분은 **Cobanov Template Attribution License 1.0**([viewer/LICENSE](viewer/LICENSE))을
따르며, 위 표시를 README와 뷰어 화면에서 지워서는 안 된다. 무엇을 바꿨는지는
[viewer/MODIFICATIONS.md](viewer/MODIFICATIONS.md), 출처는
[viewer/PROVENANCE.json](viewer/PROVENANCE.json).

## 라이선스

프로젝트 코드는 MIT. 단 `viewer/`는 위의 템플릿 라이선스를 따른다. 반입한 서드파티
자산의 별도 라이선스는 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)에 있다 — NeuroMechFly 메시는
Apache-2.0이며, 향후 커넥톰 데이터는 원 데이터 라이선스를 그대로 따른다.

# G4 — MaleCNS 루밍 회로를 실제로 받을 수 있는가

2026-09-17 · 게이트 G4([PLAN](../PLAN.md) Phase 4, D19) · 구현:
`flyohtani/brain/connectome.py` · 파생 데이터:
`flyohtani/assets/connectome/looming-subgraph-male-cns-v1.0.json` ·
회귀: `tests/test_brain_connectome.py`

## 판정: PASS — 접근·라이선스·회로 실재·실제 연결까지 확인

D19가 가정이 아니라 데이터로 뒷받침된다. 부분회로는 이미 저장소에 들어와 있고
1 GB 원본 없이 로드된다.

## 1. 접근과 라이선스

| 항목 | 확인 결과 |
| --- | --- |
| 데이터셋 | MaleCNS **v1.0** |
| 라이선스 | **CC-BY** — 상업적 이용 허용, 저작자 표시 필요 |
| 배포처 | <https://male-cns.janelia.org/download/> (인증 불필요, 공개 GCS) |
| 협력 기관 | FlyEM (HHMI Janelia), University of Cambridge (Dept. of Zoology), MRC LMB, Google Research |

받은 파일:

| 파일 | 크기 | SHA-256 |
| --- | --- | --- |
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 14,483,314 B | `2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2` |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 1,051,241,946 B | `e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1` |

규모: 주석 **211,577 뉴런**, 연결 **151,856,684 간선**(스키마
`body_pre / body_post / weight`). neuPrint API(`neuprint-python`)도 있으나
오프라인 재현성을 위해 파일 배포본을 썼다.

## 2. 루밍 뉴런이 실재하는가 — 가정하지 않고 조회

문헌에서 익숙한 타입 이름이 이 데이터셋에 있다고 가정하지 않고 주석 테이블을
직접 조회했다:

| type | n | superclass |
| --- | --- | --- |
| LPLC2 | 185 | visual_projection |
| LPLC1 | 134 | visual_projection |
| LC11 | 143 | visual_projection |
| **LC4** | **126** | visual_projection |
| LC6 | 124 | visual_projection |
| LPLC4 | 97 | visual_projection |
| DNp01 / DNp02 / DNp03 / DNp04 / DNp06 / DNp11 | 각 2 | descending_neuron |

`DNp01`의 instance 이름은 `DNp01(GF)_R` / `_L` — **Giant Fiber**다.
`visual_projection` superclass는 총 9,201개, 그 중 LC/LPLC 계열 4,835개다.

## 3. 실제 연결 — LC4/LPLC2 → 하강뉴런

선택 규칙: 전시냅스가 source type이고 후시냅스가 target type인 **모든** 간선.
임계값·재가중·중복제거 없음.

| pre | post | 시냅스 합 | 간선 수 |
| --- | --- | --- | --- |
| LC4 | DNp04 | 11,597 | 126 |
| LC4 | DNp01 (GF) | 6,362 | 126 |
| LC4 | DNp11 | 3,666 | 122 |
| LC4 | DNp02 | 4,209 | 125 |
| LC4 | DNp03 | 2,507 | 126 |
| LC4 | DNp06 | 1,152 | 125 |
| LPLC2 | DNp01 (GF) | 4,862 | 185 |
| LPLC2 | DNp04 | 3,398 | 185 |
| LPLC2 | DNp06 | 1,719 | 179 |
| LPLC2 | DNp11 | 71 | 39 |
| LPLC2 | DNp02 | 5 | 4 |
| LPLC2 | DNp03 | 1 | 1 |

**부분회로 규모: 전시냅스 311 뉴런 → 후시냅스 12 뉴런, 간선 1,343, 총 시냅스
39,549.** NumPy로 축약 없이 직접 시뮬레이션 가능한 크기다 — 축약을 정당화할
필요가 없다는 것이 D19에서 이 회로를 고른 이유 중 하나다.

구조적으로 LC4는 6개 DN 전부에 고루 투사하고, LPLC2는 DNp01/DNp04/DNp06에
선택적으로 투사한다(DNp02/DNp03로는 사실상 0). LPLC2→Giant Fiber는 문헌의
표준 루밍-탈출 경로이며, 그것이 데이터에 그대로 나타난다.

> 참고로 LC4/LPLC2의 **전체** 하류는 270,629 간선이다. 위 12개 DN은 그 중
> 일부만 본 것이며, PVLP111·PVLP011·AMMC-A1 등 다른 강한 표적이 있다. 이번
> 선택은 "운동 출력으로 나가는 경로"로 좁힌 것이고, 그 범위를 넓히는 것은
> Phase 4의 모델링 결정이다.

## 4. 저장소에 들어온 것

`flyohtani/assets/connectome/looming-subgraph-male-cns-v1.0.json` (49 KB):
간선 1,343개 + 노드 323개의 type/somaSide + **provenance 블록**.

라이선스 고지를 파일 자체에 넣었다 — CC-BY 파생물은 원 라이선스를 유지하므로,
문서에만 적어두면 파일을 복사하는 순간 표시가 끊긴다. 회귀 테스트가 이
블록의 존재와 내용을 강제한다.

`weight`는 **공표된 시냅스 개수 그대로**다. 재가중·임계·정규화하지 않았다 —
시냅스 수를 시냅스 강도로 바꾸는 것은 모델링 가정이며, 그 가정을 하는 모듈에
속하지 데이터 파일에 속하지 않는다. 테스트가 이 라벨도 강제한다.

## 5. 아직 하지 않은 것

- LC4/LPLC2의 **입력**(망막→LC 경로)은 받지 않았다. Phase 3의 망막 인코딩이
  LC 층에 무엇을 주입할지는 미결정이다.
- 신경전달물질 예측(`body-neurotransmitters` 42 MB)은 받지 않았다 — 흥분성/
  억제성 부호를 정하려면 필요하다. Phase 4 결정.
- 형태/좌표(SWC skeleton)는 받지 않았다. 뷰어의 연결도는 2열 배치이며 실제
  3D 뇌 좌표가 아니라고 표시한다(Phase 6).
- **이 회로가 루밍에 어떻게 반응하는지는 전혀 확인하지 않았다.** 배선을
  받은 것과 기능을 검증한 것은 다르다.

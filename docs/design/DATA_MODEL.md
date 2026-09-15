# 데이터와 수치 모델 계약

EXP-001 1.0 · 아래 수치·필터는 계산 실험의 설계값이다. 생체에서 측정한 매개변수로 인용하지 않는다.

## 1. 데이터 획득과 고정

[MaleCNS 공식 다운로드](https://male-cns.janelia.org/download/)의 v1.0 / minconf-0.5 파일을 쓴다. 데이터 조건은 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)이다. 출처·저자 인용·가공 내용을 원자료 manifest와 파생 회로에 보존한다.

공통 URL: `https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/`

| 파일명 | 용도 | 대략적 크기 |
| --- | --- | --- |
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | ID와 type | 13 MB |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 연결별 접점 수 | 1.1 GB |

신경전달물질·형태·개별 시냅스 좌표 파일은 첫 모델에 필요 없다. 양의 KC 입력은 이 모델의 명시적 가정이다. 예측 전달물질을 검증한 결과로 기록하지 않는다.

기대 열: annotations의 `bodyId`, `type`; weights의 `body_pre`, `body_post`, `weight`. 열 이름은 [공개 importer](https://github.com/nftechie/stonkfly/blob/78ef3e05ab0fa086032098558d893667068944a0/stonkfly/neural/connectome.py)에서 대조했으나 공식 데이터 파일을 직접 읽어 확인하지는 않았다. I-03은 실제 schema를 먼저 검사한다. 불일치 시 원 열과 변경 내용을 기록하는 명시적 변환을 추가한다. 위치로 열을 추측하거나 실패를 빈 회로로 대체하지 않는다.

다운로드는 `.part`에 하고 완료 후 SHA-256·바이트 수·URL·UTC 시각·HTTP metadata를 `data/raw/malecns-v1.0/manifest.json`에 기록한다. 공식 체크섬을 확보하면 비교하고, 없으면 `checksum_origin=local_first_download`로 표시한다. 최초 로컬 해시는 독립적인 진위 검증이 아니다. 이후에는 그 해시에 고정한다. 대형 연결 파일은 Arrow batch로 순회하며 필요한 연결만 수집한다.

## 2. 회로 추출: mcns-kc-mbon11-v1

1. type의 앞뒤 공백만 제거한다. 중복 bodyId, 결측 ID, 정수가 아닌 ID는 오류다. type 결측 행은 선택에서 제외하고 수를 기록한다.
2. 출력 집합 J: `type == "MBON11"`. 입력 후보: `type.startswith("KC")`. 대소문자나 숫자를 임의 보정하지 않는다. 출력 유형이 없으면 관측한 MBON type 목록과 함께 `data_invalid`로 중단하고 타입 매핑을 검토한다.
3. 양의 정수 접점 수를 가진 KC→J 연결만 남긴다. 중복 (pre,post)는 합산한다. 음수·비정수·비유한 weight는 오류, 0은 제거하고 개수를 기록한다.
4. 남은 연결의 KC들만 I에 포함한다. 모든 ID는 정수로 정렬하고 별도 0-based index로 매핑한다. JSON에서는 ID를 10진 문자열로 저장한다.
5. N=|I|≥20, |J|≥1, 각 j의 입력 합>0이어야 한다. 양쪽 반구는 존재하는 그대로 포함한다. 반구 사이 인공 연결은 만들지 않는다.
6. 선택 밖의 입력·재귀 연결·MBON 출력·DAN 뉴런은 생략한다. 잘라낸 회로의 활동은 전체 뇌의 활동으로 해석하지 않는다. MBON11과의 연결을 선택했다고 개별 접점의 구획 위치를 확인한 것은 아니다.

파생 파일: `data/derived/mcns-kc-mbon11-v1/{neurons.csv,edges.npz,manifest.json}`. neurons는 id/index/role/type, edges는 pre_index/post_index/contact_count 배열. 원본 해시, 필터 문자열, N/J/간선 수/접점 합, 중복 합산·제외 수, 파생 파일 해시와 추출 소스 해시를 manifest에 기록한다. 행 정렬은 (post_index, pre_index). 임의의 고정 뉴런 수를 맞추려고 자르지 않는다.

## 3. 구조와 학습 상태

접점 수 C_ij에서 `P_ij=C_ij / sum_i(C_ij)`를 **각 MBON별로** 만든다. C와 P는 실행 내내 고정이다. 학습 가능한 무차원 효능 a_ij는 존재하는 간선에만 두며 초기값 1, 범위 [0.1,1]. 유효 연결은 P_ij a_ij. 정규화·효능·전류 변환은 생물학적 측정이 아닌 모델링 가정이다. 학습 후 P나 유효 연결을 재정규화하지 않는다.

KC는 적분하지 않고 입력 스파이크 s_i∈{0,1}로 구동한다. MBON 전압 v는 무차원, 휴지/리셋0, 역치1이다. 도파민 신호 d∈{0,1}은 모든 선택 간선에 같은 외부 조절 값으로 준다. 실제 DAN의 발화율·해부학적 투사 맵이라고 부르지 않는다.

| 값 | 기본값 |
| --- | --- |
| 신경 dt | 0.001 s |
| 막 시간상수 tau_m | 0.020 s |
| 입력 trace tau_s | 0.010 s |
| 불응기 | 0.002 s |
| 입력 전달 지연 | 0.001 s |
| 전류 gain G | 100 |
| 가소성 활동 trace tau_e | 0.100 s |
| 가소성 rate eta | 0.5 /s |

## 4. 한 tick의 정확한 순서

시각 t=k·dt. 입력/조절 일정은 반열린 구간 [start,end)로 판단한다. 초기 v,x,e,지연 큐,불응기 카운터는 0이다. s(k)는 t에 발생한 KC 스파이크이며 지연 큐를 통과한 b(k)=s(k-1)이 현재 도착한다.

1. `x_i ← exp(-dt/tau_s) x_i + b_i(k)`.
2. `e_i ← exp(-dt/tau_e) e_i + b_i(k)`.
3. `I_j = G sum_i(P_ij a_ij x_i)`; 이 tick의 갱신 전 a를 사용한다.
4. 불응기가 남은 j는 v=0으로 두고 카운터를 1 줄인다. 그 외 `v_j ← I_j + (v_j-I_j) exp(-dt/tau_m)`.
5. v≥1이면 t+dt에 spike를 기록하고 v=0, 불응기 카운터=2로 둔다. 한 tick 한 spike만 허용.
6. 훈련 구간에서만 `a_ij ← clip(a_ij exp(-eta·d(k)·min(e_i,1)·dt),0.1,1)`.
7. 새 입력 s(k)를 다음 tick 큐에 넣고 시각을 dt 증가시킨다.

이산화된 입력 전류를 tick 내 상수로 두는 적분법이다. e의 clipping도 설계 선택이다. MBON 발화에 의존하는 STDP는 아니며 `dopamine_gated_depression`이라고 이름 짓는다. d=0이면 a는 정확히 불변; 자체 회복·homeostasis·장기 decay는 없다. 장기 기억 유지가 보이면 이 비감쇠 가정에 따른 결과임을 보고한다.

## 5. 상태와 정밀도

float64, CPU, 고정된 정렬·합산 순서 사용. 느린 상태=a; 빠른 상태=v/x/불응기/지연 큐; 학습 trace=e. 입력 집합·P·readout은 구조 상태. RNG별 상태와 tick은 실행 상태다. checkpoint는 전부 저장하되 probe 초기화는 구조와 선택한 a만 가져와 나머지를 0으로 한다.

단독 신경 모듈은 입력 스파이크와 d만 받는다. CS 정답/평가 점수/미래 보상은 받지 않는다. 약속한 범위 밖 상태 변경·NaN·Inf는 `numerical_invalid`로 즉시 종료하고 마지막 유효 checkpoint를 보존한다.

# VIZ-001 — 실제 연결 구조와 스파이크 활동 보기

2026-09-16 · 사용자 요청 · 구현 계획. 신경 모델과 분석 결과를 이해하고 오류를 찾는 관찰 도구다. 시각화 유무가 시뮬레이션 결과를 바꾸면 안 된다.

## V-01 실제 연결망 구조

첫 대상은 MaleCNS v1.0에서 추출한 KC→MBON11 회로다. 실제 body ID와 C_ij 접점 수를 읽는다. 기본 화면은 KC 집합과 MBON 집합의 2열 연결도, 유형·선택 회로 크기·원본 버전·생략한 회로 범위를 표시한다. 선택한 뉴런의 실제 ID/type/연결 대상/접점 수와 모델 P/a/P·a를 각각 볼 수 있게 한다.

- 기본은 유형별 집계. 상세는 선택한 MBON과 그 입력, 표시 간선 최대200개(접점 수 내림차순, 동률 ID순). 전체 연결 수와 생략 수를 항상 표시한다. 필터는 표시만 바꾸고 모델은 그대로 둔다.
- 시냅스 접점 수(C), 모델 기본 연결(P), 학습 효능(a)는 다른 선택 항목이다. 선 굵기가 어떤 값을 나타내는지 범례에 명시한다.
- 2열 배치는 **연결도**이며 실제 뇌 속 공간 좌표가 아니다. 외부에서 넣는 KC 스파이크와 조절 신호는 입력 기호로 표시한다. 생략한 DAN을 시뮬레이션 중인 뉴런처럼 그리지 않는다.
- 원본·파생 데이터 manifest와 ID를 결과에 연결한다. synthetic fixture에는 ‘합성 검증 데이터’, toy SNN에는 ‘임의 연결’ 표시. 실제 연결 데이터를 쓴 화면과 구분한다.

## V-02 스파이크와 막전압

공유 시간축에서 자극 A/B, 조절 신호 d, KC 입력 raster, MBON 출력 raster, 선택 MBON의 막전압·역치, 집단 발화율, 선택 연결의 a 변화를 보여준다.

- 가로축 초(s), 세로축 neuron ID. KC는 **주입한 입력 스파이크**, MBON은 **모델이 생성한 스파이크**라고 구분한다.
- 스파이크 저장 최소 열: run_id, seed, condition, branch, phase, trial_id, tick, neuron_id, origin(`injected`/`simulated`). 물리 시각은 tick·dt에서 복원한다.
- 상태 trace: 같은 식별자 + tick + v/threshold + 선택 a; 기본 모든 MBON v는 tick마다 기록, 효능은 trial 경계 전체와 선택32간선의10ms 기록. 선택 간선은 ID순 첫32개로 고정한다.
- 발화율은 기본50ms 반열린 bin, `count/(bin_duration·neuron_count)` Hz/neuron. 마지막 짧은 bin은 실제 길이를 사용한다. smoothing 기본 off. 시드·trial 경계를 넘어 평균하지 않는다.
- 녹화/HTML의30fps 화면 갱신은 신경1ms 적분과 별개다. frame interval 내 spike는 모두 집계하고 프레임 하나에 사건이 여러 개면 개수를 표시한다. 보기 위해 spike를 다시 발생시키지 않는다.

## V-03 학습 전후와 기억 개입

같은 seed의 W0/W1/가중치 복원/이식 probe를 나란히 비교한다. 축·색 범위·시간창을 고정하고 각각의 trial 수·분모를 표시한다. 가소성 꺼짐·unpaired 비교군도 같은 방식으로 표시한다. ‘학습 성공’ 애니메이션 대신 저장된 실험 판정과 근거를 표시한다. 반응이 달라도 score 통과인지 별도로 표시한다.

## 출력 순서와 구현 경계

1. 필수: `analysis/`에서 저장 파일만 읽어 SVG/PNG/PDF raster·회로도·효능 변화·요약표를 만든다. 기존 Matplotlib을 우선 사용한다.
2. 다음: 동일 export JSON을 읽는 로컬 HTML viewer. 재생/일시정지/시간 이동/ID 선택/조건 비교를 제공한다. 외부 서버나 웹 프레임워크는 필수 아님. frame playback은 난수·시뮬레이터에 접근하지 않는다.
3. 후속: 실제 3D 뇌 배치. 공식 skeleton/좌표를 **동일 snapshot**에서 취득하고 ID·좌표계·단위·등록 변환을 확인한 뒤 구현한다. 현재 모델에는 좌표가 없으므로 가상의 점 배치를 해부학적3D 뇌로 표현하지 않는다. 전체 뇌는 별도 범위이며 첫 회로도와 혼동하지 않는다.

필수 산출물: `artifacts/connectivity.svg`, `raster.svg`, `learning.svg`, `visualization_manifest.json`. HTML을 만들면 `viewer.html`과 재생 데이터 묶음도 저장한다. manifest는 source run/graph/checkpoint 해시, 표시한 ID/간선 목록, sampling/bin/색 범위, 파일 해시를 기록한다.

## 통과 기준

- 작은 fixture에서 source별 spike 총수와 raster/bin 합이 정확히 같다. 입력과 출력 origin이 섞이지 않는다.
- 그래프의 표시 ID/간선/접점 수가 파생 파일과 정확히 일치한다. 숨긴 간선의 개수가 맞는다.
- 같은 run을 다시 그리면 그림에 사용한 수치·표시 선택이 동일하다. 애니메이션 on/off로 원 run 해시는 불변이다.
- W0/W1·probe 분기를 바꿔도 다른 run의 데이터가 섞이지 않는다. 읽기 실패·기록 없음은 ‘자료 없음’으로 표시한다.
- 전뇌를 보여주는 듯한 기본 이미지로 실제 부분회로 규모를 과장하지 않는다.


## 야구장 리플레이 연동

[ENV-002](ENV-002-baseball.md)의 투구/접촉/타구 시각에 신경 raster를 동기화한다. 구장 전체·포수 뒤·타자 측면·파리 시점, 실제/무충돌 기준 궤적, 스트라이크존/코스별 heatmap을 제공한다. debug overlay는 정책용 vision 화면에서 제외한다.

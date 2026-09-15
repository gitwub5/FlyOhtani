# 초파리 뇌 시뮬레이션: 문헌과 최근 데모 검토

조사: 2026-09-15~16, 한국 시간. 사용자가 제시한 Stonkfly, Doom/Smash Bros., Minecraft, NeuroMechFly 기반 시뮬레이션, FLM을 원본 프로젝트 설명과 대조했다. 외부 모델은 실행하지 않았다. 후속 명세 작업에서 공개 importer 소스 일부를 읽었으나 연결망 데이터는 내려받지 않았다.

## 1. 연구 목표와 핵심 구분

사용자가 선택한 목표는 **실제 초파리 신경회로가 새로운 과제를 배우는지 연구하는 것**이다. 계산 실험에서 직접 검증할 수 있는 대상은 실제 연결망을 바탕으로 만들고, 뉴런 동역학과 가소성 가정을 더한 모델이다. 이 모델의 학습과 살아 있는 초파리의 학습은 별도의 검증 수준이다.

| 표현 | 필요한 증거 |
| --- | --- |
| 실제 배선 사용 | 데이터 출처·버전·뉴런/연결 매핑 |
| 감각에 반응 | 입력 제거·입력 섞기 대조군과 신경 반응 차이 |
| 과제 수행 | 미리 정한 성공 기준과 반복 평가 |
| 경험으로 학습 | 훈련 전후 개선, 미경험 조건, 학습 중단 대조군 |
| 회로 내부에 기억 | 일시적 활동을 초기화한 뒤 유지, 학습 가중치 복원 시 효과 소실 |
| 생물학적 설명 | 실제 신경·행동 실험과의 대응 및 개입 예측 검증 |

## 2. 사용자가 제시한 프로젝트의 확인 결과

### Stonkfly

공식 저장소는 MaleCNS의 166,700개 노드와 약 2,558만 유향 연결을 이용한다고 설명한다. 가격 차트의 픽셀이 입력이고, 고정된 신경 출력 해석기가 매수·매도·관망을 제안한다. 양·음의 손익은 각각 PAM11과 PPL101 도파민 세포에 인공 자극을 준다. **양쪽 모두 도파민 관련 신호이며, ‘도파민 대 혐오’라는 단순 구분은 부정확하다.** 수익성 있는 학습은 입증하지 못했다고 명시한다. [공식 README](https://github.com/nftechie/stonkfly)

모델 문서는 7,835개 KC→MBON 연결에 후보 가소성 규칙을 적용한다고 밝힌다. KC는 버섯체의 Kenyon cell, MBON은 버섯체 출력 뉴런이다. 규칙은 Huang 등의 연구를 확장한 것이지만, 해당 구획·데이터에 적용한 확장은 미검증이라고 설명한다. 최근 행동과 손익의 인과관계, 입력 표현, 고정 출력 해석기의 편향이 남는다. **가져올 것은 검증 규약이며, 거래 학습 성공 사례로 인용하면 안 된다.** [모델·증거 문서](https://github.com/nftechie/stonkfly/blob/main/docs/model.md)

이 프로젝트를 가리키는 공개 자료의 개발자 표기는 Alex Wormuth / `nftechie`다. 사용자가 적은 Alex Wermer-Colan과 동일 인물이라고 판단하지 않는다.

### DOOMFLY

공식 README는 MaleCNS와 Doom을 연결하고 일부 KC→MBON 연결을 갱신하는 실험이라고 설명한다. 조사 시점의 **v6 후보는 시각·조건화·생존 검증 기준을 통과하지 못했으며, 생존 학습이 입증되지 않았다**고 명시되어 있다. 가중치 변화나 긴 한 판만으로 학습을 주장하지 않는 점이 중요하다. 이 실패를 모든 초파리 모델의 학습 불가능성으로 일반화할 수는 없다. [공식 저장소](https://github.com/nftechie/doomfly)

### Super Smash Bros.

사용자 제공 Threads 페이지와 기사에서 연결된 원 X 게시물에 접근하지 못했다. 검색으로 공개 코드·학습 로그·대조군을 확인하지 못했으므로, ‘하루 학습’과 승률을 검증된 결과로 사용하지 않는다. 미확인은 허위 판정이 아니다. [사용자가 제공한 기사](https://www.aitimes.com/news/articleView.html?idxno=215207)

### Minecraft — NeuroCraft Fly

기사 속 Evan Smith의 프로젝트는 `evnsnclr/neurocraft-fly-public`으로 확인했다. 모델 활동을 사람이 선택한 출력 뉴런군에서 읽어 미리 만든 행동 프로그램을 선택·조절한다. 조사 시점 저장소는 소개·영상·배포 계획 중심이며, 실행 가능한 모드와 소스는 준비 중이다. 이름이 비슷한 다른 Minecraft 프로젝트와 혼동하지 않는다. [공식 프로젝트](https://github.com/evnsnclr/neurocraft-fly-public)

### NeuroMechFly 기반 — Fly Arena

제공된 GeekNews 링크의 대상은 `artem-x-meta/fly-arena`다. MaleCNS·MuJoCo·NeuroMechFly와 명시적인 행동 제어기를 결합한다. README는 일부 시연 영상과 두 마리 대결 모드가 연결망 없이 실행된다고 밝힌다. 연결망을 사용하는 모드도 먹이 탐색·행동 선택 등에 설계된 규칙이 포함된다. **움직이는 몸의 시연만으로 신경회로의 학습을 판단할 수 없다.** [공식 저장소](https://github.com/artem-x-meta/fly-arena)

### FLM — Fly Language Model

공식 설명은 고정된 1.2B 언어모델, 고정된 초파리 연결망, 학습한 278,528개 파라미터의 출력 어댑터를 구분한다. 토큰 임베딩이 연결망에 들어가고 어댑터가 다음 토큰 점수를 조정한다. rate equation을 사용하며, 도파민 보상이나 온라인 기억 갱신은 없다고 명시한다. **뇌 내부가 언어를 학습한 사례로 분류할 수 없다.** 결과 표는 웹에서 로드되지 않아 정량적 우열은 이번 조사에서 확인하지 않았다. [공식 설명](https://fly-language-model.vercel.app/)

## 3. 연구의 기반이 되는 1차 자료

| 자료 | 확인된 기여 | 우리 연구에 주는 의미 |
| --- | --- | --- |
| [FlyWire, Dorkenwald 등, Nature 2024](https://doi.org/10.1038/s41586-024-07558-y) | 성체 암컷 뇌 139,255개 뉴런, 약 5,450만 시냅스 지도 | 배선 자료. 전체 VNC까지 포함하는 자료로 해석하지 않음 |
| [Shiu 등, Nature 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11446845/) | 연결망·전달물질 기반 LIF 모델로 섭식·청소 회로 예측 및 일부 생물학적 검증 | 신경 반응 재현의 출발점. 새로운 과제 학습의 증명은 아님 |
| [Lappalainen 등, Nature 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11525180/) / [FlyVis](https://github.com/TuragaLab/flyvis/blob/main/readme.md) | 연결망 제약과 시각 운동 과제 최적화로 신경 반응 예측 | 좌표 기반 인코더 이후 실제 시각 경로를 연구할 때 참고 |
| [NeuroMechFly v2, Nature Methods 2024](https://www.nature.com/articles/s41592-024-02497-y) | 시각·후각·운동 피드백을 포함한 가상 몸·환경 | 뇌와 별개인 감각·운동 실험 기반 |
| [Eon 기술 설명, 2026-03-10](https://eon.systems/updates/embodied-brain-emulation) | 기존 뇌 모델과 몸을 연결한 감각운동 순환 | 기존 운동 제어기와 수작업 대응 사용. 당시 학습·가소성 대부분 미포함 |
| [FlyGM, arXiv v3, 2026-06-14](https://arxiv.org/abs/2602.17997v3) | 연결망 그래프 제어기를 강화학습에 활용하고 효율 향상 보고 | 구조 제약과 학습을 결합한 참고 연구. 조사에서는 동료심사 출판 확인 못 함 |
| [MaleCNS, Google Research 2026-09-03](https://www.research.google/blog/a-connectomics-milestone-mapping-the-complete-male-fruit-fly-brain/) | 수컷 뇌·VNC, 16.6만 개 이상 뉴런과 약 1.25억 시냅스 발표 | 뇌–운동계 연결 연구의 후보. 지도와 동작 모델을 구분 |

9월 3일 연구 발표 시점을 데이터 최초 이용 가능 시점과 동일시하지 않는다. 데이터 버전별 공개 이력은 선택한 공식 배포 기록으로 별도 고정한다.

### 학습 연구에서 추가로 읽어야 하는 두 논문

- **Handler 등, Cell 2019:** 도파민 신호와 감각 입력의 상대적 시간 순서가 버섯체 시냅스 변화·연합학습과 연결됨을 연구한다. ‘보상이면 모든 연결 강화’로 단순화하기 어렵다. [논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC9012144/)
- **Huang 등, Nature 2024:** 버섯체의 단기·장기 기억 단위와 도파민 피드백을 연구한다. 연결망과 가소성을 함께 다루는 계산 모델은 일반적인 reward-modulated STDP보다 우리 목적에 직접적인 후보다. [논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC11525173/)

현재 실행 기준은 [연구 계획](../PLAN.md)과 [EXP-001](../experiments/EXP-001-associative-learning.md)이다. EXP-001은 간소화한 인공 조건화 모델이며 두 논문의 재현이 아니다. Huang 원 모델은 여러 기억 구획을 다룬 축약 모델이고 [공식 MATLAB 구현](https://github.com/schnitzer-lab/Luo_Huang_2024_MB_model)이 공개되어 있다. 이를 개별 MaleCNS 뉴런의 스파이킹 모델과 동일시하지 않는다. 원 논문 재현과 시각 기반 공 치기로의 확장은 별도 단계다.

## 4. 데이터와 실행환경에 대한 설계 근거

- [FlyWire 지침](https://join.flywire.ai/guidelines)은 v783 공개 자료와 CC BY-NC 4.0을 명시한다. 최신 주석도 별도 스냅샷으로 기록한다.
- [MaleCNS 다운로드](https://male-cns.janelia.org/download/)를 공식 데이터 진입점으로 확인했다. 실제 선택할 파일의 버전·체크섬·라이선스 문구는 도입 전에 기록한다.
- [Eon 구현](https://github.com/eonsystemspbc/fly-brain)은 기본 GPL-2.0-or-later, 원 Shiu 자료는 별도 MIT라고 안내한다. 데이터 조건과 코드 조건을 분리한다.
- [FlyGym migration](https://neuromechfly.org/migration/)에 따르면 2026년 4월의 2.x API는 Gymnasium 준수를 중단했다. 구버전은 `flygym-gymnasium`으로 이동했다. 논문 이름의 NeuroMechFly v2와 Python 패키지 2.x를 혼동하지 않는다.
- [FlyGym 설치 안내](https://neuromechfly.org/installation/)의 Warp 가속 경로는 NVIDIA GPU를 전제로 한다. Mac의 기본 실행과 별도 Linux 가속 환경을 분리해 계획한다.

시냅스 접점 수와 뉴런 쌍을 합친 유향 간선 수는 다르다. 모든 실험에서 뉴런 수·간선 수·시냅스 수·필터·부호 규칙을 각각 기록한다.

## 5. 조사 범위의 한계

공식 논문·README·모델 문서 기반의 조사다. 전체 외부 소스 감사나 결과 재현은 수행하지 않았다. Stonkfly·DOOMFLY 등의 한계는 저자들의 공개 설명을 요약한 것이며 독립 재현 판정은 아니다. 원문 접근에 실패한 일부 Nature 페이지는 PMC 전문·공식 구현으로 보완했다. 사용자 제공 DCInside·Threads 링크는 접근하지 못했다. 이동하는 저장소의 상태는 구현 시 커밋으로 고정해야 한다.

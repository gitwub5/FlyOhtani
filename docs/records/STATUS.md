# 현재 상태

## 2026-09-16 — I-07a-1 완료: B0 접촉 수렴·보상·구장 대조 (최신)

- **선행 발견**: RK4 적분기에서 `mj_step()` 직후 `xpos`/`contact`가 접촉이 막 시작되는 순간에만 방금 갱신된 `qpos`/`time`과 어긋날 수 있음을 최소 모델로 확인(최대0.026m, dt=0.01s 예시). 두 환경의 `step()` 모두에 `mj_step()` 뒤 `mj_forward()` 호출을 추가해 상태 일관성을 보장했다. 회귀 테스트 2개 추가(양쪽 환경).
- **A. 접촉 수렴**: control_dt=0.005s 고정, physics_dt [0.0005,0.00025,0.000125,0.0000625]s 비교(시간표 재생 + 물리시각 기준 미세 onset 진단, 두 실험 분리). 접촉창의 두 경계가 dt에 따라 수렴하지만, **dt=0.0005(ENV-002 §7 원래 후보)는 앞쪽 경계에서 0.875ms 벗어나 기준(≤0.5ms)을 만족하지 못한다.** 기준을 만족하는 가장 큰 dt인 **0.00025s를 기본값으로 채택**하고 XML/env 기본 frame_skip에 반영(control_dt=0.005s 유지). 수렴 그래프·CSV·JSON: `runs/i07a1-convergence/`(gitignore, 로컬).
- **B. 보상 확정(`b0-contact-v1`)**: 검토되지 않았던 접촉속도 보너스(0.25)를 **0**으로 설정. hit=+10(최초1회)/miss=-3/시간적분 제어비용(-0.2∫u²dt)은 유지. 측정한 접촉속도는 `info`에 계속 기록되나 보상에서는 제외. 보상(mean_reward=9.940)과 접촉 성공률(hit_rate=1.000)을 분리 보고.
- **C. 구장 배치 대조**: 이번에 실제로 [MLB 공식 2025 규칙집 PDF](https://mktg.mlbstatic.com/mlb/official-information/2025-official-baseball-rules.pdf)를 가져와(`WebFetch`+`poppler`) Rule 2.02/2.04·Appendix 1/2와 직접 대조했다(이전 세션은 PDF 미확인 상태로 표준 관행값만 사용). **실제 오차 2건 발견·수정**: 투수판 크기(24in×6in 규정과 다르게 가로세로가 뒤바뀌어 부정확했음), 타자 박스의 투구방향 중심(플레이트 중심 0.2159m가 아니라 0.2m로 1.6cm 어긋남). 홈플레이트의 오각형 형상 단순화는 의도된 것으로 유지(비충돌 마커). "우타자=3루측"은 도면 자체가 아닌 일반 관례임을 명시. 전체 대조표: `docs/design/ENV-002-field-comparison.md`.
- **고정 궤적 반복의 의미 재확인**: B0의 baseline 반복(20/20, 100/100)은 동일 결정적 궤적의 **재현성 확인**이며 다양한 투구에 대한 신뢰구간으로 해석하지 않는다 — 이전 VALIDATION_LOG 항목도 이 의미로 재해석해야 함을 명시했다.
- `pytest tests/` → **38 passed**(baseball15+fly23), `ruff` 클린. baseline 재확인(dt=0.00025, 새 보상 적용): zero_torque/held_rest/random 0/20, scripted 20/20(Wilson95% 0.839-1.000). 영상 재녹화 완료.
- **남은 문제**: dt=0.0005 실패의 정확한 원인(관통 vs 기타)은 미확정(수용 여부만 판단); "우타자=3루측"은 도면으로 미검증인 관례; 홈플레이트 오각형 미구현(의도됨); B0는 결정적이라 다양한 투구 성공률은 B1부터; B1·공기역학·변화구·선구안·강화학습 훈련은 진행 안 함(지시 범위 밖).
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — B0 구현 보고에 대한 인계 검토

- `5ba3635` 소스와 검증 기록 확인: I-07a 구현·smoke 완료 보고를 확인했다.35개 테스트와4개 영상의 독립 재실행/육안 검토는 이번에 하지 않았다.
- 다음 작업은 I-07a-1: 고정 control/action 시각에서 접촉창 수렴, B0 보상 placeholder 정리, 공식 도면 배치 대조. 이후 I-07b 코스 확장.
- 시간 간격별 hit/miss 불일치의 원인은 아직 확정하지 않는다. 경계 밖 일치와 경계 위치 수렴으로 수용 여부를 판단한다.
- 구체 절차·수치 기준은 [작업표](../implementation/WORK_PACKAGES.md)의 I-07a-1에 있다. 이번 변경은 문서만이다.


## 2026-09-16 — I-07a 완료: ENV-002 B0(야구장 고정 직구) 구현 (최신)

- 신규 `envs/baseball_env.py`(`BaseballB0Env`) + `envs/assets/baseball_park.xml`: 홈플레이트/투수판/우타자 박스/파울라인 배치(ENV-002 §1 좌표계), 릴리스 마커와 정확히 일치하는 공 spawn, 고정 직구(release=(16.5,0,1.8), 목표=(0.4318,0,1.0), 수평속도35m/s), 확대된 파리 타자(지지점 고정) + 수평 스윙 배트(길이0.85m).
- **중요한 정정**: 야구장 자유낙하를 해석값과 대조하다 공의 자유관절에 `armature="0"`을 빠뜨려 `<default>`의 armature가 상속되고 있었음을 발견(유효 중력 ~1.4% 감소, ~14mm 오차). **ENV-001(`fly_batter.xml`)도 같은 결함이 있었다** — 수정 후 재측정하니 I-03b가 "정지시각 양자화 잔차"로 잘못 설명했던 오차(dt=2ms에서13% seed가0.01m 기준 초과)가 완전히 해소됐다(0% 초과, 최대0.0064m). 두 XML 모두 수정, 과거 기록은 보존하고 이 항목으로 정정.
- gear를 배트 스케일(관성 약645배)에 맞춰 재보정: [4,8,12,16] 중 **12**(0.296s, 기준0.30s) 선택, ENV-001 값(0.08) 재사용하지 않음. `docs/design/ENV-002-calibration.json`.
- held_rest를 substep(0.5ms) 단위로 정확히 고정하도록 구현(I-03b의 control-step 근사를 개선).
- physics_dt 후보(0.0005/0.00025/0.000125s) 비교: 여유 있는 타이밍에서는 접촉시각이 0.0003s 이내로 수렴하지만, **경계에 가까운 타이밍에서는 가장 미세한 해상도가 다른 hit/miss 판정을 낸다** — 기록만 하고 기본값 유지.
- **baseline 결과(개발 시드0-19, B0는 완전 결정적이라 20개 결과 동일): zero_torque 0%, held_rest 0%, random 0%, scripted 100%(Wilson95% 0.839-1.000).** ENV-002 §8의 I-07a 공학적 smoke 기준 충족. 이 배트는 수평(z축) 스윙이라 중력 토크가0 — ENV-001과 달리 zero_torque가 전혀 드리프트하지 않는다(새 발견).
- `demos/record_baseball_episode.py --mode video`로 4개 카메라(전체 구장/포수 뒤/타자 측면/파리 시점) 영상을 `runs/env002-b0-demo/video/*.mp4`(30fps, gitignore 대상, 로컬 전용)에 저장. 투구→스윙→접촉(contact_time=0.4585s, planned_arrival=0.4591s)을 재현하고 접촉 프레임을 육안 확인했다.
- `pytest tests/` → **35 passed**(신규 baseball 13개 + 기존 fly 22개, armature 수정 후 재확인). `ruff` 클린.
- **남은 문제**: 타자 박스 등 세부 배치는 공식 PDF 부록 대조 없이 표준 관행값 사용(ENV-002가 직접 명시한 수치만 검증됨); reward 가중치는 ENV-001 구조를 복사한 placeholder(검토 안 함, 명시 표시만); 경계 타이밍의 dt 민감성 미해결; B0는 결정적이라 통계적 baseline 비교는 B1부터 의미 생김; 시각 품질은 기능적 수준. B1 이상 코스, 공기역학/변화구, 강화학습 훈련은 진행하지 않음(사용자 지시).
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — I-03b 완료: ENV-001 기반 오류 수정 (T10)

- `docs/records/REVIEW_2026-09-16.md`·`docs/design/ENV-001-interception.md`·`docs/implementation/WORK_PACKAGES.md`·`docs/implementation/VALIDATION.md`를 읽고 I-03b 1~5 전체를 구현·검증했다.
- 초기 관통(지면·자기충돌) 제거: `<contact><exclude>`로 thorax-limb 연결부만 명시적 제외, 힌지 범위 `[-1.4,0.65]`로 좁힘, 준비각 0.50rad, `reset()`에 관통 시 `RuntimeError`.
- gear 재보정: 공 없이·초기접촉 0에서 준비각→정렬각(-0.264rad) 0.35초 기준으로 [0.01,0.04,0.08,0.12] 평가 → **0.08 선택**(0.01은 도달 못함, 0.04는 0.548s로 기준 초과). `docs/design/ENV-001-calibration.json`에 전체 기록.
- 목표점(0.50,0,0.52)·통과경계(0.75)·준비각을 env 생성자 속성으로 통일(하드코딩 제거).
- substep 최초 terminal에서 즉시 종료, 동일 substep 지면-우선 규칙, `passed_no_contact`를 terminated로 재분류, terminal 뒤 `step()` 오류, `planned_arrival` 기반 타이밍(zone-crossing 대체), 시간적분 제어비용으로 전면 재작성.
- **baseline 재측정 결과(시험 시드 1000-1099, n=100, 튜닝 미사용): zero_torque 0%, held_rest 0%, scripted 100%(Wilson95% 0.963-1.000), scripted-random=100pp.** ENV-001의 "첫 정비 통과" 기준을 모두 충족 — 지난 회차의 "정지 팔이 모든 각도에서 맞는다"는 결론은 REVIEW가 지적한 초기 관통 오염 때문이었음을 재확인했다.
- `pytest tests/` 22개 테스트로 전면 교체(전부 통과), `ruff` 클린. VALIDATION.md의 물리 회귀 필수 항목 8개에 각각 대응하는 테스트를 추가했다.
- **남은 문제**: 기본 dt=2ms에서 자유낙하 목표오차가 약13% seed에서 0.01m를 근소 초과(최대1.1mm, dt=1ms에서는 전부 충족 — 정지시각 양자화 잔차, RK4 오차 아님); `best_constant_angle`이 시험 시드 100%를 맞혀 ENV-001이 이미 명시한 "고정 목표점의 한계"를 재확인(새 문제 아님, 향후 규약 필요); held_rest는 10ms 간격 재고정 근사; I-02/I-04/I-05는 미착수; RL 훈련은 시작하지 않음(사용자 지시).
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — 야구장 환경 확장

- 사용자 요청으로 ENV-002를 추가: 구장·투수 릴리스·타자 박스의 파리, 고정 직구→코스→속도→변화구→선구안.
- 기본안은 야구 스케일 구장과 확대된 파리 타자. 실제 곤충 역학과 구분한다. 코스 확장 전 조준 제어·도달성을 검사한다.
- I-03b 기반 오류 수리 후 I-07a B0로 진행. 신경 조건화와 독립 개발 가능. 코드/테스트/실험은 이번 문서 변경에서 수행하지 않았다.


## 2026-09-16 — Codex 재검토·실행 명세 보완 (최신)

- I-01 환경 구성과 I-03의 중력/damping/단위 수정은 유지한다. 현 commit e2447bb에서 기존 테스트8개 재통과.
- I-03은 **부분 완료**다. +1.1rad 준비각의 지면 관통(약14.5cm), 몸통–팔 자기충돌, zero-torque 팔의 큰 움직임을 직접 확인했다. 기존 ‘정지 팔 모든 각도 충돌’·‘actuator 충분’ 결론을 정정한다. [검토](REVIEW_2026-09-16.md) 참조.
- I-03b 기본 설계를 [ENV-001](../design/ENV-001-interception.md)로 정했다. 초기 겹침 처리→구동 식별→외곽 목표/낮은 궤적→사건 순서/지표→baseline 검증 순서. 새 설계의 구현·성공률 측정은 아직 하지 않았다.
- [EXP-001](../experiments/EXP-001-associative-learning.md)을0.2→1.0으로 보완했다. 자극 일정·seed·readout·효과 기준·예산을 명시해 Q-05 대기를 해소했다. 실제 신경 데이터 취득/구현/본실험은 아직 없다.
- [VIZ-001](../design/VISUALIZATION.md)에 실제 연결도와 주입/생성 spike·학습 전후 시각화를 추가했다. 구현 전이다.
- 검증 스텁을 실제 T01~T10 명세로 교체하고 작업표·설정·호출/저장 계약·인덱스를 동기화했다.
- 이번 변경은 문서만이다. 기존 테스트와 임시 메모리 모델 진단을 실행했으며 Python/XML/YAML/의존성 파일은 수정하지 않았다.

아래는 과거 시점의 기록이다. 상충하는 ‘완료’나 원인 해석은 위 최신 검토가 우선한다.


## 2026-09-16 — I-03 후속: "타자" 시작 자세로 바꿨지만 근본 원인은 기하학적 문제 (latest)

- 사용자 요청으로 팔 정지 위치를 "타자처럼" 뒤로 젖힌 자세(`SWING_REST_ANGLE=1.1`)로 바꾸고 `ScriptedSwingController`를 새 자세에 맞게 재작성했다.
- 액추에이터가 너무 약한 게 원인일까 의심해 확인했으나, 이전 측정(-1.35에서 거의 안 움직임)은 관절이 물리적 한계(-1.4)에 눌려 있던 테스트 artifact였다. 실제로는 gear=0.01 그대로도 0.5초 안에 2.4 rad을 휩쓸 만큼 충분히 강했다 — 액추에이터는 수정하지 않았다.
- **하지만 회전각 -1.4~+1.3 rad 11개 지점을 전부 스윕해 무동작 baseline hit rate를 측정한 결과 전부 1.000이었다.** 원인: 현재 중력 보정 발사식이 고정 목표점(0.08,0,0.52)에 정확히 도달하려면 정점 높이 1.12~1.69m짜리 큰 포물선이 필요한데, 힌지-목표점 거리(~0.14m)가 팔 길이(0.58m)보다 훨씬 짧아 목표점이 팔의 도달 반경 안에 항상 들어있다. **정지 자세를 어디로 옮기든 이 기하학적 구조상 해결 안 됨을 확인했다.**
- 실제 해결에는 (a) 궤적 정점을 낮추는 `flight_time`/높이 범위 조정, (b) 목표점을 힌지에서 더 멀리 배치, (c) 팔에 자유도/도달거리 여유 추가 등 **과제 기하 설계 결정**이 필요 — 사용자/Codex 확인 대기, 임의로 바꾸지 않음.
- 테스트 8/8 통과(신규 1개 추가), lint 클린. 상세는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — I-03 완료: 기존 타격 환경 물리 결함 8개 항목 수정

- `PROJECT_AUDIT_2026-09-16.md`가 지적한 8개 항목(중력 보정, substep별 접촉 수집, 접촉점 상대속도 단위, 타이밍/보상 분리, 제어비용 명명, 보상·종료 사유 구분, 관측·baseline 비교, 렌더링 설명)을 모두 수정했다. `envs/fly_batter_env.py`를 재작성하고, `envs/assets/fly_batter.xml`(공의 `ball_free` 관절에 실려 있던 의도치 않은 damping 제거), `demos/record_episode.py`(baseline 비교용 `--controller` 플래그 추가, `None` 처리 버그 수정)도 함께 고쳤다.
- **새 테스트 스위트** `tests/test_fly_batter_env.py`(7개, 모두 통과)를 추가해 각 수정 사항을 결정적 시나리오로 재현·검증했다.
- 발사식 중력 보정만으로는 목표에 도달하지 못해 원인을 추적한 결과, XML의 `<default>` joint damping(0.02)이 공의 자유 관절에도 적용되고 있었음을 발견해 함께 수정했다(감사 목록에 없던 추가 결함).
- **새로 발견한 미해결 문제**: 수정 후 `scripted`·`none`(무동작)·`random` baseline을 동일 조건에서 50 episode씩 비교한 결과 **셋 다 hit_rate 1.000**으로 나왔다. 정지된 팔이 이미 공의 경로를 구조적으로 막고 있어, 현재 팔 배치/목표점 설계로는 제어 능력을 전혀 변별하지 못한다. 이는 물리/지표 버그가 아니라 **과제 난이도 설계 문제**이며, 임의로 고치지 않고 사용자/Codex의 결정을 기다리는 채로 `docs/implementation/WORK_PACKAGES.md`에 남겨뒀다.
- `ruff check envs/ demos/ tests/`가 클린하다(사전 존재하던 lint 이슈 5건 포함 모두 해소; 손대지 않은 `controllers/brian2_stdp_controller.py`의 3건은 범위 밖으로 남김).
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.
- 이 작업은 환경의 물리/보상/종료 로직을 수정했을 뿐, 과제 자체가 의미 있게 어려운지는 여전히 미해결이다. 학습 성능이나 생물학적 타당성은 여전히 다루지 않았다.

## 2026-09-16 — I-01 완료: 실행환경 확정과 첫 런타임 검증

- 프로젝트 전용 venv(`.venv/`, Python 3.11.5, PLAN.md D07 기준)를 만들고 core+dev 의존성을 설치했다. 기존 셸의 `python3`가 무관한 다른 프로젝트의 3.9.6 가상환경을 가리키고 있어 `pyproject.toml`의 `>=3.10` 요구조차 만족하지 못했던 상태를 대체했다.
- **이 프로젝트에서 처음으로** MuJoCo 런타임이 `envs/assets/fly_batter.xml`을 실제로 로드하고 물리 step을 실행했다(이전에는 XML 문법 검사만 통과한 상태였음). `FlyBatterEnv`의 Gymnasium reset/step 루프, scripted 컨트롤러, `demos/record_episode.py`도 처음으로 끝까지 실행됐다.
- 측정 결과(목표치 아님): scripted 컨트롤러 5 episode 중 hit 0건. `demos/record_episode.py`는 episode당 약 -2×10⁷ 규모의 보상을 냈는데, 이는 20-step 무작위 행동 테스트(-20~-25 수준)보다 훨씬 크며 `timing_error` 항의 0-나눗셈에 가까운 불안정성과 기존 P0(중력 미보정) 결함과 일치하는 크기다. 원인은 진단만 하고 수정하지 않았다(I-03 범위).
- 패키지 배포 포함 검증: wheel 빌드로 `envs/assets/fly_batter.xml`을 포함한 6개 선언 패키지가 모두 포함됨을 확인했다.
- `pytest`(0 tests, `tests/` 미존재)와 `ruff`(기존 코드에서 lint 이슈 5건, 미수정)가 정상 동작함을 확인했다.
- 정확한 설치 조합을 `requirements-lock.txt`에 고정했다. 상세 실행 증거는 `docs/records/VALIDATION_LOG.md` 참고.
- `.gitignore`를 추가해 `.venv/`, `__pycache__/`, `*.egg-info/`, 향후 `runs/`·`data/raw|derived/` 등을 git 추적에서 제외했다.
- 이 작업은 런타임이 "돌아간다"는 것만 확인한다. 물리적 정확성, 학습 성능, 보상 설계의 타당성은 검증하지 않았다 — 그 부분은 I-03/I-04/I-05의 몫이다.

## 2026-09-16 — 문서 정리: 폴더 재구성과 결정 동기화

- 사용자 요청으로 `docs/`를 정리했다. 정리 전 조사에서 `docs/PLAN.md`와 `docs/design/DATA_MODEL.md`(당일 00:30, 가장 최근 배치)가 그때까지 `docs/DECISIONS.md`·`docs/experiments/EXP-001-associative-learning.md`(0.1-draft)가 "미정"으로 표시하던 Q-01~06 중 다수를 이미 구체값(D01~D09: MaleCNS v1.0, KC→MBON11 회로 `mcns-kc-mbon11-v1`, `dopamine_gated_depression` 가소성 규칙, Python 3.11/NumPy CPU/본 평가 30 시드)으로 확정해 둔 상태였음을 발견했다. 이 확정이 CLAUDE.md·DECISIONS.md·STATUS.md·EXP-001 문서에 반영되지 않아 두 세대의 문서가 불일치 상태로 공존했다.
- 사용자에게 확인한 뒤 PLAN.md/DATA_MODEL.md를 유효한 최신 연구 결정으로 채택하고, `docs/README.md`가 이미 전제하고 있던 하위 폴더 구조(records/, design/, implementation/, research/)로 마이그레이션을 완료했다: `STATUS.md`→`records/STATUS.md`, `TEST_LOG.md`→`records/VALIDATION_LOG.md`, `ARCHITECTURE.md`→`design/ARCHITECTURE.md`, `IMPLEMENTATION_HANDOFF.md`→`implementation/WORK_PACKAGES.md`, `PROJECT_AUDIT_2026-09-16.md`→`records/PROJECT_AUDIT_2026-09-16.md`.
- 대체된 이전 세대 문서(`PROJECT_PLAN.md`, `RESEARCH_PLAN.md`, `RESEARCH_REVIEW_2026-09-16.md`)는 삭제하지 않고 `docs/archive/`로 옮겼다(이력 보존, 사유는 `docs/archive/README.md` 참고).
- `docs/DECISIONS.md`의 Q-01~06 표와 `docs/experiments/EXP-001-associative-learning.md`(0.1-draft → 0.2)를 PLAN.md/DATA_MODEL.md의 실제 결정에 맞춰 갱신했다. Q-05 중 자극 A/B 배정·시점·강도의 구체 수치와 통과 기준 숫자는 여전히 미정으로 정확히 남겨뒀다(임의 수치로 채우지 않음).
- `docs/implementation/VALIDATION.md`는 아직 통합된 내용이 없어 관련 문서 위치를 가리키는 미작성 스텁으로만 만들었다.
- 저장소에 `.git`이 없어 재구성 전 상태를 baseline commit으로 스냅샷한 뒤 이동·편집을 진행했다.
- 이 작업은 문서 재구성·상호 참조 정합성 작업이며, 코드 실행·의존성 설치·데이터 임포트·연구 실행은 하지 않았다.

## 2026-09-16 — Architecture and Claude handoff

- User confirmed the division of work: Codex handles planning and structure; Claude and the user handle implementation and tests.
- Updated the root README to the active research direction and removed the obsolete sequential PPO→SNN roadmap from the main entry point.
- Added `CLAUDE.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `IMPLEMENTATION_HANDOFF.md`, `configs/README.md`, and the draft `experiments/EXP-001-associative-learning.md`.
- Defined module responsibilities, clock/unit boundaries, fast/slow/trace state handling, independent memory probes, configuration and run records.
- Handoff work I-01/I-02 and the independent physics fixes I-03 can proceed with Claude. Dataset/model implementation and EXP-001 scientific execution depend on the listed research choices.
- Scientific paper, dataset, circuit extent, detailed parameters, evaluation thresholds, and compute budget remain pending; the draft is not an executable experiment.
- Existing Python, XML, TOML and YAML implementation/configuration are intentionally unchanged. No application tests, installs, data imports or model runs were performed in this documentation task.

## 2026-09-16 — Planning-first research

- User direction: planning before implementation; investigate whether real fruit-fly circuits can learn new tasks.
- References supplied by the user: Stonkfly, Doom/Smash Bros., Minecraft, NeuroMechFly-based demos, and FLM.
- Added a dated source audit and primary-source research review. The active proposal is `RESEARCH_PLAN.md`; the previous implementation roadmap is historical.
- Proposed sequence: select a literature-backed mushroom-body learning protocol; verify actual connectivity and neural dynamics; test conditioning, retention, and memory removal; extend to timing and then interception.
- Output-layer-only learning is a comparison condition, not the main evidence for internal circuit learning.
- Source concerns: gravity missing from launch calculation; contact checked after frame skipping; metric definitions; neural/physics timing; disconnected configuration and experiment records.
- Current shell: macOS arm64, Python 3.14.0; major runtime/learning packages absent in that interpreter. Python AST checks passed for 19 files. Runtime physics and learning remain unvalidated.
- No implementation, dependency installation, external data import, or training was performed. Documentation only.
- Pending planning choices: reference paper/protocol, dataset and circuit scope, whether whole-brain scale is essential, available hardware and budget. The older implementation next actions below are deferred.

## 2026-09-15

### Current State

- Repository scaffold exists directly at the project root.
- Python package metadata exists in `pyproject.toml`.
- Minimal MuJoCo environment exists in `envs/fly_batter_env.py`.
- MuJoCo XML asset exists in `envs/assets/fly_batter.xml`.
- Scripted swing baseline exists in `controllers/scripted.py`.
- Placeholder MLP, SNN, and Brian2 STDP controller interfaces exist.
- Retina-like and compact ball-state spike encoders exist.
- Demo, training, analysis, and config entry points exist.
- Documentation folder added to track project plan, status, test results, and research sources.

### Decisions

- Start with a deliberately simple agent: one body and one actuated swing limb.
- Use MuJoCo for contact and rigid-body physics.
- Use Gymnasium-style environment APIs for compatibility with PPO tooling.
- Treat external connectome datasets as data dependencies with separate citation and license requirements.
- Do not import FlyWire or hemibrain data until the project explicitly needs it.

### Known Limitations

- The current local environment did not have `mujoco` or `gymnasium` installed during initial validation.
- The MuJoCo environment has passed Python syntax checks and XML syntax checks, but not runtime physics validation yet.
- Scripted swing parameters are initial guesses and should be tuned after MuJoCo runtime is installed.
- The SNN and Brian2 controllers are scaffolds, not finished learning systems.

### Next Actions

1. Install runtime dependencies with `pip install -e ".[dev]"`.
2. Run `python demos/record_episode.py --episodes 3`.
3. If contact does not occur, tune:
   - ball target point
   - flight time range
   - swing hinge torque gear
   - swing trigger distance
   - limb length and collision capsule radius
4. Add first real metrics to `docs/TEST_LOG.md`.
5. Add tests once environment runtime behavior is confirmed.

# 검증 기록

## 2026-09-16 — I-07b B1: 배트 조준과 9개 코스

범위: 사용자 지시 1~5, 기준 `docs/design/ENV-002-baseball.md` §3-4. **구속 변화·변화구·강화학습 훈련은 진행하지 않았다.** 설계를 먼저 고정: `docs/design/ENV-002-B1-courses.md`(구현 전 작성, 이후 §4를 실제 시행착오로 갱신). 신규: `envs/assets/baseball_park_b1.xml`, `envs/baseball_b1_env.py`(`BaseballB1Env`), `controllers/baseball_b1.py`(`OracleAimController`/`ScriptedAimController`/`FixedPoseAlwaysSwing`), `demos/record_baseball_b1_episode.py`, `tests/test_baseball_b1_env.py`(15개). B0의 `envs/baseball_env.py`·`envs/assets/baseball_park.xml`은 **손대지 않았다**(회귀 방지, 별도 파일로 분리).

### 1. 제어 주기 유지

`BaseballB1Env` 기본값: physics_dt=0.00025s(I-07a-1에서 채택한 값), frame_skip=20 → control_dt=0.005s(B0와 동일). episode_seconds=1.2s(B0와 동일), max_steps=240으로 자동 재계산. 영상은 매 control step(0.005s)마다 프레임을 캡처해 30fps로 저장(B0와 동일 방식, 슬로모션 재생).

**검증:** `test_control_period_matches_b0`.

### 2. 배트 조준 기능 (2번째 제어축 — 틸트)

기존 수평 스윙(`bat_hinge`, world +z, gear=12, 변경 없음)에 자식 힌지 `bat_tilt_hinge`(`bat_body`의 로컬 -y축, 스윙과 함께 회전하는 프레임이라 항상 배트 길이에 수직 유지)를 추가했다. 양의 틸트=배트 끝 상승(부호 실측 확인). 관절범위 `[-0.6,0.6]`(필요 최대 ±0.41에 여유). `bat_body`가 이제 geom이 없어(`inertiafromgeom` 대상 없음) 명시적 `<inertial mass=0.001>`("손목" placeholder) 추가. 충돌 제외를 `batter_body`-`bat_tilt_body`로 갱신(배트 geom 이동).

**틸트 gear 재보정** (공 없음, 초기접촉0, physics_dt=0.00025s, 0→±0.41rad, 기준0.30s):

| gear | 도달 시각 | 판정 |
| --- | --- | --- |
| 2 | 도달 못함 | 실패 |
| 4 | 0.853s | 실패 |
| **6** | **0.287s** | **통과(선택)** |
| 8 | 0.209s | 통과 |

스윙 gear(12)는 그대로 재사용(축이 다르므로 재검증만): B0와 동일하게 중력 토크0 확인. **틸트축은 중력 토크가 0이 아니다** — swing=1.0,tilt=0에서 0.16초 방치 시 tilt=-0.212까지 처짐(배트 자중이 수평 지렛대). 대기 중 능동 유지가 필요함을 확인하고 컨트롤러에 반영(아래).

**타자 지지점**: box 안 유지 확인(위치 변경 없음, B0와 동일 좌표). **초기 관통**: 9개 코스 × 3 seed 전부 0건, 그리고 스윙 전 범위 × 틸트 전 범위(0.2rad/0.15rad 격자) 스윕에서도 지면/몸통 관통 없음을 확인(관절범위 자체가 이미 안전하게 좁혀져 있음).

**검증:** `test_reset_never_starts_from_a_penetrating_state_any_course`, `test_no_ground_or_torso_penetration_across_full_tilt_and_swing_range`, `test_batter_footing_is_inside_the_batters_box`, `test_held_pose_is_exact_on_both_axes_at_substep_resolution`, `test_zero_torque_swing_static_tilt_drifts_under_gravity`.

### 3. 9개 코스

zone 중심=(0.4318,0,1.0), 반폭(y)=0.2159m(plate 반폭), 반높이(z)=0.35m(§4 "스트라이크존 0.65~1.35m" 그대로). u>0=몸쪽(+y, 우타자 기준), v>0=높은 코스. 9개 좌표는 `docs/design/ENV-002-B1-courses.md` §1 표. **릴리스(16.5,0,1.8)·수평속도35m/s(vx=-35 고정)는 B0와 동일** — 9개 코스 전부 T=0.45909s로 동일(목표 y,z만 다름, x는 고정이므로).

**검증:** `test_nine_courses_match_the_fixed_zone_definition`, `test_release_and_horizontal_constraint_match_b0_for_every_course`(9개 코스 T 전부 동일 확인), `test_unknown_course_is_rejected`.

### 4. 학습 전 도달성 검증 — oracle vs scripted

**시행착오** (그대로 보존, 문서 §4 참고): 연속 PD(kp=25,kd=2) 실패 → 2단계 bang-bang/근접-P 실패(오버슈트) → 축별 독립 교차시각 계산 실패(스윙-틸트 관성 결합 무시, 예: out_mid에서 스윙 단독 교정 시각으로는 0.11rad 부족) → **두 축을 동시에 실제 구동한 채 코스별 트리거 시각을 직접 탐색**(성공). 격자: swing_trigger∈[0.20,0.40], tilt_trigger∈[0.05,0.45], 0.01s 간격.

**oracle(정답 코스 라벨 사용, 도달성 진단 전용) — 9/9 코스 100% hit(20/20 각각).** 이는 "이 몸이 이 코스에 도달 가능한가"의 답이며 정책 성능이 아니다. **도달 불가능한 코스는 없었다** — 관절범위/gear 재설계는 불필요.

**scripted(관측만, 코스 라벨 없음) — 9개 코스 중 5개만 hit(각 20/20 또는 0/20, 코스별로 완전히 갈림):**

| 코스 | oracle | scripted | scripted 실패 원인 |
| --- | --- | --- | --- |
| in_high | 100% | 100% | — |
| in_mid | 100% | 100% | — |
| in_low | 100% | **0%** | 선형 조준 fit + 코스 공통 평균 스윙 트리거의 근사오차 |
| mid_high | 100% | 100% | — |
| mid_mid | 100% | **0%** | 상동(가장 단순한 코스조차 평균 트리거 시각 오차로 실패) |
| mid_low | 100% | 100% | — |
| out_high | 100% | **0%** | 상동 |
| out_mid | 100% | **0%** | 상동 |
| out_low | 100% | 100% | — |

scripted가 관측 기반 9점 선형 최소제곱 fit(스윙/틸트 목표)과 틸트 부호별 평균 트리거 기울기를 쓰기 때문에, 코스별 실제 비선형성(§3 표에서 스윙 목표가 y에 정확히 선형이 아님, 틸트 교차시각이 중력 때문에 양/음 비대칭)을 완전히 못 잡아 일부 코스에서 근사오차가 접촉 허용오차(~0.06m)를 넘는다. **이는 몸/구동 한계가 아니라 관측 기반 조준 알고리즘의 정밀도 한계**이며, oracle이 9/9를 달성했으므로 명확히 구분된다.

**검증:** `test_oracle_reaches_all_nine_courses`(9개 전부), `test_scripted_controller_never_reads_course_identity`(코스 라벨을 함수 시그니처에서 받지 않음을 확인), `test_scripted_hit_rate_is_course_dependent_and_reported_per_course`.

### 5. 코스별 baseline 비교와 영상

`demos/record_baseball_b1_episode.py --mode all`, 개발 시드0-19 × 9코스(B1도 코스별로는 결정적 — 반복은 재현성 확인, 코스 간 차이가 실제 변주):

| baseline | 9개 코스 전체 hit_rate |
| --- | --- |
| zero_torque | 0/9 코스에서 0%(전부 0/20) |
| held_rest | 0/9 코스에서 0%(전부 0/20) |
| random | 0/9 코스에서 0%(전부 0/20) |
| always_swing_fixed_pose(조준 없이 항상 스윙) | 0/9 코스에서 0%(전부 0/20) — **조준 없이는 mid_mid조차 못 맞힘**, 아이밍 자체의 기여를 보여줌 |
| scripted | 5/9 코스에서 100%, 4/9 코스에서 0%(위 표) |
| oracle(진단 전용, baseline과 분리 보고) | 9/9 코스에서 100% |

원자료: `runs/env002-b1-demo/baseline_results.json`(gitignore, 로컬).

**영상**: `runs/env002-b1-demo/video/<course>/{park_wide,behind_catcher,batter_side,fly_pov}.mp4`(9개 코스 × 4카메라, scripted 컨트롤러 재현, 30fps). hit한 5개 코스는 투구→조준→접촉이, miss한 4개 코스는 투구→조준→(접촉 없이) 통과가 담겨 있다(둘 다 유효한 기록).

### 종합

`pytest tests/` → **53 passed**(B1 신규15 + 기존38). `ruff check envs/ controllers/ demos/ tests/ analysis/` → clean.

### 남은 문제

1. scripted의 선형 조준 fit은 9개 중 4개 코스에서 실패한다 — 개선(비선형 보간, 코스별 트리거) 가능하지만 이번 범위에서는 측정·보고만 하고 수정하지 않았다.
2. 왼손 타자 대칭 profile은 구현하지 않았다.
3. 스윙-틸트 두 축의 실제 관성 결합(§4의 시행착오)은 정성적으로만 확인했고, 정량적 해석(결합 계수 등)은 하지 않았다.
4. B1도 코스별로는 완전 결정적이라 baseline 반복은 재현성 확인 이상의 의미가 없다 — 코스 간 비교가 B1의 실제 변주 축이다.
5. 구속(속도) 변화, 변화구, 선구안, 강화학습 훈련은 이번 범위에서 진행하지 않았다(사용자 지시).

## 2026-09-16 — I-07a-1: B0 수용 검토 마무리 (접촉 수렴·보상·구장 대조)

범위: `docs/implementation/WORK_PACKAGES.md`의 I-07a-1 A/B/C, 기준 commit `5ba3635`. 변경: `envs/baseball_env.py`, `envs/fly_batter_env.py`(state-consistency fix 이식), `envs/assets/baseball_park.xml`(dt, 투수판 크기, 타자박스 중심), `tests/test_baseball_env.py`(+3), `tests/test_fly_batter_env.py`(+1). 신규: `analysis/env002_dt_convergence.py`, `docs/design/ENV-002-field-comparison.md`, `runs/i07a1-convergence/`(gitignore 대상: `onset_scan.csv`, `replay_schedule.csv`, `convergence.png`, `summary.json`). **B1·강화학습 훈련은 진행하지 않았다(지시 범위 밖).**

### 0. 선행 발견: mj_step() 직후 xpos/contact가 qpos/time과 어긋날 수 있음

item A를 시작하기 전, 최소 모델로 먼저 확인했다: RK4 적분기에서 `mujoco.mj_step()` 직후 `d.xpos`/`d.contact`가 **접촉이 막 시작되는 시점에만** 방금 갱신된 `d.qpos`/`d.time`과 어긋난다(그 외 구간은 정확히 일치). 최소 예시(벽에 접근하는 자유낙하 공, dt=0.01s): 접촉 시작 직후 몇 step 동안 `qpos.x`와 `xpos.x`가 최대 0.026m까지 벌어지다가 재정렬된다. `mj_step()` 뒤에 `mujoco.mj_forward()`를 한 번 더 호출하면 항상 일치했다. **두 환경의 `step()` 모두에 이 refresh를 추가했다** — 접촉 판정(`_detect_bat_contact`/`_detect_limb_contact`/`_detect_ground_contact`)과 `_ball_has_passed()`가 이제 항상 `d.time`과 같은 순간의 상태를 읽는다. 회귀 테스트: `test_state_is_self_consistent_after_every_step_not_an_rk4_substage`(양쪽 환경, 2000 substep 동안 중복 `mj_forward` 호출이 no-op임을 확인).

### A. 접촉 판정 수렴 검증

명령: `.venv/bin/python analysis/env002_dt_convergence.py` (재현 가능, `runs/i07a1-convergence/`에 원자료 저장)

**설계:** control_dt=0.005s 고정, physics_dt 후보 [0.0005, 0.00025, 0.000125, 0.0000625]s에 맞춰 frame_skip=[10,20,40,80]로만 조정(제어 주기·episode_seconds·초기상태는 불변, max_steps는 같은 식으로 재계산되어 사실상 불변). 두 실험을 분리했다:
- **A1(시간표 재생)**: 한 번(dt=0.0005) scripted controller를 실행해 control-step별 ctrl 값을 기록한 뒤, controller 재호출 없이 그 시간표를 각 dt에 그대로 재생(action clock=control_dt 고정, physics_dt만 변화).
- **A2(미세 onset 진단)**: frame_skip=1로 action clock=physics clock을 만들어, 모든 dt에서 스윙이 정확히 같은 물리시각에 시작하도록 했다(control_dt 격자 자체를 제거).

**A2 결과 — 접촉창(hit 구간)의 두 경계가 dt에 따라 수렴:**

| dt(s) | 앞쪽 경계(s) | 기준값과 차이(ms) | 뒤쪽 경계(s) | 기준값과 차이(ms) | 두 경계 모두≤0.5ms |
| --- | --- | --- | --- | --- | --- |
| 0.0005 | 0.14100000 | 0.8750 | 0.18600000 | 0.4375 | **아니오** |
| 0.00025 | 0.14175000 | 0.1250 | 0.18625000 | 0.1875 | **예** |
| 0.000125 | 0.14187500 | 0.0000 | 0.18639063 | 0.0469 | 예 |
| 0.0000625(기준) | 0.14187500 | — | 0.18643750 | — | 예 |

(기준=가장 미세한 dt=0.0000625의 경계값. 경계는 0.0625ms 해상도까지 이분법으로 정밀화.)

- 가장 미세한 두 dt(0.000125, 0.0000625) 간 경계 차이: 앞쪽0.0ms, 뒤쪽0.047ms — **둘 다 ≤0.5ms 기준 충족**.
- 경계에서1ms 이상 떨어진 모든 스캔점(0.12~0.22s, 1ms 간격)에서 4개 dt의 hit/miss가 **97/97(100%) 일치**.
- 공통 hit의 접촉시각 최대 차이: **0.5ms**(기준 충족, 경계값).
- **dt=0.0005(ENV-002 §7의 원래 후보)는 앞쪽 경계에서 0.875ms 벗어나 기준(≤0.5ms)을 만족하지 못한다.** dt=0.00025는 두 경계 모두 통과하는 가장 큰 dt다.

**A1 결과(시간표 재생, controller 재호출 없음):** 4개 dt 전부 동일 스케줄로 hit, 접촉시각 0.45806~0.45850s(스프레드0.44ms) — 수렴.

**수렴 그래프:** `runs/i07a1-convergence/convergence.png`(dt별 최소 표면간격 vs onset 시각, hit=초록/miss=빨강, 점선=정밀화된 경계). 원자료: `runs/i07a1-convergence/{onset_scan.csv,replay_schedule.csv,summary.json}`.

**결정: dt=0.00025s를 기본값으로 채택.** 근거: 위 표에서 기준을 만족하는 가장 큰 dt. `envs/assets/baseball_park.xml`의 `<option timestep>`과 `BaseballB0Env`의 기본 `frame_skip=20`(control_dt=0.005s 유지)에 반영했다. dt=0.0005는 물리적으로 불가능한 민감성이 아니라 **경계 위치 자체의 미수렴**으로 기준 미달임을 확인했다(관통/tunneling 여부는 별도로 단정하지 않음 — 요청대로 원인을 확정하지 않고 수용 여부만 판단).

**검증:** `pytest tests/` 재실행(아래 종합 참고), 기존 baseline 재확인(zero_torque/held_rest/random 0%, scripted 100%, dt 변경 후에도 동일).

### B. B0 보상 확정 — `b0-contact-v1`

`envs/baseball_env.py`의 `RewardWeights.contact_velocity`를 0.25→**0**으로 변경(검토되지 않은 채 ENV-001에서 복사했던 값). `hit_success=10`(최초1회), `miss=3`, `control_cost=0.2`(시간적분 `-0.2∫u²dt`)는 유지. 측정한 접촉속도 자체는 `info["contact_velocity_post_contact"]`에 계속 기록되며 보상에서만 빠진다.

실제 hit episode의 `reward_terms`: `{hit_success: 10.0, contact_velocity: 0.0, control_cost: -0.00065, miss: -0.0}`, 총 보상≈9.94(제어비용만 차감). **보상과 접촉 성공률을 분리해 보고**: scripted baseline hit_rate=1.000(Wilson95% 0.839-1.000)이며 mean_reward=9.940은 별도 수치다(성능 주장 아님).

**검증:** `test_b0_contact_v1_reward_definition`(가중치 값, 접촉속도 항상0, hit 시 raw 측정값은 여전히 존재).

### C. 구장 배치 대조 — 공식 PDF와 직접 대조

이전 세션은 PDF를 가져오지 못해 표준 관행값만 썼다. 이번에 `WebFetch`로 [2025 Official Baseball Rules](https://mktg.mlbstatic.com/mlb/official-information/2025-official-baseball-rules.pdf)(SHA-256 `d1860de4...`, 192페이지)를 실제로 받고, `poppler`(`pdftotext -layout`, `brew install poppler`로 설치)로 Rule 2.02(Home Base)·2.04(Pitcher's Plate)·Appendix 1/2(도면)를 직접 대조했다. 전체 대조표: `docs/design/ENV-002-field-comparison.md`.

**발견한 실제 오차 2건, 수정함:**
1. 투수판 크기가 규정(24in×6in, Rule 2.04)과 다르게 부정확했고 가로세로도 뒤바뀌어 있었다(7.09in×23.6in) → `size="0.0762 0.3048 ..."`(정확히 6in×24in)로 수정.
2. 타자 박스의 투구방향 중심이 플레이트 중심(0.2159m, Appendix 2의 "3'0"+3'0"" 대칭 분할 기준)이 아니라 0.2m로 1.6cm 어긋나 있었다 → 0.2159로 수정.

**일치 확인된 항목**: 투수판-홈 거리(60'6"=18.4404m), 플레이트 앞변 폭(17in=0.4318m), 박스 크기(4'0"×6'0"=1.2192×1.8288m), 박스-플레이트 간격(6in=0.1524m).

**의도된 단순화로 유지**: 홈플레이트를 실제 오각형(17-17-8.5-8.5-12-12) 대신 17in×17in bounding box 사각형으로 표현(비충돌 마커라 정확도에 영향 없음).

**미확정으로 명시**: "우타자 박스=3루측(+y)"은 도면 자체(좌우 대칭)가 아니라 일반적인 야구 관례에서 가져온 가정이다 — 도면으로 직접 검증되지 않음을 문서에 남겼다.

**고정 궤적 반복의 의미**: B0의 20/20 scripted hit, 100/100 dev-seed 반복(이전 회차)은 **동일 결정적 궤적의 재현성 확인**이며, 다양한 투구에 대한 신뢰구간으로 해석하지 않는다. `random` 정책의 action 난수(controller 내부 RNG)와 투구 자체의 다양성(현재 B0에는 없음)은 별개다 — `docs/records/VALIDATION_LOG.md`의 이전 baseline 표는 이 의미로 재해석해야 한다.

**검증:** `test_field_dimensions_match_official_rules_pdf`(투수판 크기·위치, 플레이트 폭, 박스 크기·중심 좌표 모두 규정값과 직접 대조).

### 종합

`pytest tests/` → **38 passed**(baseball15 + fly23, 신규 4개: state-consistency ×2, b0-reward, field-comparison — 기존 field-dimensions 테스트를 대체). `ruff check envs/ controllers/ demos/ tests/ analysis/` → clean. baseline 재확인(dt=0.00025, b0-contact-v1 보상 적용 후): zero_torque/held_rest/random 0/20, scripted 20/20(Wilson95% 0.839-1.000), mean_reward=9.940. 영상 재녹화: `runs/env002-b0-demo/video/*.mp4`(contact_time=0.45825s, planned_arrival=0.45909s).

### 남은 문제

1. dt=0.0005가 왜 기준을 못 만족하는지(관통 vs 다른 수치적 원인)는 원인을 확정하지 않았다 — 수용 여부(dt 선택)만 판단했다.
2. "우타자=3루측" 배치는 도면 자체로 검증되지 않는 관례적 가정이다.
3. 홈플레이트의 실제 오각형 형상은 구현하지 않았다(의도된 단순화, 비충돌 마커).
4. B0는 여전히 완전 결정적이라 baseline 반복은 재현성 확인 이상의 의미가 없다 — 다양한 투구에 대한 성공률은 B1부터 얻을 수 있다.
5. B1, 공기역학/변화구, 선구안, 강화학습 훈련은 이번 범위에서 진행하지 않았다.

## 2026-09-16 — I-07a: ENV-002 B0(야구장 고정 직구) 구현과 검증

범위: 사용자 지시 1~8, 기준 문서 `docs/design/ENV-002-baseball.md`·`docs/implementation/WORK_PACKAGES.md` I-07. 신규 파일: `envs/assets/baseball_park.xml`, `envs/baseball_env.py`(`BaseballB0Env`), `controllers/baseball_scripted.py`, `demos/record_baseball_episode.py`, `tests/test_baseball_env.py`(13개), `docs/design/ENV-002-calibration.json`. 변경: `envs/__init__.py`, `pyproject.toml`(`video` extra: imageio/imageio-ffmpeg), `requirements-lock.txt`. **강화학습 훈련·B1 이상 코스·변화구는 진행하지 않았다(지시 범위 밖).**

### 0. 정정: I-03b "양자화 잔차"는 실제로는 armature 버그였다

야구장의 자유낙하 오차를 실제 해석해(analytic) 비교하다가 발견: 공의 `ball_free` 관절에 `damping="0"`만 주고 `armature="0"`을 빼먹어, `<default>`의 armature(야구장 0.002, ENV-001 0.001)가 상속되고 있었다. armature는 병진 자유도에도 가상 관성을 더해 유효 중력가속도를 `mass/(mass+armature)`만큼 줄인다. 야구장에서는 이 효과가 약1.4%(≈14mm 오차)로 뚜렷하게 드러나 실제 해석값과 시뮬레이션을 직접 대조해서야 잡아낼 수 있었다. **ENV-001(`fly_batter.xml`)도 같은 결함이 있었다** — 수정 후 재측정하니 dt=2ms에서 30 seed 전부 0.01m 기준을 통과한다(수정 전 평균0.0077m/최대0.0113m/13% 초과 → 수정 후 평균0.0031m/최대0.0064m/0% 초과). **I-03b VALIDATION_LOG의 "정지시각 양자화 잔차" 설명은 부분적으로 틀렸다** — 실제로는 이 armature 버그가 주 원인이었다. 두 XML 모두 `armature="0"`을 추가했다. 과거 기록은 지우지 않고 이 항목으로 정정한다.

### 1. 구장 배치와 ENV-002 좌표계 (지시 1)

원점=홈플레이트 뒤쪽 꼭짓점, +x=투수 방향, +y=3루 방향, +z=위(ENV-002 §1). 배치: 투수판 x=18.4404m, 홈플레이트 폭0.4318m, 우타자 박스1.2192×1.8288m(3루측, +y). **주의:** MLB 공식 2025 규칙집 PDF 부록은 이번 세션에서 가져오지 않았다 — 타자 박스가 플레이트 가장자리에서6in(0.1524m) 떨어진다는 표준 관행값과 우타자=3루측 관행을 사용했으며, ENV-002가 직접 명시한 수치(투수거리·플레이트 폭·박스 크기)만 정확히 일치가 검증됐다. `docs/design/ENV-002-calibration.json`의 `field_dimensions_source`에 명시.

**검증:** `test_field_dimensions_match_env002_spec_values`(투수판 거리·플레이트 폭·박스 크기가 ENV-002 수치와 일치), `test_batter_footing_is_inside_the_batters_box`.

### 2. 확대된 파리 캐릭터·배트·스윙 (지시 2)

타자는 지지점 고정(다리 동역학 없음), 배트는 길이0.85m/반경0.025m/질량0.9kg 강체, 힌지 축은 **수직(+z, 수평 스윙)** — ENV-001의 수직평면 스윙과 기구가 다르다(ENV-002 §3, "기존 수직 평면의0.58m 팔과 같은 기구로 취급하지 않는다"). `<contact><exclude body1="batter_body" body2="bat_body"/>` 로 힌지 연결부만 제외.

### 3. 릴리스·손 마커·고정 직구 (지시 3)

B0 프리셋 그대로: release=(16.5,0,1.8)m, 목표면 x=0.4318m/중심 y=0,z=1.0m, 수평속도35m/s. `T=(16.5-0.4318)/35=0.4591s`, `v0=(target-release-0.5gT²)/T`(중력만, 공 damping/armature=0). 측정: 총 초기속도35.0037m/s, 수평속도35.0000m/s(정확히 일치, `info["launch_speed_total_m_s"]`/`launch_speed_horizontal_m_s"]`로 기록). 릴리스 마커 geom과 공의 reset() spawn 위치가 `np.array_equal`로 정확히 일치.

**검증:** `test_ball_spawn_exactly_matches_the_release_marker`, `test_gravity_only_launch_matches_analytic_ballistics_at_the_actual_stop_time`(적분오차와 정지시각 양자화를 분리 — 적분오차 하한1e-4m 이내, armature 수정 후 사실상 기계정밀도).

### 4. 새 스케일 구동 재보정 (지시 4, ENV-001 gear 재사용 안 함)

배트 관성(약0.217kg·m², ENV-001 팔의 약645배)이 훨씬 커서 gear를 처음부터 다시 스윕했다. **충돌 없는 구동 측정값** (공 없음, 초기접촉0, damping=0.05/armature=0.002 유지, physics_dt=0.0005s, 준비각1.0→정렬각-1.30rad, 기준0.30s):

| gear | 도달 시각 | 판정 |
| --- | --- | --- |
| 4 | 0.5165s | 실패 |
| 8 | 0.3635s | 실패 |
| **12** | **0.296s** | **통과(최소값 선택)** |
| 16 | (탐색값15→0.2645s, 20→0.229s 모두 통과 확인, 16 자체는 미측정) | 통과 예상 |

선택: gear=12, `envs/assets/baseball_park.xml`에 반영. 정렬각은 -1.30rad(목표점까지 최소거리1.3mm, -2.0~2.0rad을 0.01rad 간격으로 스윕). 전체 기록: `docs/design/ENV-002-calibration.json`.

**검증:** `test_scripted_hits_zero_torque_and_held_rest_do_not`(gear=12가 baked-in된 실제 XML로 재현).

### 5. held_rest를 substep 단위로 정확하게, 목표시각 오차 분리 (지시 5)

`BaseballB0Env.set_held_pose(angle)`를 추가해 `step()`의 substep 루프 안에서 **매 mj_step 직후** qpos/qvel을 강제 고정한다(이전 I-03b는 control step(10ms) 단위로만 재고정하는 근사였음). 목표시각 오차는 위 "정정" 항목대로 적분오차(armature 버그, 수정됨)와 정지시각 양자화(물리적으로 불가피, dt의 절반×속도로 상한)를 별도 assertion으로 분리했다.

**검증:** `test_held_pose_is_exact_at_physics_substep_resolution`(모든 substep에서 qpos/qvel이 1e-12 이내로 고정), `test_gravity_only_launch_matches_analytic_ballistics_at_the_actual_stop_time`.

### 6. 시간 간격 후보의 고속 접촉 수렴 검사 (지시 6)

physics_dt 후보 0.0005s(기본, control_dt=0.005s) vs 0.00025s vs 0.000125s 비교, 동일 트리거 시각으로 스윙:

| trigger(s) | dt=0.0005 | dt=0.00025 | dt=0.000125 |
| --- | --- | --- | --- |
| 0.159 | hit, t=0.45850 | hit, t=0.45825 | hit, t=0.45813 |
| 0.180 | hit, t=0.44900 | hit, t=0.44875 | **miss(passed_no_contact)** |

여유 있는 트리거(0.159)에서는 접촉시각이 세 해상도 모두 0.0003s 이내로 수렴하고 접촉을 놓치지 않는다. 그러나 **경계에 가까운 트리거(0.18)에서는 가장 미세한 해상도(dt=0.000125)가 나머지 둘과 다른 결과(hit→miss)를 낸다** — 얇은 배트·빠른 공(35m/s)의 접촉 판정이 타이밍 경계 근처에서 dt에 민감할 수 있다는 뜻이다. 이는 관통(tunneling) 버그라기보다 경계 근처의 실제 민감성으로 판단하며, 기본값(physics_dt=0.0005s/control_dt=0.005s, ENV-002 §7 후보값)을 그대로 유지하되 **경계 근처 타이밍 결과는 dt에 따라 달라질 수 있음을 기록**한다. B1+ 단계에서 더 세밀히 다룰 문제.

### 7. baseline 비교와 사건 순서 (지시 7)

`demos/record_baseball_episode.py --mode baselines`, 개발 시드0-19(**B0는 고정 투구이므로 20개 결과가 전부 동일함 — ENV-002 §8 스스로 명시한 대로 "결정적 한 궤적의100회는 독립100개 학습 증거가 아니다"**):

| baseline | hit | hit_rate | Wilson95% | end_reason |
| --- | --- | --- | --- | --- |
| zero_torque | 0/20 | 0.000 | (0.000,0.161) | passed_no_contact ×20 |
| held_rest | 0/20 | 0.000 | (0.000,0.161) | passed_no_contact ×20 |
| random | 0/20 | 0.000 | (0.000,0.161) | passed_no_contact ×20 |
| scripted | 20/20 | 1.000 | (0.839,1.000) | hit ×20 |

ENV-002 §8의 I-07a 공학적 smoke 기준(held_rest/zero_torque 접촉0, scripted 접촉≥80%)을 충족. 흥미로운 부가 발견: 이 배트는 수평(z축) 스윙이라 **중력 토크가 0** — zero_torque가 ENV-001과 달리 전혀 드리프트하지 않는다(`test_zero_torque_does_not_drift_horizontal_swing_is_not_gravity_torqued`).

초기 관통·사건 순서: `test_reset_never_starts_from_a_penetrating_state`(seed0-4, contact.dist≥-1e-6), `test_ground_contact_priority_and_first_terminal_event_stop`(동일 substep 지면-우선, 최초 terminal에서 즉시 종료 — elapsed==1 substep), `test_step_after_terminal_raises_and_no_double_reward`, `test_same_seed_reproduces_an_identical_trajectory`(재현성), `test_headless_and_render_mode_give_identical_physics`(렌더링 유무가 물리에 영향 없음), `test_observation_does_not_expose_hidden_target_or_rng`(관측이 현재 물리상태에서만 유도됨).

### 8. 영상 저장 (지시 8)

`demos/record_baseball_episode.py --mode video` → `runs/env002-b0-demo/video/{park_wide,behind_catcher,batter_side,fly_pov}.mp4`(30fps, h264, 153프레임/5.1초 — 실제 사건은 약0.46초+후속0.03초를 슬로모션으로 늘림) + `manifest.json`(seed/end_reason/contact_time/launch_speed/카메라경로/이벤트 타임라인). scripted 컨트롤러로 투구→스윙→접촉을 재현했다(contact_time=0.4585s, planned_arrival=0.4591s, signed_timing_error=-0.0006s). 접촉 프레임을 batter_side/behind_catcher에서 육안으로 확인(배트가 존 안에서 공과 겹침). `runs/`는 `.gitignore` 대상이라 커밋되지 않는다 — 로컬 경로로만 존재.

### 종합

`pytest tests/` → **35 passed**(baseball13 + fly22, armature 수정 후 재확인). `ruff check envs/ controllers/ demos/ tests/` → clean.

### 남은 문제

1. 타자 박스 등 구장 세부 배치는 ENV-002가 직접 명시한 수치만 검증했고, 표준 관행값(6in 오프셋, 우타자=3루측)은 공식 PDF 부록 대조 없이 사용했다.
2. `RewardWeights`는 ENV-001 구조를 그대로 복사한 placeholder다(ENV-002 §6 "ENV-001의 속도 보너스를 새 스케일에 검토 없이 복사하지 않는다"의 경고 대상 — 검토 안 함, 명시적으로 표시만 함).
3. 경계 근처 타이밍(트리거0.18)에서 dt=0.000125가 dt=0.0005/0.00025와 다른 hit/miss 판정을 낸다 — 수정 안 함, 기록만.
4. B0는 완전히 결정적이라 baseline n=20은 실질적으로1회 반복이다. 통계적 다양성은 B1(코스 변화)부터 의미가 생긴다.
5. 시각 품질은 기능적 수준(조명·재질 단순)이며 사실적 렌더링을 목표하지 않았다.
6. B1 이상 코스, 공기역학/변화구, 선구안, 강화학습 훈련은 이번 범위에서 진행하지 않았다(사용자 지시).

## 2026-09-16 — I-03b: ENV-001 기반 오류 수정과 검증 (T10)

범위: `docs/implementation/WORK_PACKAGES.md`의 I-03b 1~5, `docs/design/ENV-001-interception.md` 전체, `docs/implementation/VALIDATION.md`의 "물리 회귀의 필수 추가 항목" 8개. 변경 파일: `envs/fly_batter_env.py`(재작성), `envs/assets/fly_batter.xml`(관절 범위, contact exclude, gear), `controllers/scripted.py`(재작성 + `ConstantAngleController` 추가), `controllers/__init__.py`, `demos/record_episode.py`(재작성: held_pose 진단, dev/test seed 분리, Wilson CI), `tests/test_fly_batter_env.py`(22개 테스트로 전면 교체), 신규 `docs/design/ENV-001-calibration.json`.

### 1. 초기 관통·연결부 자기충돌 (ENV-001 항목1-2)

- XML에 `<contact><exclude body1="agent_body" body2="swing_limb"/></contact>` 추가. thorax-limb 연결부 겹침(REVIEW가 찾은 dist=-0.0567m)만 명시적으로 제외했고, 다른 모든 pair(공-지면, 공-팔, 공-몸통, 팔-지면)는 그대로 유지.
- 힌지 관절 범위를 `[-1.4,1.4]`→`[-1.4,0.65]`로 좁혔다(REVIEW가 찾은 +1.1rad에서의 지면 관통 -0.1449m 재발 방지).
- 준비각을 0.50rad으로 변경(ENV-001 후보값). 확인: 준비각에서 접촉 0건, 지면 여유 0.094m(요구 0.02m 이상 충족).
- `reset()`에 `_check_no_initial_penetration()`을 추가해 `contact.dist < -1e-6`이면 즉시 `RuntimeError`. 조용히 넘어가지 않는다.

**검증:** `test_reset_never_starts_from_a_penetrating_state`(seed 0-19), `test_prep_pose_has_ground_clearance_margin`, `test_no_ground_penetration_across_the_full_joint_range`(관절범위 전체 0.05rad 간격 스윕), `test_thorax_limb_connector_overlap_is_excluded_not_penetrating`(관절범위 전체) — 모두 통과.

### 2. zero_torque/held_pose/actuated 구분과 구동 재측정 (ENV-001 항목3-5)

REVIEW의 지적대로 **zero_torque는 정지 상태가 아니다** — 중력이 가벼운 팔에 토크를 가해 0.35초 만에 준비각(0.50)에서 0.60rad까지 수동으로 회전한다(측정: `test_zero_torque_held_pose_and_actuated_are_three_distinct_conditions`). held_pose는 매 control step마다 qpos/qvel을 강제로 준비각에 고정하는 별도 진단(진짜 controller 아님)으로 구현했다(`demos/record_episode.py:run_held_pose_episode`).

**충돌 없는 구동 측정값** (공 없음, thorax-limb 제외 외 다른 충돌 유지, damping=0.02/armature=0.001 유지, dt=0.002s, 준비각 0.50→정렬각 -0.264, 기준 0.35s):

| gear | 초기 접촉 | 도달 시각 | 관절한계 반발 | 판정 |
| --- | --- | --- | --- | --- |
| 0.01 | 0 | 도달 못함(1.0s 내) | 없음 | 실패 |
| 0.04 | 0 | 0.548s | 없음 | 실패(기준 초과) |
| **0.08** | 0 | **0.28s** | 없음 | **통과 (최소값 선택)** |
| 0.12 | 0 | 0.202s | 없음 | 통과 |

선택: gear=0.08(가장 작은 통과값), XML에 반영. 전체 기록: `docs/design/ENV-001-calibration.json`. 이전 gear=0.01 측정("0.5초에 2.4rad")은 REVIEW가 지적한 대로 초기 관통의 충돌 반발력이 섞인 결과였음을 재확인 — 관통을 없앤 뒤 gear=0.01은 1.0초 안에 정렬각에 전혀 도달하지 못한다.

**검증:** `test_actuator_reaches_alignment_angle_within_deadline_without_ball`(XML에 반영된 gear=0.08로 재현).

### 3. 목표점·통과 경계 설정 공유 (ENV-001 항목3)

`target=(0.50,0,0.52)`, `pass_x=target_x+0.25=0.75`, `prep_angle=0.50`을 `FlyBatterEnv` 생성자 인자 겸 인스턴스 속성으로 만들어 reset/관측(TTC)/종료판정에서 전부 공유한다. 이전의 `ZONE_X=0.08`/`0.45` 하드코딩은 제거했다. `flight_time_range`도 [0.72,0.95]→[0.40,0.50]로 ENV-001 후보값 적용.

자유낙하 목표 오차(공-팔 충돌 비활성, 15seed 평균, physics substep 단위로 정렬각 시각에 정지):

| dt | 평균 오차 | 최대 오차 | 0.01m 초과 비율(30seed) |
| --- | --- | --- | --- |
| 0.002s(기본값) | 0.0077m | 0.0113m | 13% |
| 0.001s | 0.0069m | 0.0091m | 0% |

dt를 절반으로 줄이면 오차가 악화되지 않고 개선된다(요구사항 충족). 다만 **기본 dt=0.002s에서는 일부 seed(약13%)가 0.01m 기준을 근소하게(최대 1.1mm) 초과한다** — RK4 적분 오차가 아니라 목표 도착시각 T가 physics_dt의 정수배가 아니어서 생기는 정지시점 양자화 잔차다(수정 안 함, 아래 "남은 문제" 참고).

**검증:** `test_gravity_compensated_launch_error_does_not_worsen_when_dt_halves`(15seed, dt 완화 없음 확인 + dt=1ms에서 ≤0.01m).

### 4. substep 사건 순서·종료 분류·타이밍·시간적분 비용 (ENV-001 항목4)

- `step()`의 substep 루프가 **최초 terminal 사건에서 즉시 break**하도록 재작성(이전엔 frame_skip 5회를 항상 다 돌고 사후 판정). 같은 substep에 지면접촉과 hit가 동시에 있으면 지면접촉 우선(보수적 실패 규칙).
- `end_reason ∈ {hit, ground_contact, passed_no_contact, timeout}`; hit/ground_contact/passed_no_contact는 `terminated=True`, timeout만 `truncated=True`(이전엔 passed가 truncated였음 — REVIEW 지적 반영).
- terminal 뒤 `step()` 호출은 `RuntimeError`.
- 타이밍을 재정의: 실제 zone-crossing을 기다리는 대신 `planned_arrival_s`(=reset에서 뽑은 T)를 기준으로 `signed_timing_error_s = contact_time_s - planned_arrival_s`를 계산. hit가 나면 항상 값이 존재한다(이전엔 hit가 조기 종료를 유발해 zone-crossing을 못 봐서 자주 결측이었음).
- 제어비용을 `torque² × 실제 substep 경과시간`으로 재정의(이전엔 매 control step마다 고정 action²만 사용해 control_dt에 의존).

**검증:** `test_ground_and_limb_contact_in_the_same_substep_prioritizes_ground`, `test_first_terminal_event_stops_the_substep_loop_early`(elapsed==1 substep만), `test_mid_substep_contact_within_frame_skip_is_not_missed`, `test_passed_no_contact_is_terminated_not_truncated`, `test_timeout_is_truncated_only`, `test_step_after_terminal_raises_runtime_error`, `test_no_double_hit_reward_on_repeated_contact`(재호출 시 RuntimeError 포함), `test_timing_uses_planned_arrival_and_is_always_present_on_hit`, `test_timing_error_on_a_naturally_launched_hit_not_just_teleported_ball`(순간이동 없이 scripted controller의 실제 10회 발사 중 hit 발생 확인, VALIDATION.md의 "인위적 순간이동 테스트만으로 대체 금지" 충족), `test_timing_missing_reason_when_no_contact`, `test_control_cost_invariant_to_control_dt`(physics_dt=1ms에서 control_dt 5/10/20ms 절대오차 1e-9 이내 일치), `test_point_velocity_matches_omega_cross_r_analytically`(성분별 오차 1e-8 이내).

### 5. baseline 재정의와 dev/test seed 분리 (ENV-001 항목5)

`demos/record_episode.py`에 `zero_torque`/`held_rest`/`random`/`scripted`/`best_constant_angle` 5종을 구현. `DEV_SEEDS=range(20)`(튜닝용), `TEST_SEEDS=range(1000,1100)`(튜닝 미사용, 판정용)로 분리. `RandomController`는 독립 RNG를 쓰므로 다른 controller의 환경 입력을 바꾸지 않음(`test_env_rng_is_independent_of_controller_choice`로 검증).

scripted 컨트롤러는 "남은 도달시간(관측 기반 예측) − 구동 보정시간(0.30s, gear=0.08 측정치+여유)" 트리거로 재작성. `best_constant_angle`은 개발 시드에서 각도 후보(-0.15~-0.40)를 스윕해 **-0.30rad**을 선택(20/20 hit).

**첫 정비 통과 기준 결과 — 시험 시드(1000-1099, n=100, 튜닝에 사용 안 함):**

| baseline | hit | hit_rate | Wilson95% | 기준 | 판정 |
| --- | --- | --- | --- | --- | --- |
| zero_torque | 0/100 | 0.000 | (0.000,0.037) | ≤5% | 통과 |
| held_rest | 0/100 | 0.000 | (0.000,0.037) | =0% | 통과 |
| random | 0/100 | 0.000 | (0.000,0.037) | (scripted-random≥30pp의 분모) | — |
| scripted | 100/100 | 1.000 | (0.963,1.000) | ≥80% | 통과 |
| scripted−random | — | 1.000 | — | ≥30pp | 통과 |
| best_constant_angle(-0.30) | 100/100 | 1.000 | (0.963,1.000) | (참고, 통과 기준 아님) | — |

개발 시드(0-19, n=20)에서도 동일 패턴(zero_torque/held_rest/random=0/20, scripted=20/20). **ENV-001의 모든 "첫 정비 통과" 기준을 시험 시드에서 충족했다.**

### 종합

`pytest tests/ -q` → **22 passed**. `ruff check envs/ controllers/ demos/ tests/` → clean. `docs/implementation/VALIDATION.md`의 "물리 회귀의 필수 추가 항목" 8개 전부 대응하는 테스트를 추가했다(위 절별로 매핑).

### 남은 문제 (수정 안 함, 다음 논의 필요)

1. 기본 물리 해상도(dt=0.002s)에서 자유낙하 목표 오차가 일부 seed(약13%)에서 0.01m 기준을 근소하게(최대1.1mm) 초과한다. dt=1ms에서는 전부 충족. 정지시각 양자화 잔차이며 RK4 오차가 아니다. dt를 기본값으로 낮출지, 허용오차를 조정할지는 설계 결정이 필요하다.
2. `best_constant_angle=-0.30`이 시험 시드 100/100을 전부 맞힌다 — ENV-001이 스스로 명시한 "고정 목표점의 한계"를 재확인한 것으로, 새로운 문제가 아니다. ENV-001 문서가 요구하는 대로, 이 결과를 "타이밍 학습"의 증거로 사용하려면 목표 위치/도달시간을 바꾸는 새 규약이 먼저 필요하다(수정 안 함, 범위 밖).
3. "always max torque" 정책 baseline(ENV-001의 향후 규약에서 언급)은 구현하지 않았다 — 첫 정비 통과 기준에는 불필요.
4. `held_rest`는 매 control step(10ms)마다 qpos/qvel을 재고정하는 근사 구현이다. 한 control step 안의 물리 substep 5회 동안 미세하게 드리프트할 수 있으나 관측된 hit_rate에는 영향이 없었다(0/100).
5. I-02(설정·기록 계약)는 여전히 미구현. I-04/I-05(실제 회로, EXP-001 실행)는 이번 작업과 독립이며 착수하지 않았다. 강화학습 훈련도 시작하지 않았다(사용자 지시).

## 2026-09-16 — ENV-002 계획 연결 확인

- MLB 공식 필드/릴리스 설명과 공식 링크의2025 규칙집을 참조하고, 설계용 preset과 구분했다.
- Markdown24개의 상대 링크 검사: 누락0. I-07/ENV-002/VIZ/PLAN/상태·설정 인계를 연결했다. 문서만 수정, 신규 환경 실행·학습은 하지 않았다.


## 2026-09-16 — 문서 정합성 확인

- 루트/설정/docs의 Markdown23개에서 상대 링크 검사: 누락0. archive의 이동 전 링크도 수정.
- EXP-001 1.0, ENV-001 1.0, VIZ-001, I-01~I-06과 T01~T10의 참조를 대조했다.
- Git 변경 파일 확인: 문서만 변경. 기존 소스/XML/YAML/TOML/lock에는 차이 없음. 신경 실험·새 환경 구현·시각화 실행은 수행하지 않았다.

## 2026-09-16 — Codex 독립 검토

- 기준 commit e2447bb. `.venv/bin/python -m pytest tests/test_fly_batter_env.py -q`:8 passed in0.23s.
- reset 직후 contact 검사 및 seed0/frame_skip1/zero torque 재현: ground–limb dist=-0.1449m, thorax–limb dist=-0.0567m; +1.1rad→약0.712s hit 때 -1.2466rad. 재현 절차와 한계는 [REVIEW](REVIEW_2026-09-16.md).
- in-memory 모델에서 thorax/ball collision을 제외한 actuator 분리 측정: 최대 음의 입력0.5s, q0=0→-0.03173rad, q0=0.5→0.44742rad. 원본 XML/gear는 수정하지 않았다.
- ENV 후보의 고정 준비각+0.5/목표(0.5,0,0.52)/27개 표본 궤적에서 최소 표면 여유 약0.166m. 전체 동역학/baseline 성공률 검증 아님.
- 과거 아래 기록의 ‘geometry confirmed’·‘motionless’ 해석은 최신 검토로 정정한다. 이전 측정값은 보존한다.


Record command results here so experiment state remains recoverable.

## 2026-09-16 — I-03 follow-up: "batter" rest position attempt, and why it isn't enough

User request: move the swing limb's rest position to a "batter-like" cocked-back
stance, away from the ball's path, since the baseline comparison above found a
motionless limb intercepts 100% of the time. Changed: `envs/fly_batter_env.py`
(new `SWING_REST_ANGLE = 1.1` constant, used in `reset()` instead of the old
hardcoded `-0.75`), `controllers/scripted.py` (rewritten to swing from the new
rest angle: `swing_gain=-1.0`, `reset_angle=1.0`, since decreasing the hinge
angle from +1.1 sweeps toward the interception zone).

### Investigation: was the actuator too weak to swing at all?

An initial open-loop test (sustained max torque from `qpos=-1.35` for 1.6s)
showed almost no movement, suggesting the actuator (`gear=0.01`) might be too
weak to matter. This was a testing artifact, not a real defect: `-1.35` is
right against the hinge's `range="-1.4 1.4"` limit, so the joint was pinned
against its hard stop. Repeating the same test starting at `qpos=1.2` (away
from any limit) showed the limb sweep from +1.2 to -1.2 rad in under 0.5s under
sustained torque — the actuator is not the bottleneck. No change made to
`gear`.

### Command

```bash
python -c "... sweep SWING_REST_ANGLE over 11 values from -1.4 to +1.3,
run 30 seeded episodes each with an all-zero action, measure hit rate ..."
```

### Result: every reachable rest angle still gets ~100% hit with zero action

| rest angle (rad) | motionless (`none`) hit rate over 30 episodes |
| --- | --- |
| -1.4, -1.2, -0.9, -0.6, -0.3, 0.0, 0.3, 0.6, 0.9, 1.1, 1.3 | **1.000 for all 11** |

Root cause (confirmed analytically): the gravity-compensated launch (I-03's
main fix) requires a large initial vertical velocity to land exactly on the
fixed target `(0.08, 0, 0.52)` at `t=flight_time`. For the current
`ball_z∈[0.45,0.65]` / `flight_time∈[0.72,0.95]s` ranges, computed apex height
ranges **1.12–1.69 m** — far above both the target and the swing limb's
maximum reach (hinge at `z≈0.39`, arm length `0.58` ⇒ max reach `z≈0.97`). The
hinge is only `~0.143 m` from the exact target point (`sqrt(0.06²+0.13²)`),
which is much smaller than the arm's `0.58 m` length, so the target lies well
inside the arm's full reach circle at every angle the arm can take. Combined
with the trajectory's final descent sweeping through a range of directions
relative to the hinge as it approaches the target (varying by seed), a static
arm anywhere in its ±1.4 rad range ends up crossing the ball's path.

**Conclusion:** repositioning the *rest angle* cannot by itself make the task
discriminate control skill, regardless of which angle is chosen — this is a
task/environment **geometry** issue (target-to-hinge distance vs. arm length
vs. launch-arc height), not fixable by the rest-position change alone. The
`SWING_REST_ANGLE=1.1` + rewritten `ScriptedSwingController` changes are kept
(a genuine "cocked back, must swing" starting stance, and still the literal
change requested), but do not yet resolve the underlying discrimination
problem. Candidate real fixes (not implemented, need a design decision):
narrow the launch-arc height (tighter `flight_time`/height ranges), move the
target point farther from the hinge, or give the limb more reach/DOF margin
to clear the corridor. Recorded in `docs/implementation/WORK_PACKAGES.md`.

### Command

```bash
pytest tests/ -q   # 8/8 passed (added test_reset_starts_the_limb_at_the_cocked_back_rest_angle)
ruff check envs/ controllers/ demos/ tests/   # clean (pre-existing brian2_stdp_controller.py issues untouched)
```

## 2026-09-16 — I-03 physics defect fixes and baseline comparison

Changed: `envs/fly_batter_env.py` (rewritten), `envs/assets/fly_batter.xml` (`ball_free` joint damping override), `demos/record_episode.py` (rewritten: fixes a `None`-vs-`np.nan` bug and adds `--controller {scripted,none,random,all}`), new `tests/test_fly_batter_env.py`.

### Command

```bash
pytest tests/ -v
```

### Result

Passed, 7/7. Each test targets one audited defect with a deterministic setup (white-box manipulation of `env.data`/`env.model`, not reliant on any controller's behavior):

- `test_gravity_compensated_launch_reaches_target_without_limb_interference` — with limb collision disabled (`geom_contype`/`conaffinity=0`), a zero-action flight from `ball_z=0.55` reaches within 0.05 m of the fixed target `(0.08, 0, 0.52)` at `flight_time=0.8s`, and never drops within 0.05 m of the ground. **This only passed after also fixing the XML** (see below) — the launch-velocity formula alone was not sufficient.
- `test_no_double_hit_reward_on_repeated_contact` — forcing sustained ball/limb contact confirms `hit_success` reward is granted exactly once (first control step), zero on any later step even though the two-return-value contract (`terminated=True`) means a real caller wouldn't call `step()` again.
- `test_point_velocity_is_in_m_per_s_and_scales_with_lever_arm` — with the hinge spinning at a known `omega`, `_point_velocity` at two different radii from the hinge axis returns speeds within 20% of `omega*r`, confirming it does not reproduce the old bug (summing the ball's m/s speed with the limb's raw rad/s).
- `test_ground_contact_terminates_with_distinct_end_reason` — a ball forced near the ground with downward velocity (limb collision disabled) terminates with `end_reason="ground_contact"`, `hit=False`, and a negative `miss` reward term. Previously ground contact was never checked at all.
- `test_control_cost_matches_action_squared_and_is_isolated` — a single mid-episode step with `action=0.6` yields `reward_terms["control_cost"] == -weight * 0.6**2` exactly, with `miss`/`hit_success` at 0 (confirms no cross-contamination from removing the timing-based term).
- `test_timing_error_missing_reason_when_no_contact` — with limb collision disabled, a full episode (ends via ground/pass/timeout) reports `timing_error=None`, `timing_error_missing_reason="no_contact"`.
- `test_timing_error_defined_after_hit_when_zone_crossing_detected` — a two-phase setup (cross `ZONE_X` with limb disabled, then re-enable and force contact at the recorded limb position) confirms `timing_error` is a finite `>=0` value once both a zone-crossing and a hit are recorded.

### Finding: gravity-compensated launch formula alone was insufficient

The `<default><joint damping="0.02".../></default>` block in `envs/assets/fly_batter.xml` cascaded onto the ball's own `ball_free` joint (`model.dof_damping` was `[0.02]*7`, all 7 DOFs including the ball's 6 free-joint DOFs), applying artificial viscous drag to a body that should fly freely under gravity alone. With this damping present, `test_gravity_compensated_launch_reaches_target...` failed by ~0.12 m even with the correct ballistic-compensation formula. Fixed by adding `damping="0"` directly on the `ball_free` joint (overriding the class default, which is evidently meant for the actuated `swing_hinge`, not the ball). After this, the same test passes with <0.05 m error. This was not in the original P0/P1 audit list — discovered while verifying the gravity fix.

### Command

```bash
python demos/record_episode.py --controller all --episodes 50 --seed 0
```

### Result (measured, not a target)

All three baselines — `scripted`, `none` (always zero torque), and `random` (uniform random action each step) — score **hit_rate=1.000 across 50/50 episodes each**, under matched reset conditions (same seed sequence, same observation/action interface via `--controller all`). `end_reasons` is uniformly `{"hit": 50}` for all three.

**This is a new finding, not previously documented**: before the gravity fix, hit_rate was 0/5 for `scripted` because the ball crashed into the ground before reaching the swing zone (I-01's measured -2×10⁷ reward blowup). After the gravity fix, the ball reliably reaches the fixed target point `(0.08, 0, 0.52)`, but the swing limb's geometry at its *rest* angle (`-0.75` rad, unmoving) already occupies enough of the airspace between the ball's approach corridor and the target that it intercepts the ball regardless of control input. Measured static-geometry check: the closest point on the rest-position limb capsule to the exact target point is ~0.158 m away (capsule radius + ball radius = 0.063 m contact threshold), so contact isn't happening exactly *at* the target — it's happening somewhere along the ball's parabolic approach path, which the 0.58 m-long capsule spans a wide enough arc to intercept.

**Consequence:** the environment currently cannot discriminate control/timing skill — a motionless arm "solves" it as reliably as any active controller. This is a task-design issue (arm rest position / fixed target point), not a metric or physics-correctness bug, and is left unfixed pending a deliberate decision (see `docs/implementation/WORK_PACKAGES.md` I-03's "새로 발견해 미해결로 남긴 항목").

### Command

```bash
ruff check envs/ demos/ tests/
```

### Result

Passed, clean, after fixing import-order/unused-variable nits in the new/changed files (auto-fixed via `ruff check --fix` plus 2 manual nits). The 3 remaining repo-wide `ruff check .` findings are pre-existing issues in `controllers/brian2_stdp_controller.py`, untouched by this work (out of I-03 scope).

### Notes

This fixes the environment-level defects I-03 listed and produces the first reproducible deterministic-scenario evidence for each. It does **not** establish that the task (ball interception) is meaningful as currently configured — see the baseline-comparison finding above. Physical realism of the fly/limb/ball scale is still not claimed (per existing README wording).

## 2026-09-16 — I-01 environment setup and first runtime verification

Interpreter: `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11` (Python 3.11.5, CPython, macOS-26.6.2-arm64-arm-64bit). Chosen per `docs/PLAN.md` D07. Project-dedicated venv created at `.venv/` (previously the shell's active `python3` resolved to an unrelated project's Python 3.9.6 virtualenv, which does not satisfy `pyproject.toml`'s `>=3.10`).

### Command

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Result

Passed. Core deps (`gymnasium==1.3.0`, `mujoco==3.13.0`, `numpy==2.4.6`, `PyYAML==6.0.3`, `matplotlib==3.11.2`) and dev deps (`pytest==9.1.1`, `ruff==0.16.7`) installed without conflicts. Full pinned set recorded in `requirements-lock.txt`. `rl`/`snn` optional extras (stable-baselines3, torch, brian2) were not installed in this pass — out of scope for I-01's core verification.

### Command

```bash
python -c "import envs, controllers, encoders, train, analysis, demos"
# plus explicit per-submodule imports, including controllers.brian2_stdp_controller
```

### Result

Passed. All 6 top-level packages and every submodule import without error, including `controllers.brian2_stdp_controller` despite brian2 not being installed (confirms it is interface-only, per existing docs — no top-level `import brian2` yet).

### Command

```python
import mujoco
model = mujoco.MjModel.from_xml_path("envs/assets/fly_batter.xml")
data = mujoco.MjData(model)
mujoco.mj_step(model, data)
```

### Result

Passed — first actual MuJoCo runtime load and physics step in this project (previously only XML-syntax-checked, never loaded by the MuJoCo runtime). `nq=8 nv=7 nu=1 nbody=4`, one step advances `data.time` to `0.002` (confirms `model.opt.timestep=0.002`, so `max_steps = int(1.6/(0.002*5)) = 160` in `FlyBatterEnv`).

### Command

```python
from envs.fly_batter_env import FlyBatterEnv
env = FlyBatterEnv()
obs, info = env.reset(seed=0)
# 20 random-action steps
```

### Result

Passed — first successful Gymnasium `reset`/`step` cycle. `obs.shape=(11,)`, `action_space=Box(-1,1,(1,))`. No exceptions, no NaN.

### Command

```bash
python -m demos.record_episode  # internally: FlyBatterEnv + ScriptedSwingController, 5 episodes, seeds 0-4
python demos/record_episode.py --episodes 3 --render none
```

### Result

Ran to completion without crashing (measured, not a target number): scripted controller scored **0/5 hits** across 5 episodes (160 steps each, terminates only on contact or `max_steps`/ball-passed truncation). `demos/record_episode.py --episodes 3` produced episode rewards on the order of **-2×10⁷**, far larger in magnitude than the -20..-25 range seen in the direct 20-step random-action check above. Root cause not investigated further here (out of scope for I-01) — the `timing_error` reward term divides by ball x-velocity (`envs/fly_batter_env.py:_time_to_swing_zone`) and is only guarded for `abs(vx) < 1e-6`; under the known uncompensated-gravity trajectory (`docs/records/PROJECT_AUDIT_2026-09-16.md` P0) the ball likely crosses low-`vx` states after ground contact, which is consistent with this magnitude. This is corroborating measured evidence for I-03, not a newly diagnosed bug; no fix applied.

### Command

```bash
pip install build && python -m build --wheel
```

### Result

Passed. All 6 declared packages (`envs`, `controllers`, `encoders`, `train`, `analysis`, `demos`) and `envs/assets/fly_batter.xml` are present in the built wheel — package-data inclusion for the new asset is intact.

### Command

```bash
pytest --collect-only -q
ruff check .
```

### Result

`pytest`: runs, 0 tests collected (`tests/` does not exist yet — expected, no test suite has been written). `ruff`: runs, found 5 pre-existing lint issues in `envs/fly_batter_env.py` (import order, mutable class-attribute default) — not fixed here, out of I-01 scope.

### Notes

This establishes a working, reproducible environment and first-ever runtime execution of the existing scaffold. It does **not** establish physics correctness, learning performance, or that `FlyBatterEnv`'s reward/termination logic is sound — see I-03 in `docs/implementation/WORK_PACKAGES.md` for the known physics defects this run's numbers are consistent with.

## 2026-09-16 — Planning structure review

- Compared SHA-256 fingerprints before/after the documentation changes for all 22 existing Python, XML, TOML and YAML files: identical; no implementation or runtime configuration changes.
- Checked relative Markdown links across 15 root/config/project documents: no missing targets.
- Reviewed active-plan, historical-roadmap, and pending-choice labels for consistency with the Claude implementation handoff.
- These were documentation consistency checks only. No application tests, package installation, physics simulation, or learning experiment was run.

## 2026-09-15–16 — Planning review

- Read 19 Python files, XML, config, package metadata, and project documents.
- Parsed all Python sources with `ast.parse`, without importing dependencies or generating bytecode: 19 passed.
- Current shell inspection: arm64, macOS 26.6.2, Python 3.14.0. NumPy, MuJoCo, Gymnasium, PyTorch, Brian2, SB3 and pytest were absent from this interpreter.
- Memory query `sysctl -n hw.memsize` was denied; available RAM remains unknown.
- Analytic launch check: missing gravity correction causes 2.5428–4.4268 m displacement relative to target over 0.72–0.95 s, assuming free flight. Ground collision was not simulated.
- No local `.git` entry in the project folder. No Git initialization was performed.
- Initial documentation patch was rejected during patch validation; no files changed in that attempt. A revised documentation-only patch was then applied.
- No dependency installation, runtime physics test, external model execution, training, or dataset download was performed.

These checks establish source findings, not physics correctness or model performance.

## 2026-09-15

### Command

```bash
python3 -m compileall envs controllers encoders train analysis demos
```

### Result

Passed. All Python source files compiled successfully.

### Notes

The local shell did not provide `python`; `python3` was used instead.

## 2026-09-15

### Command

```bash
python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject ok')"
```

### Result

Passed. `pyproject.toml` parsed successfully.

## 2026-09-15

### Command

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('envs/assets/fly_batter.xml'); print('xml ok')"
```

### Result

Passed. The MuJoCo XML file is well-formed XML.

### Limitations

This only checks XML syntax. It does not validate MuJoCo semantics or runtime physics behavior.

## 2026-09-15

### Command

```bash
python3 -c "import sys; print(sys.version); import importlib.util; print('mujoco', importlib.util.find_spec('mujoco')); print('gymnasium', importlib.util.find_spec('gymnasium'))"
```

### Result

`mujoco` and `gymnasium` were not installed in the current environment.

### Next Runtime Test

After installing dependencies:

```bash
pip install -e ".[dev]"
python demos/record_episode.py --episodes 3 --render none
```

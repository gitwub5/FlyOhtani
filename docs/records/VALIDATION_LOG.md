# 검증 기록

## 2026-09-16 — I-08a-style + I-07c-score + I-07c-swing: 옆선 자세·원본 색상, 비거리 점수, 스윙 windup 개선

범위: `docs/design/BATTING-QUALITY-AND-SWING.md`의 A(자세·색상)→B(점수/보상)→C(스윙)를 순서대로 진행했다. 중앙 mid_mid만 다뤘다. 8코스 확대·B2·변화구·RL 훈련·전신 역학(I-08b)은 진행하지 않았다.

### A. 옆선 자세와 원본 색상 (`docs/design/FLY-BATTING-STANCE-AND-COLOR.md`)

**자세**: 기존 I-08a-fix의 "직립(pitch -90° about Y)" 변환에 -90°(Z축) yaw를 추가로 합성했다 (`ROOT_TOTAL_MAT = rot_z(yaw) @ rot_y(pitch)`, `scripts/build_fly_visual_asset.py`). numpy로 벡터 변환을 먼저 독립 검증한 뒤 적용: 원본 배쪽(-Z, "가슴") 방향이 world -Y로, 어깨축(+Y)이 world +X(홈→투수 방향과 평행)로 동시에 매핑됨을 확인했다. 실제 컴파일된 씬에서 재측정(`scripts/render_stance_diagnostic.py`): f(몸통 전방)·p(홈→투수) 각도 **90.00°**(설계 허용 80~100°), 어깨축·p 평행 오차 **0.00°**.

**다리 보정 불변성**: 기존 다리 Coxa 보정은 pitch 성분만 상쇄하는 로직이었는데, yaw를 추가해도 다리가 겪는 총 회전은 `Yaw*Pitch*Pitch⁻¹=Yaw`(중력과 같은 축의 순수 yaw라 "아래로 닿는" 정도에 영향 없음)이므로 코드를 바꾸지 않았다 — 기존 접지/도달성 테스트가 전부 무변경 상태로 통과함으로 확인했다.

**머리 방향**: 목(Head) 관절에 별도 quat을 수치적으로 풀어(고정 각도 추측 아님) 로컬 +X가 `BaseballB1Env.RELEASE=(16.5,0,1.8)`을 향하게 했다. **버그 발견/수정**: 처음엔 `geom_xpos/geom_xmat`(메시 자체 정렬이 섞여 들어가는 MuJoCo 내부 좌표)로 검증해 11.17~11.21° 오차(10° 설계 허용 초과)가 나 스크립트가 `SystemExit`으로 올바르게 중단됐다. `probe_data.xpos/xmat`(BODY 프레임)로 일관되게 바꾸자 **정확히 0.00°**로 해소됐다(이 세션 이전의 Thorax `geom_quat` 버그와 동일한 패턴 — I-08a-fix VALIDATION_LOG 항목 참고). **재확인(이번 배치)**: 위 0.00°는 빌드 스크립트가 flybody를 독립 프로브로 세운 상태의 값이다. 실제 `baseball_park_b1.xml`에서 `batter_body`가 `pos="0.1 0.9 1.0"`으로 배치된 뒤(즉 최종 씬)의 head world 위치 기준으로 다시 측정하면 오차는 **4.72°**다 — 여전히 10° 설계 허용 이내지만, 두 숫자는 서로 다른 기준점(고립 프로브 vs 최종 배치 씬)의 값임을 명확히 구분해 기록한다. 진단 이미지: `runs/env002-b1-neuromechfly/mid_mid/stance_axis_diagnostic.png`(f/어깨축/머리방향/p 벡터를 겹친 하향 투영도, 수치 라벨 포함).

**원본 색상**: flygym==1.2.1 wheel의 `flygym/config.yaml`(SHA-256 `97c7a3c1d4131121213868fd1565d5e370ebd456b0b9adfbe9cc456f0f8de7f0`, 317줄) `appearance:` 섹션 14개 그룹(wing/eye/arista/haltere/head/thorax/antenna/proboscis/coxa/femur/tibia/tarsus/a12345/a6)을 `flygym/fly.py`의 `_set_geom_colors`와 함께 참고해 그대로 `APPEARANCE_GROUPS`(`scripts/build_fly_visual_asset.py`)에 옮겼다. 값을 손으로 근사하지 않고 원본 rgba/texture rgb1·rgb2·markrgb·size·random을 그대로 복사했다. 각 그룹마다 MuJoCo 절차적 `<texture builtin="flat|gradient">` + `<material>` 쌍을 생성하고, `strip_physics_attrs`가 geom 이름→그룹 매핑이 없으면 즉시 예외를 던지도록 해(무음 fallback 색 방지) 45개 메시 전부에 원본 대응 재질을 적용했다. 동적 mocap 앞다리(`fly_visual_front_legs.xml`)에도 동일 매핑(`fly_appearance_femur/tibia/tarsus`)을 적용했다. 원본과 다르게 바꾼 값은 없다(가독성 조정 없이 그대로 복원).

**단계A 불변성 검증**: `pytest tests/` **64 passed**(이 배치 시작 시점), 접촉/exit_velocity/착지 등 물리 필드가 이 변경 전후 완전히 동일함을 확인(그립/접지 테스트 전부 재통과). `docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json`에 `appearance`/`pose_construction`(yaw·머리방향) 섹션을 추가해 출처/해시/파생 설정을 기록했다.

### B. 비거리 점수와 `forward-carry-v1` 보상 (I-07c-score)

`envs/baseball_b1_env.py`에 순수 읽기 전용 계산(qpos/qvel/ctrl을 절대 쓰지 않음, `_compute_scoring()`)으로 추가:

- `carry_distance_m`: 첫 bat contact 시점 공 중심(신규 `_first_contact_ball_pos`, contact 이벤트와 같은 지점에서 캡처)→첫 착지 공 중심 XY거리. 기존 `carry_distance_xy_m`(분리/exit 시점 공 위치 기준)과 기준점이 달라 별도 필드로 유지했다 — 실측 mid_mid 예시로 둘이 실제로 다른 값(5.819m vs 5.815m)임을 확인(`test_carry_distance_m_and_carry_distance_xy_m_are_distinct_reference_points`).
- `landing_range_from_home_m`: `HOME_REFERENCE_XY=(0,0)`(구장 좌표 정의 — home plate 뒷꼭짓점이 원점, +x가 투수 방향, `baseball_park_b1.xml` 코멘트)에서 첫 착지까지 거리.
- `scoring_valid`: bat contact 발생 + 정상 분리(`_exit_velocity is not None`) + exit_vx>0 + 실제 착지 관측 + 착지가 전방90° 부채꼴(`x_rel>0 and abs(y_rel)<=x_rel`) + `recontact_count==0` + `not prolonged_contact`.
- `batting_score`: `scoring_valid`면 `carry_distance_m`, 아니면 0.0(정상 실패는 0점, timeout/OOB는 `status="incomplete"`로 `batting_score=None`과 구분).
- `status`: `end_reason`이 `timeout_pitch`/`timeout_flight`/`out_of_bounds`면 `"incomplete"`(착지 미관측), 그 외 종료 사유면 `"complete"`(정상 실패 0점 포함), 진행 중이면 `None`.
- `ForwardCarryRewardWeights`(`forward-carry-v1`, `outcome_scale=0.1, miss_penalty=3.0, control_cost=0.2`): 정상 종료시 `scoring_valid`면 `0.1*batting_score`, 아니면 `-3`; timeout/incomplete는 outcome/벌점 없이 제어비용만; 제어비용 형식·가중치는 기존 `batted-ball-v1`과 동일(중복 적용 아님, 별도 dict `forward_carry_v1.reward_terms`에 항상 계산해 `info`에 병기). 기존 `reward_terms`(활성 버전)는 `reward_version`(기본값 `"batted-ball-v1"`, 하위호환 유지) 선택에 따라 그대로 반환하거나 `forward-carry-v1`로 바꿀 수 있음 — 기본값은 바꾸지 않아 기존 64개 테스트가 전부 무수정 통과했다.

**검증**: 합성 경계 테스트(5/20/60m 유효 착지, 후방·부채꼴 밖·재접촉·prolonged_contact·exit_vx≤0 배제, timeout/OOB→incomplete+null, 진행중→null), 실제 mid_mid oracle episode(현재 스윙 기준 batting_score=5.82m 확인), 중복 지급 금지(활성 스칼라가 정확히 그 버전 항의 합과 일치), timestep 독립 제어비용(두 보상 버전의 control_cost 총합이 정확히 동일), `reward_version` 전환 시 활성 스칼라가 실제로 바뀜을 모두 `tests/test_baseball_b1_env.py`에 추가(19개 신규). **물리 불변성**: `_compute_scoring()`/`_info()` 반복 호출 전후 qpos/qvel 완전 동일함을 직접 비교로 확인(`test_scoring_does_not_change_underlying_physics_trajectory`, 재작성 — 이유는 아래 C 참고). `pytest tests/` **83 passed**(B 배치 완료 시점).

### C. 스윙 windup 개선 (I-07c-swing)

**측정(기존, prep_swing=-1.9)**: 준비각 -1.9rad, 트리거(가속 시작) t=0.375s, 접촉 t=0.459s(각 -1.3635rad, ALIGNMENT 목표 -1.298rad과 0.0655rad 차이 — 실제 접촉은 기하 목표를 살짝 지나침, 기존부터 있던 특성), 제동 진입 t=0.470s, hold 도달 t=0.905s(접촉 후 0.446s, 0.5s 목표 이내), 정착 후 0.2s p-p=9.98e-6rad(0.02rad 기준 이내). 준비→접촉 30.74°, 접촉→정착 26.67°. bat_contact_vx=+6.98m/s, exit_speed=8.53m/s, launch_angle=14.0°, carry=5.82m, batting_score=5.82.

**레버 분석**: `_SwingAxis`의 accelerate 단계는 트리거~목표각 교차(또는 접촉)까지 **끝까지 최대토크**(조기 제동 없음, 이미 설계 요구 충족)이므로, 이 구간의 접촉속도는 `v=sqrt(2*a_max*Δθ)`(등가속 구간, a_max=134.4rad/s²@gear=30, 실측 고정값)로 결정된다. ALIGNMENT의 접촉각(-1.298rad, 방향 무관 기하값)은 그대로 두고 Δθ(준비각에서 접촉각까지 거리)만 `bat_hinge`의 고정 관절범위 `[-2.0,2.0]`(변경 없음) 안에서 넓히면 gear/반발계수를 건드리지 않고 접촉속도를 올릴 수 있음을 확인했다 — 기존 여유(prep=-1.9, 관절한계까지 0.1rad)가 있었다. `test_no_ground_or_torso_penetration_across_full_tilt_and_swing_range`(0.2rad 그리드로 전체 [-2.0,2.0] 관통 없음 기확인)로 관절범위 전체가 물리적으로 안전함을 사전 확인했다.

**탐색**: prep_swing ∈ {-1.9,-1.93,-1.95,-1.96,-1.98,-1.99}, 각각 analytic crossing_time(`sqrt(2Δθ/a_max)`) 주변 ±0.01s를 0.001s 간격으로 국소 탐색(`scripts/swing_experiment.py`, I-07b-fix가 gear/트리거를 찾을 때 쓴 것과 동일한 방법론). -1.93/-1.98/-1.99는 접촉각이 목표에서 너무 벗어나 반대 방향(음의 exit_vx, 전방 실패)으로 나왔다 — 관절범위 끝에 가까울수록 항상 좋아지는 것은 아님을 확인(숨기지 않고 그대로 보고). **-1.96(트리거 0.09425316355759385s)이 채택 후보**: 유효 전방 착지 유지, batting_score/carry 최대.

**채택 후보 vs 기존 비교표** (`runs/env002-b1-i07c-swing/final_comparison_table.json`, 중앙 mid_mid, oracle 동일 시드):

| 지표 | 기존(prep=-1.90) | 신규(prep=-1.96) |
| --- | --- | --- |
| 준비→접촉 각변위 | 30.74° | 34.26° |
| 접촉→정착 각변위 | 26.67° | 26.59° |
| 접촉점 속도 | 7.19m/s | 7.62m/s |
| bat_contact_vx | +6.98m/s | +7.40m/s |
| exit_speed | 8.53m/s | 8.61m/s |
| launch_angle | 14.0° | 41.2° |
| carry_distance_m | 5.82m | 8.48m |
| batting_score | 5.82 | 8.48 (+46%) |
| reward(batted-ball-v1) | 9.999 | 9.9998 |
| reward(forward-carry-v1) | 0.581 | 0.848 |
| 정착시간(접촉 후) | 0.446s (≤0.5s 충족) | 0.431s (≤0.5s 충족) |
| 정착 후 p-p | 9.98e-6rad (≤0.02rad 충족) | 4.25e-5rad (≤0.02rad 충족) |
| 재접촉/prolonged_contact | 0 / False | 0 / False |
| status | complete | complete |

정직하게 보고하는 트레이드오프: **launch_angle이 14°→41°로 크게 높아졌다** — 단순히 더 빠른 직선타가 아니라 궤적 형태 자체가 바뀐 것이며(접촉 시점이 배트의 연속 스윙 궤적 중 다른 지점으로 이동했기 때문, 외형을 의도적으로 고른 결과가 아니라 트리거 재계산의 부산물), 이 시뮬레이션 물리 체계(파리 스케일 질량/공기저항 없음)에서는 이 발사각이 오히려 체공시간을 늘려 비거리를 더 늘린 것으로 관측된다.

**민감도 점검(`scripts/swing_sensitivity.py`)**: trigger ±1 control step(±0.005s) — **채택 후보(-1.96)와 기존(-1.90) 둘 다** 어느 방향으로 한 스텝만 어긋나도 `scoring_valid=False`(반대 방향 배트 궤적 구간과 접촉해버림)로 뒤집힘을 확인했다. **이는 이번에 새로 생긴 문제가 아니라 기존부터 있던, bang-bang 오라클/충돌 타이밍 설계의 공유된 취약성**이며(구체 수치는 `envs/baseball_b1_env.py`의 `CROSSING_TIME_S` 코멘트, `test_i07c_swing_trigger_timing_is_a_known_shared_fragility`), 이번 작업에서 고치지 않았다(닫힌 루프/접촉 트리거 방식으로 재설계해야 하며 범위 밖). physics_dt 절반(0.000125s, frame_skip 40으로 조정해 동일 control_dt=0.005s 유지) + 동일 기록된 제어 시퀀스 재생: batting_score 8.19 vs 8.48(약 3.4% 차이), scoring_valid/forward_flight_success 모두 유지 — 경계 뒤집힘 없이 합리적으로 수렴했다.

**A의 불변성 재검증(새 스윙 전 구간)**: `FrontLegGripOverlay.update()`로 prep_swing=-1.96 전체 에피소드(356스텝) 동안 양손 reach_error가 항상 정확히 0임을 직접 실행으로 확인, 관절범위 전체 관통 검사(`test_no_ground_or_torso_penetration_across_full_tilt_and_swing_range`)도 그대로 통과.

**채택**: `envs/baseball_b1_env.py`의 `BaseballB1Env.prep_swing` 기본값을 -1.9→-1.96, `CROSSING_TIME_S["mid_mid"][0]`을 0.094091→0.09425316355759385로 변경했다(다른 8코스는 여전히 재보정 전이라 미사용 경고를 그대로 유지). 기존 물리값에 고정 회귀하던 두 테스트(`test_central_hit_physics_unchanged_by_the_visual_overlay`, `test_scoring_does_not_change_underlying_physics_trajectory`)는 새 수치로 바꾸되 이유·이전 값·근거를 테스트 docstring에 그대로 남겼다(옛 정답만 교체하고 통과라 부르지 않기 위함). I-07c-swing 전용 신규 테스트 4개(기본값 확인, 기존 대비 개선, 정착 목표 재확인, 트리거 취약성 고정) 추가. `pytest tests/` **87 passed**.

**산출물**: 전후 비교 영상(동일 카메라, 1×, `runs/env002-b1-i07c-swing/{before,after}/{park_wide,batter_side}.mp4`, 화면에 실시간 거리/점수/상태 오버레이 — 비행중 거리는 "NOT final"로 명시), 배트 끝 궤적 그림(`runs/env002-b1-i07c-swing/bat_tip_trajectory_before_after.png`), 수치 비교 테이블(`runs/env002-b1-i07c-swing/final_comparison_table.json`).

### 남은 문제 (정직하게 보고)

- **트리거 타이밍 취약성**(±1 control step로 판정 뒤집힘)은 기존/신규 모두 미해결 — 별도 재설계 과제로 남긴다.
- **41.2° 발사각**은 실제 야구의 "좋은 타구" 감각과 다르게 매우 높다 — 물리적으로는 유효하지만 외형/직관상 부자연스러울 수 있음을 그대로 보고한다.
- 나머지 8코스는 여전히 I-07b-fix 이전(구 prep_swing=1.0, gear=12) 기준으로 미보정 상태이며 이번 prep_swing 기본값 변경으로 그 격차가 더 벌어졌을 수 있다(원래도 "사용 금지"로 명시돼 있었으므로 새로운 리스크는 아니다).
- tilt축의 0.5s 정착 목표 미충족(gear=6 토크 한계, I-07b-followthrough에서 이미 보고)은 이번 작업 범위 밖이라 재검증만 하고 수정하지 않았다.
- 머리방향 실제 씬 오차(4.72°)는 설계 허용(10°) 이내지만 빌드 스크립트가 보고했던 "0.00°"(고립 프로브 기준)와는 다른 숫자이므로 혼동하지 않도록 위에 명시했다.

## 2026-09-16 — I-08a-fix: 외형 좌표 버그 수정과 자세 재정의

범위: `docs/records/FLY-VISUAL-REVIEW.md`의 완료 기준 전부. I-08b, 나머지 8코스, B2/변화구/RL은 진행하지 않았다.

### 0. 검토가 지적한 문제 재확인

`docs/records/FLY-VISUAL-AUDIT.json`(Codex)의 실측: LH 발 최저 world z=0.920263m, RH=0.920254m, LM=1.068321m, RM=1.061728m — 지면(z=0) 기준 모두 약0.92~1.07m 떠 있었다. 직접 재현: 원인은 `scripts/build_fly_visual_asset.py`가 `ground_offset = -min_foot_z`를 fly_visual의 **로컬 프레임**에서 계산했기 때문이다. 이 body를 batter_body(world z=1.0) 안에 `pos="0 0 ground_offset"`으로 중첩하면, 최종 world z = batter_z(1.0) + ground_offset + foot_local_z = batter_z(1.0) + (-foot_local_z) + foot_local_z = **1.0** — 부모의 world 오프셋을 전혀 상쇄하지 않는 계산식이었다. 8cm의 추가 오차는 "발바닥"을 geom **origin**(항상 0,0,0)으로 취급했기 때문 — 실제 메시 표면의 최저점(geom origin이 아닌, mesh vertex)은 origin보다 낮다.

### 1. 좌표 수정

**월드 프레임 접지**: `local_z_offset = -BATTER_WORLD_POS[2] - min_sole_z`로 부모의 world z를 명시적으로 상쇄하도록 수정(`BATTER_WORLD_POS=(0.1,0.9,1.0)`은 `baseball_park_b1.xml`의 `batter_body` pos와 반드시 일치해야 하며, 스크립트 상단에 그 사실을 주석으로 남겼다 — 자동 동기화 수단은 없음).

**실제 메시 정점 기반 측정**: `scripts/fly_mesh_utils.py`(신규)의 `geom_world_vertices()`가 STL 원본 파일을 직접 읽어(`mujoco`가 내부적으로 삼각형을 어떻게 저장하는지에 의존하지 않음) `<mesh scale>`과 geom의 실제 컴파일된 `geom_xpos/geom_xmat`으로 world 좌표까지 변환한다. 발바닥(LH/RH Tarsus1)의 world z 최솟값, 머리 최고점 등 모든 측정을 이 함수로 다시 했다.

**회전 피벗 재발견 — XY 재중심화**: 위 두 수정만으로 자세를 다시 빌드해 앞다리 도달거리를 재측정했더니(스윙 방향 문제로 잘못 진단했던) 어깨-그립 거리가 여전히 준비 자세부터(즉 스윙 동역학과 무관하게) 0.108~0.053m 부족했다. 원인 추적: `FlyBody`(회전 피벗)의 원점이 `Thorax` 자신의 중심이 **아니어서**, -90°(Y축) 회전이 Thorax를 피벗 주위로 "휘둘러" X축으로 약0.52m 밀어냈다(원본 Thorax 로컬 pos (0.198,0,0.519)를 회전하면 (-0.519,0,0.198) — 부호가 바뀌며 큰 X 오프셋이 생김). 이 밀림이 Thorax에 가까운 앞다리 어깨(LFCoxa/RFCoxa)까지 그대로 전파돼, 몸통 자체가 배트보다 훨씬 뒤(-X)에 위치하게 됐다. 해법: `fly_visual`의 `pos.xy`를 `-rotate(thorax_local_pos)[:2]`로 설정해 **회전 후 Thorax가 batter_body 기준 (0,0)에 오도록 재중심화**했다(Z는 기존 접지 계산과 독립이라 손대지 않음).

세 수정 모두 적용 후 재측정: `fly_visual local pos set to (0.518658, -0.000000, 0.022824)`, world sole z = **0.000000**(스크립트 자체 검증 출력), pytest로도 LH -1.1e-7m/RH 3.9e-4m(5mm 기준 이내) 확인.

### 2. 자세 재정의 (사용자 지시대로: 앞다리 그립·뒷다리2개 지지·중간다리 접기)

기존 "4다리(LH/RH/LM/RM) 모두 코xa 보정만 적용해 지면 지지" 설계를 버리고 역할을 셋으로 나눴다:

- **LH/RH(뒷다리, 지지)**: 기존과 동일하게 Coxa에 +90°(Y축) 정적 보정만 적용 — 원본의 "수평 지면 서기" 형태를 그대로 물려받는다.
- **LM/RM(중간다리, 접기)**: Coxa 보정에 더해 Femur·Tibia에도 정적 보정을 추가. 원본 rig의 Femur/Tibia pitch 조인트를 15° 간격(-150°~150°)으로 그리드서치해 LMTarsus1과 LMCoxa 사이 거리를 최소화하는 조합을 찾았다: **Femur=-120°, Tibia=-150°** → 잔여 거리 0.2098(rad-scale 단위, 완전히 편 상태 ~1.6 대비 약87% 접힘). R쪽에 동일 각도 적용 시 대칭 확인(RM 거리 0.2098, 동일).
- **LF/RF(앞다리, 동적 그립)**: Coxa만 정적(어깨 고정점), Femur/Tibia/Tarsus1은 `envs/fly_visual.py`가 매 프레임 IK로 배치(아래).

렌더로 확인(`/tmp/fix_side.png` 등, 세션 로그): 뒷다리 2개가 지면까지 뻗어 있고, 중간다리는 어깨 부근에 접혀 짧게 튀어나온 형태로 보이며 추가 팔처럼 뻗지 않는다. 날개에 가려 완전히 보이진 않지만 클리핑(몸통 관통)은 육안상 확인되지 않았다.

### 3. 앞다리 3배 확대 제거와 도달성 재검증

I-08a는 몸통 K=400과 별도로 앞다리에 K=1200(3배)을 적용했는데, 이는 (좌표 버그로 인해 잘못 측정된) "최대 1.265m 도달거리"를 근거로 한 결정이었다. 좌표 수정 후 재측정:

```
TOTAL_REACH_M (K=400, Femur+Tibia+Tarsus1) = 0.5796441011694135
max reach error (전체 mid_mid 에피소드, L/R 양쪽) = 0.0, 0.0
```

**전체 에피소드(준비→가속→접촉→감속→정착) 내내 도달 오차가 정확히 0** — 자연 팔 길이(몸통과 동일 K=400)만으로 충분했다. "1.265m 필요"는 좌표 버그(주로 XY 재중심화 누락)가 만든 착시였음을 확인했다 — 실제로는 팔을 늘릴 필요가 전혀 없었다. `envs/fly_visual.py`의 3x 확대 코드·상수를 제거하고 `envs/assets/fly_visual_assets.xml`의 LF/RF Femur/Tibia/Tarsus1 메시 scale을 몸통과 동일한 400으로 재생성했다(`test_front_leg_arm_segments_use_the_same_scale_as_the_rest_of_the_body`로 회귀 고정).

**도달 불가능 사례는 없었다** — "도달이 불가능하면 팔다리를 늘리지 말고 원인을 보고해줘"라는 지시에 따라 스트레칭 없이 먼저 진단했고, 실제로는 좌표 버그가 원인이었으며 수정 후 완전히 해결되어 보고할 미해결 도달성 문제가 남지 않았다.

### 4. 앞다리에 Tarsus1(발끝) 복원 — 3구간 IK

I-08a는 Femur+Tibia만 사용하고 Tibia의 끝을 "손"으로 취급했다(Tarsus1 메시 자체는 앞다리에서 아예 제외). 리뷰의 "발끝(Tarsus 포함)을 보존" 요구에 따라 Tarsus1을 실제 3번째 세그먼트로 복원했다:

- Femur+Tibia(2-link 해석적 IK, 코사인법칙, 굽힘평면 기준=world -Z)가 "손목" 지점(그립 목표에서 Tarsus1 길이만큼 뒤로 뺀 점)까지 도달.
- Tarsus1이 손목→그립목표를 직접 잇는다 — **실제로 그립에 닿는 메시가 Tarsus1(진짜 발끝)이지, 추상적인 IK 끝점이 아니다.**

`test_front_leg_overlay_hands_track_the_grip_sites`가 Tarsus1의 원위(distal) 끝(로컬 -Z 방향으로 TARSUS1_LEN_M만큼 떨어진 지점, 실제 메시가 끝나는 지점과 동일한 계산)을 그립 사이트와 비교해 매 스텝 <1mm 오차(기준 5mm)로 확인한다.

### 5. 완료 기준별 검증 결과

| 기준 (설계값) | 결과 |
| --- | --- |
| 양쪽 뒷발 world sole 지면 오차 ≤5mm | LH -1.1e-7m, RH 3.9e-4m (실측, `test_ground_legs_soles_touch_the_true_world_ground_inside_the_batter_box`) |
| 준비~정착 수평 미끄러짐 ≤5mm | 정적 리그(조인트 없음)라 원천적으로 0 — `test_ground_legs_do_not_slip_across_the_episode`로 실측 확인(1e-9 미만) |
| 발이 박스 안 | LH/RH 발 중심 좌표가 batter_box의 pos±half_size 안에 있음을 좌표로 확인 |
| LF/RF 발끝-그립 오차 ≤5mm 전 프레임 | 전체 에피소드 매 스텝 <1mm (`test_front_leg_overlay_hands_track_the_grip_sites`) |
| 관절 부착점 추가 분리 오차 ≤2mm | Femur/Tibia/Tarsus1의 mocap_pos가 IK 계산으로 정확히 이전 세그먼트의 끝점에 배치됨(부동소수점 오차만, <1e-6m) |
| 모든 부위 배율 동일, 뼈 길이 불변 | K=400 uniform(회귀 테스트로 고정); IK는 위치/방향만 바꾸고 세그먼트 길이(FEMUR_LEN_M 등)는 상수로 고정, 메시를 늘이지 않음 |
| physics overlay on/off 불변 | `test_central_hit_physics_unchanged_by_the_visual_overlay` — 소수점 단위까지 동일(이전과 동일 회귀 기준값) |
| 정면·측면 영상 확인 | `runs/env002-b1-neuromechfly/mid_mid/stills/{prepare,contact,settle}_{front,side}.png` + 동영상 |

### 6. 회귀·영상

`tests/test_baseball_b1_env.py`에 4개 신규(스케일 동일성, 월드 접지, 미끄러짐 없음 — 그립 추적 테스트는 새 3-세그먼트 API로 재작성). `pytest tests/` → **64 passed**, `ruff` 클린.

`demos/record_baseball_b1_neuromechfly.py`를 정면/측면/그립 근접 카메라 + 준비/접촉/정착 정지화면 저장 기능을 추가해 재작성, 재실행 — `runs/env002-b1-neuromechfly/mid_mid/`에 영상 4개(park_wide/behind_catcher/batter_side/grip_closeup, 동일 200fps 실시간 축) + 정지화면 9개(3모먼트×3카메라) 저장. 물리 수치는 위 정확값 회귀와 동일.

**manifest 갱신**: `docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json`에 이번 수정 내역(좌표 버그 3건, 자세 재정의, 스케일 통일)과 45개 메시(43개 아님 — LFTarsus1/RFTarsus1도 이제 사용됨, Codex의 `FLY-VISUAL-AUDIT.json` 바이트 동일성 확인 결과 참조)를 반영했다.

### 남은 문제(외형, 기록만)

- 서 있는 키(약1.53m)가 I-08a(1.17m)보다 커졌다 — 2다리 지지로의 자세 변경에 따른 부수 효과이며, 목표 신장을 별도로 정하지 않았다(향후 필요시 K 재조정 가능).
- 팔꿈치 굽힘 평면(BEND_REF=world -Z)은 시각적으로 자연스러워 보이도록 임의 선택한 것이며 해부학적 근거는 없다.
- 중간다리(LM/RM)의 접힘 각도는 그리드서치로 찾은 근사값이며, 몸통 관통 여부를 메시 단위로 엄밀히 검증하지 않았다(육안 확인만 함).
- Head의 3-DOF 목 관절은 여전히 고정, 시선 타기팅 없음. 다리 Tarsus는 대부분(뒷다리·중간다리) 1분절로 단순화 유지.
- I-08b(전신 역학 통합), 나머지 8코스 재보정, B2·변화구·RL 훈련은 범위 밖.


## 2026-09-16 — I-08a: NeuroMechFly 연구용 시각 모델 적용

범위: `docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md` section C. I-08b(전신 역학 통합), 나머지 8코스 재보정, 강화학습은 진행하지 않았다.

### 1. 자산 취득

`pip download flygym==1.2.1 --no-deps -d <dir>`로 PyPI wheel(sha256 `5db9bb...4390d`, 전체 기록은 manifest)을 받아 압축 해제했다. 패키지 전체가 아니라 실제 사용한 메시 43개(STL)와 `LICENSE`(Apache-2.0)만 `envs/assets/mesh_neuromechfly/`에 복사했다. 원본 번들 MJCF(`neuromechfly_seqik_kinorder_ypr.xml`)는 body/joint 계층과 rest-pose 수치를 읽어오는 **참조용**으로만 사용했고 리포에 그대로 vendoring하지 않았다(`scripts/build_fly_visual_asset.py`가 재실행 시 다시 내려받아 참조하는 방식). 상세 표는 `docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json`.

원본 STL 좌표는 실제 SI 미터 단위(예: Thorax 약 1.07mm)이고, 원본 MJCF는 `<mesh scale="1000...">`로 "1 수치단위=1mm" 관례를 자체적으로 적용한다(`gravity="0 0 -9810"`이 이를 뒷받침). 본 프로젝트 야구장 MJCF는 미터 단위이므로, mesh scale과 모든 유지된 `<body pos>`에 동일한 `K/1000` 배율(K=400, 몸통 전용)을 적용해 실제 학명 수치를 그대로 확대했다 — 별도 스케일 유도 없이 원본의 mm 관례를 그대로 재활용한 선택.

### 2. 일어선 자세 — 시행착오와 최종 해법

**실패한 첫 접근(평탄화 추출)**: `data.geom_xpos`/`geom_xmat`을 직접 읽어 단일 wrapper body의 flat 자식 geom들로 재배치했다. 머리-몸통 거리가 원본과 수치상 동일(0.7218 ≈ 0.722)함을 확인했음에도 렌더에서 머리가 몸통 위에 크게 떨어져 떠 있었다. 원인을 여러 단계로 오진단(메시 자동 중심화 이론 → 반박)한 끝에, MuJoCo의 `fusestatic`이 정적 body 체인을 **압축·합성**하면서 `geom_pos`(body 상대)가 authored 값과 달라진다는 것을 확인했다 — `geom_xpos`(월드) 자체는 정확하지만, 이를 추출해 **새 파일의 body-relative pos로 재주입**하면 그 파일에서 메시가 다시 한번 compile-time 배치를 거쳐 **이중 적용**된다. 재현 확인: 동일 head/thorax 조합을 원본 구조 그대로(미수정) 렌더하면 정상, flatten 후 재주입하면 깨짐.

**해법**: 원본 XML 트리(중첩 body 구조: Thorax→A1A2→...→A6, Thorax→Head→eyes/antennae, Thorax→각 다리 Coxa→Femur→...)를 **그대로 유지**한 채 ElementTree로 직접 편집했다(`scripts/build_fly_visual_asset.py`): mesh scale과 body pos만 비례 재조정하고, 회전은 아래 방식으로 주입했다. 이렇게 하면 MuJoCo 자신의 FK/fusestatic이 원본과 동일한 방식으로 합성해 버그가 사라진다(직접 렌더로 재확인: 머리-몸통 거리 0.0, 시각적으로 완전히 붙어 있음).

**회전 주입**: FlyBody(전체 루트)에 Y축 -90° quat을 부여해 머리-꼬리 축(원래 수평 +X)을 수직(+Z, 머리가 위)으로 세웠다. 이 상태로는 다리도 함께 회전해 지면을 향하지 않으므로, 6개 다리 각각의 `joint_XXCoxa`(피치, 로컬 Y축 — Thorax·모든 Coxa가 원본에서 quat 항등이라 세계 Y축과 동일)에 **정확히 반대 방향(+90°)의 정적 quat**을 Coxa body 자체에 걸었다(라이브 조인트는 삭제, 이제 순수 정적). 같은 물리적 축에 대한 두 회전이 합성되어 정확히 상쇄되므로, 다리는 원본의 "지면 지지" 형태를 그대로 유지한 채 몸통만 세워진다 — 수치가 아니라 MuJoCo 자체 FK로 검증(발 z, 머리 z를 직접 조회해 서 있는 높이(약1.17m) 확인).

접지 보정: 4개 중간·뒷다리 Tarsus1의 최소 z를 조회해 전체 rig를 그만큼 위로 이동, 발이 z=0(로컬)에 닿도록 했다.

### 3. 양손 그립(동적, 앞다리)

앞다리는 정적 리그에서 Coxa만 남기고(Femur/Tibia/Tarsus 제거) 별도로 다룬다. `envs/fly_visual.py`의 `FrontLegGripOverlay`가 매 렌더 프레임: 고정 어깨(LFCoxa/RFCoxa의 현재 world xpos, 정적 리그의 일부라 배트와 무관하게 고정) → 배트 손잡이 위 이동 그립 사이트(`grip_L`/`grip_R`, `bat_tilt_body` 로컬 x=0.05/0.12)까지 2관절(Femur, Tibia) 해석적 IK를 풀어(법선 벡터는 월드 -Z 고정, 코사인법칙) elbow를 구하고, 팔 2개 구간을 각각 mocap 바디(DOF 없음, `data.mocap_pos/mocap_quat`로만 이동, 물리에 영향 불가)에 적용한다.

**리치 재보정**: 처음엔 몸통과 같은 K=400으로 팔 길이(Femur 0.282m+Tibia 0.207m=0.489m 자연 리치)를 잡았으나, 실제 mid_mid 스윙 전체를 시뮬레이션해 어깨-그립 거리를 측정하니 최대 **1.265m**(prep_swing=-1.9의 젖힌 자세가 고정 어깨에서 멀기 때문)로 자연 리치를 크게 초과했다. 앞다리 전용 메시(LFFemur/LFTibia/RFFemur/RFTibia)만 K=1200(3배)으로 재스케일하고 `UPPER_LEN_M`/`LOWER_LEN_M`도 동일 비율로 갱신 — 리치 1.467m로 여유 확보(1.265m 대비). 이는 설계 문서가 명시적으로 허용한 "도달 불가능하면 자세/스케일/그립 위치 조정을 기록" 조항에 해당하며, 실제 파리 비례를 주장하지 않는다.

렌더로 확인: 준비 자세, 접촉 순간(step~94), 팔로우스루 정착(step 200)까지 3개 프레임 모두 양손이 손잡이(손잡이 쪽 끝, x=0.05~0.12)를 붙잡은 모습을 유지했다.

**mocap 갱신 버그(발견·수정)**: 처음엔 `data.mocap_pos`만 설정하고 `mj_forward()`를 다시 호출하지 않아, 파생값인 `geom_xpos`가 갱신되지 않고 이전(리셋 시점) 값에 머물러 팔이 원점 근처에 렌더됐다(배트와 완전히 분리된 것처럼 보임). `FrontLegGripOverlay.update()` 끝에 `mj_forward()`를 추가해 해결 — 이 호출은 qpos/qvel을 적분하지 않고 현재 상태에서 파생량(geom_xpos 등)만 재계산하므로 물리 궤적에 영향 없음(아래 4번에서 실행으로 재확인).

### 4. 물리 불변성 검증

- `batter_torso`(질량55kg, 충돌 geom)는 **전혀 수정하지 않고** `rgba="0 0 0 0"`만 추가해 렌더링만 숨겼다 — 질량·충돌·제외 규칙(`batter_body`-`bat_body`/`bat_tilt_body` exclude)은 그대로. `batter_body`는 관절이 없어(월드에 고정) 이 질량이 애초에 동역학에 관여하지 않음도 확인.
- 모든 `fly_*` geom: `contype=0 conaffinity=0`, 질량 없음(explicit mass 속성 제거) — `test_mesh_overlay_geoms_are_visual_only`로 전수 검증.
- **정확값 회귀**: `test_central_hit_physics_unchanged_by_the_visual_overlay`가 I-07b-followthrough 시점(오버레이 추가 전)에 기록된 값과 현재 값을 `abs=1e-9`로 비교 — bat_contact_vx=6.97982152004564, exit_velocity_xyz=(7.290940342091032,3.924448811941408,2.067631551065398), forward_flight_success=True 전부 일치. 오버레이가 이제 같은 XML에 baked-in되어 "토글로 A/B 비교"가 불가능해졌으므로, 이전 세션에서 기록된 고정 참조값과의 정확 일치가 유일한 증명 수단임을 명시.
- `FrontLegGripOverlay`가 전체 에피소드 동안 IK 도달 범위(팔 길이 합) 안에서 계속 갱신됨을 `test_front_leg_overlay_hands_track_the_grip_sites`로 확인.

### 5. 회귀·영상

`tests/test_baseball_b1_env.py`에 4개 신규(위 3개 + geom 비충돌 전수검사) — `pytest tests/` → **61 passed**, `ruff` 클린.

`demos/record_baseball_b1_neuromechfly.py`: park_wide/behind_catcher/batter_side(전신, 기존 200fps 실시간 축과 동일) + grip_closeup(근접) 4개 카메라, 준비→타격→정착→착지 전체. `runs/env002-b1-neuromechfly/mid_mid/`에 저장. manifest의 물리 수치는 위 정확값 회귀와 동일.

### 남은 문제(외형, 기록만 — 이번 범위에서 해결 안 함)

- 중간·뒷다리 4개가 원본 곤충의 다리 벌림 패턴을 그대로 물려받아 좌우로 모여 있다 — 안정적인 쿼드러페드 지지처럼 보이지 않는다(정적 장식용이라 실제 접지/균형 물리는 없음).
- 앞다리가 K=1200으로 몸통(K=400) 대비 3배 확대되어 비율이 과장됐다(리치 확보의 시각적 대가).
- Head의 3-DOF 목 관절은 원본 정지각으로 고정 — 시선 타기팅 없음.
- Tarsus(발가락 다분절)는 전 다리에서 단순화(중간·뒷다리는 Tarsus1만, 앞다리는 아예 제외) — "단순화 메시"를 재차 단순화한 것.
- I-08b(전신 역학 실제 통합), 나머지 8코스 재보정, RL 훈련은 범위 밖.


## 2026-09-16 — I-07b-followthrough: 팔로우스루 안정화와 접촉 재료 설명 정정

범위: `docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md`의 A(팔로우스루 안정화)와 B(접촉 설명 정정). C(NeuroMechFly 시각 모델)와 나머지 8코스 재보정은 진행하지 않았다.

### 0. 버그 재현

이전 커밋(미커밋 상태, c812766 이후)의 `OracleAimController`로 mid_mid를 재현: 접촉(0.459~0.468s) 자체는 정상이었으나(배트 vx 항상 양수, 접촉 창 정확히 3.75ms), 분리(0.468s) 이후 스윙 ctrl이 목표각(-1.298rad) 주변에서 `1.0 if target>angle else -1.0`을 영원히 반환해 **5회 전부 최대토크 부호 반전, 각도 [-1.599,-0.960]rad 진동**을 확인했다(Codex 보고와 일치). 최초 반전은 t=0.565s(분리 후 0.097s)로, **접촉/타구 결과 자체에는 영향이 없었다** — 이 사실을 먼저 substep 단위로 확인한 뒤에 제어기 재설계로 넘어갔다.

### A. 팔로우스루 상태기계

`controllers/baseball_b1.py`에 `_SwingAxis`/`_TiltAxis`를 신설(prepare→accelerate→brake→hold). accelerate에서 벗어나는 조건은 접촉 관측(obs의 prev_contact 비트) 또는 자기 자신의 스윙이 목표각을 통과했는지(순수 운동학적, 미래 정보나 코스 라벨 누출 없음) 중 먼저 오는 쪽이며, **한 번 벗어나면 다시 accelerate로 돌아가지 않는다.**

**단일 샘플 정착 판정의 함정(실측 발견)**: 처음에는 `abs(vel)<0.2`가 1회만 참이면 즉시 hold로 전환했는데, 실제 충돌 반동이 목표각보다 한참 못 미친 지점(각도 -1.376, 속도 -5.56rad/s)에서 이미 한 번 영속도를 지나가며(각도 -1.496에서 속도 -0.03) **거짓 정착**을 유발했다. hold 진입 즉시 `_hold`(순수 P, gain=50)가 0.6rad 오차를 보고 다시 최대토크를 걸어 원래 버그를 그대로 재현했다(각도가 다시 -1.0을 넘어 폭주). **40 연속 스텝(0.2s) 동안 저속 유지를 요구하도록 고쳐** 해결했다.

**스윙축(gear=30) 설계**: 등속 접촉각(-1.298)에서 ctrl=1 유지 시 실측 최대각가속도=134.4rad/s²(격리 측정, θ=-0.898 부근) → 유효관성 I=gear/a_max=0.2232kg·m². 임계감쇠 근처(ζ=0.9) 감쇠 PD `ctrl=-kp(θ-θ_ft)-kd·ω`를 접촉각+0.4rad(=-0.898rad, 진행 방향으로의 팔로우스루 목표)에 적용. kp=8.0, kd=2·0.9·√(kp·I/gear)=0.4392.

측정(중앙 직구, seed=0): 래치(t=0.470s) 후 **0.435s만에 |qvel|<0.2rad/s 40스텝 연속 달성**(설계기준 0.5s 이내 충족), 이후 0.2s간 각도 peak-to-peak=1.0e-5rad(기준 0.02rad 이내), 목표각 오버슈트 없음.

**틸트축(gear=6) — PD 게인은 문제가 아니었다**: 처음엔 스윙과 같은 감쇠 PD를 시도했으나, 실제 충돌이 유발하는 교란(각속도 -3.3rad/s로 킥, 각도 변위 최대 0.40rad)에서는 kp=5부터 500까지 스윕해도 **결과가 전혀 달라지지 않았다** — 이 정도 오차·속도에서는 어떤 kp를 골라도 ctrl이 포화(±1)돼 있어 사실상 bang-bang과 동일했기 때문이다(선형/비포화 PD가 이 교란을 0.5s 안에 처리하려면 ωn≈3.5rad/s가 필요하다는 역산도 했지만, 이는 임계감쇠 기준 정착시간 1s를 넘겨 애초에 불가능).

틸트의 실제 최대각가속도를 격리 측정하니 **a_max=10.07rad/s²(ctrl=1, θ=0 부근)** — 기하학적 "막대-끝-고정" 추정치(27.7)의 절반 이하였다(스윙-틸트 중첩 관절 구조로 인한 실제 유효관성이 예상보다 큼, I_eff=gear/a_max=0.596kg·m²). 이 실측값으로 **시간최적 bang-bang**(`(θ-θ_target)+ω|ω|/(2·a_max)`의 부호로 스위칭)을 적용: 반전/발산은 제거됐고(순수 P 방식의 무한 반전과 달리 스위칭 곡선을 따라 단조에 가깝게 수렴), 최종적으로 각도 -0.0002rad, 속도 0.06rad/s까지 수렴했다. 그러나 **정착까지 실제로 0.6~0.9s가 걸려 0.5s 설계 기준을 못 채웠다** — 이는 gear=6의 실제 토크 한계이지 제어 설계의 결함이 아니다(연장 시뮬레이션으로 재확인, 다만 스윙축 ctrl을 인위적으로 0으로 고정한 상태라 정확한 재현은 아니고 근사치). 타구 판정에 쓰이는 실제 에피소드는 공이 착지하며 t≈1.17s(래치 후 0.70s)에 끝나, 40연속 스텝 확인이 완료되기 전에 에피소드가 끝난다 — 최종 상태 자체는 사실상 수렴(속도 0.06rad/s)해 있었다.

**정확히 0.5s를 만족시키려면 gear 재보정이 필요하다** — 스윙축의 gear=12→30 재보정과 동일한 종류의 작업이며, 이번 범위(팔로우스루 안정화) 밖으로 남겨둔다.

`FixedPoseAlwaysSwing`도 이 조사 중 발견한 잔여 버그: I-07b-fix에서 스윙 방향을 반전했지만 이 baseline의 ctrl은 `-1.0`(구 방향) 그대로였다 — `prep_swing=-1.9`에서 `-1.0`은 -2.0 관절한계로 그대로 박혀 접촉이 전혀 없었음을 실행으로 확인(`contact_occurred=False`, 최종각=-2.003). `+1.0`으로 수정.

**중앙 직구 결과 보존 확인**: bat_contact_vx/exit_velocity_xyz/forward_flight_success/first_landing_xyz가 재작성 전후 소수점까지 완전히 동일(=7.290940342091032 등) — 접촉 이전(0~0.468s) 로직을 전혀 바꾸지 않았으므로 당연하지만, 실행으로 재확인했다.

### B. 접촉 재료 설명 정정

Codex 지적대로, 실제 ball–bat 접촉의 `data.contact[i].solref`를 직접 읽으면 **(0.0051, 0.505)**이며 ball_geom 단독 선언값 (0.0002, 0.01)과 다르다. 원인을 직접 확인: `ball_geom`과 `bat_geom`은 priority=0, solmix=1.0으로 동일하며, MuJoCo는 이 경우 **두 geom의 solref/solimp를 산술평균**한다(공식 문서: https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters). (0.0002+0.01)/2=0.0051, (0.01+1.0)/2=0.505 — 정확히 일치. solimp[2]도 (0.0001+0.001)/2=0.00055로 실측과 일치. 기존 XML 주석의 "the pair uses the softer/lower-priority of the two geoms' params"는 틀렸다 — 정정했다.

refsafe(`model.opt.disableflags`의 `mjDSBL_REFSAFE`)는 비활성(=refsafe 활성) 상태이며, refsafe는 solref[0](timeconst)가 2×physics_dt(=0.0005s) 미만이면 그 값으로 clamp한다. 실측 유효 timeconst(0.0051s)가 안전 하한보다 10배 크므로 **이번 설정에서 refsafe clamp는 작동하지 않는다**(직접 확인, 값 그대로 반영됨) — 다만 physics_dt를 더 세밀하게 바꾸면 재확인이 필요하다는 점을 calibration manifest에 남겼다.

기존 dampratio 스윕 결론("0.01 밑으로는 결과가 안 바뀜")은 이 혼합 사실을 반영해도 **여전히 유효하다** — 혼합이 항상 대략 절반 가중이므로, ball 단독 dampratio를 낮추면 실제 접촉 dampratio도 비례해서 낮아지고(0.01→평균 0.505, 이미 상당히 감쇠된 값), 같은 방향의 개선이 계속되다가 물리적으로 수렴한 것이지 혼합을 몰라서 생긴 우연이 아니다.

**신규 calibration manifest**: `docs/design/ENV-002-B1-contact-calibration.json` — solver 설정(timestep/integrator/refsafe), 선언된 geom별 접촉 파라미터, 실측 ball–bat 접촉 파라미터와 혼합 규칙 설명, gear 스윕 전체 표(12/20/27/30/45/60), 실측 a_max(스윙 134.4, 틸트 10.07)와 역산 유효관성, 중앙 직구 최종 수치를 모두 기록. mid_mid만 검증됨을 명시.

### 회귀 확인

`tests/test_baseball_b1_env.py`에 4개 신규: `test_swing_settles_after_contact_instead_of_chasing_forever`(accelerate 재진입 금지, 최종 hold 상태), `test_swing_settle_time_and_overshoot_meet_the_design_targets`(0.5s/0.02rad 기준), `test_fixed_pose_always_swing_moves_toward_the_alignment_zone`(방향 회귀), `test_actual_ball_bat_contact_solref_matches_the_documented_mixing_rule`(실측 solref=두 geom 평균). 틸트의 0.5s 기준은 **의도적으로 assert하지 않았다**(실측상 못 채우는 것이 정상이므로 거짓 통과를 만들지 않기 위함).

`pytest tests/` → **58 passed**(B1 20개 + 기존 38개). `ruff` 클린.

**영상/timeline**: `demos/record_baseball_b1_mid_mid_fix.py`에 `timeline.json`(매 control step의 swing/tilt 각도·속도·ctrl·state·접촉 여부) 덤프를 추가하고 재실행 — `runs/env002-b1-fix-verification/mid_mid/{park_wide,batter_side}.mp4` + `timeline.json`.

**손대지 않은 것(사용자 지시대로)**: NeuroMechFly 시각 모델(I-08a), 나머지 8개 코스 재보정, B2·변화구·강화학습 훈련.

**남은 위험**: 틸트 gear=6의 0.5s 미충족은 구조적 한계로 보이나, gear를 올리면(스윙의 12→30처럼) 이번엔 "너무 빨리 움직여 트리거 해상도로 못 맞추는" 문제가 재발할 수 있어 — 재보정 시 스윙에서 겪은 것과 동일한 종류의 시행착오가 필요할 것으로 예상된다. `_SwingAxis`/`_TiltAxis`의 accelerate 단계(코스별 조준이 실제로 움직이는 경우)는 mid_mid(둘 다 prep=target인 특수 케이스, 스윙만 실제로 움직임)에서만 검증됐고 다른 코스 조합은 미검증이다.


## 2026-09-16 — I-07b-fix: 스윙 방향·접촉 판정·중앙 직구 실제 타구 검증

범위: 사용자 지시 "역방향 스윙과 접촉-only 성공 판정을 수정...중앙 직구를...타격하고 착지까지 추적하는 것부터 검증...9개 코스로 확장은 아직". `docs/records/B1-BATTING-REVIEW.md`(Codex 진단)와 `docs/design/ENV-002-BATTED-BALL.md`(타구 규약)를 먼저 읽고 진행했다. B2·변화구·강화학습·9코스 확장은 진행하지 않았다.

### 1. 스윙 방향 원인 분석과 수정

정적 쿼리로 확인: 같은 배트 접촉각(θ=-1.298rad)에서 dθ/dt=+1(증가 방향)이면 배트 팁 속도=(+0.819,+0.229,0), dθ/dt=-1(과거/감소 방향)이면 (-0.819,-0.229,0). 과거 구현은 prep_swing=+1.0에서 감소하는 방향으로 스윙해 접촉점 속도 x부호가 항상 음수였다(Codex 진단과 일치: 9코스 전부 배트 vx<0).

`prep_swing`을 **-1.9**로 변경(관절범위 [-2.0,2.0] 안, 여유 0.1rad), 증가하는 각도(양의 ctrl)로 ALIGNMENT의 동일 접촉각(-1.226~-1.346rad, 방향 무관 기하값이므로 재사용 가능)을 통과하도록 스윙 방향을 반전했다. `envs/assets/baseball_park_b1.xml`에서 prep_swing=-1.9 관통 없음, 양의 ctrl이 각도를 증가시킴(20스텝에 -1.9→-1.899)을 실측 확인 후 반영.

### 2. 접촉-only 판정 제거: phase 상태기계

`envs/baseball_b1_env.py`를 전면 재작성. `docs/design/ENV-002-BATTED-BALL.md`의 phase 모델(`pitch → bat_contact → batted_ball → done`)을 구현:

- 접촉은 이벤트일 뿐 종료 사유가 아니다. `_phase`가 "pitch"를 벗어나면 `pass_x` 판정을 비활성화한다(규약대로).
- 분리: 접촉이 사라진 첫 tick을 후보로 잡고 2ms(`SEPARATION_CONFIRM_S`) 연속 무접촉이면 확정, 그 후보 시각의 공 속도를 `exit_velocity_xyz`로 기록. 중간 재접촉 시 후보를 취소(`recontact_count` 증가, phase는 다시 "bat_contact"로).
- 50ms(`PROLONGED_CONTACT_S`) 초과까지 분리가 없으면 `prolonged_contact=True` 진단 플래그(강제 성공 처리 안 함).
- `forward_flight_success`: batted_ball phase에서 공이 x=5m(`FORWARD_GATE_X`) 기준면을 +x로 통과할 때 인접 tick 사이 선형보간으로 통과 y좌표를 구하고 `|y|≤x`(인필드 부채꼴)인지 확인.
- 종료 사유 세분화: `no_pitch_contact`/`ground_before_bat_contact`(pitch 단계 지면접촉)/`ground_before_separation`(분리 전 지면접촉)/`batted_ball_landing`(분리 후 정상 착지)/`out_of_bounds`(안전망, |x| 또는 |y|>150m)/`timeout_pitch`/`timeout_flight`(분리 후 10s 초과, truncated).
- `mj_step()` 직후 `mj_forward()` 호출(I-07a-1의 RK4 상태 일관성 수정)은 그대로 유지.

`info`에 `docs/design/ENV-002-BATTED-BALL.md`의 전체 지표(contact_occurred, first_contact_time_s, bat_contact_vx, bat_contact_velocity, recontact_count, prolonged_contact, separated, exit_time_s, exit_velocity_xyz, exit_speed, launch_angle_rad, spray_angle_rad, gate_crossing_xyz/time_s, forward_flight_success, first_landing_xyz, carry_distance_xy_m)를 채운다.

**검증:** `test_contact_is_an_event_not_a_terminal_bat_contact_state_is_reached`.

### 3. 물리 재보정 — 스윙 방향만으로는 여전히 실패했다 (예상 밖 발견)

스윙 방향 수정 직후, prep_swing=-1.9·gear=12(변경 전)·기본 solref로 mid_mid를 실행하니 접촉점 속도는 양수(예: trigger=0.30에서 bat_contact_vx=+4.93 m/s)였는데도 **공은 거의 그대로 진행**했다(exit_velocity_xyz의 x성분 -25.4 m/s). 원인을 단계적으로 분리했다:

**3a. 접촉 지속시간이 접촉 강성(`solref`)에 비해 너무 짧다.** 서브스텝 단위로 추적(physics_dt=0.00025s): 접촉은 1~3 서브스텝(0.25~0.75ms)만 지속되는데, `<default>`의 `solref="0.01 1"`(10ms 임계감쇠)은 이보다 10배 이상 느린 시간상수라 힘이 거의 못 쌓인다. 배트 각속도는 접촉 전후로 거의 변하지 않았고(예: 10.40→10.20 rad/s), 공 속도도 35.0→34.25 m/s로 거의 그대로였다(운동량이 사실상 전달되지 않음).

검증: 공 지오멤 solref를 `[0.0002, 1.0]`(더 뻣뻣, 임계감쇠 유지)로 바꾸면 exit vx가 -25.4→-15.3으로 개선. dampratio를 1.0→0.5→0.2→0.05→0.02→0.01→0.005→0.002로 낮출수록(임계감쇠 없는 "바운시" 접촉) 좋은 트리거 시각(0.315근처)에서 exit vx가 2.37→2.64→2.77→2.85로 계속 개선되다가 0.002 근처에서 정체(수확체감). **dt 수렴도 별도 확인**: dt를 0.00025→0.00005→0.00001→0.000005s(25배 세밀)로 낮춰도 exit vx가 -28.8~-28.6 범위에서 수렴해, 이산화/터널링 문제가 아니라 실제 (약한) 접촉 모델 거동임을 확인했다.

**3b. 접촉 법선 방향이 트리거 시각에 매우 민감하다.** `data.contact[].frame`을 직접 조회: trigger=0.25에서는 법선이 거의 Z축(예: [-0.10,0.11,-0.99]) — 배트 원통 캡슐의 위/아래 모서리를 스치는 그레이징 접촉이라 운동량이 거의 수직으로만 전달됐다. trigger=0.30~0.32 근처에서는 법선이 X축에 가까워짐([0.93,0.29,-0.22] 등). **같은 solref/gear라도 트리거 시각(=배트가 정확히 ALIGNMENT 각도를 지나는 순간과 공의 실제 도달 순간의 일치도)이 접촉 품질을 좌우한다.**

**3c. gear=12로는 접촉점 속도 자체가 부족하다.** 위 3a/3b를 최대한 보정해도(dampratio=0.01, 최적 트리거) mid_mid에서 얻을 수 있는 최대 exit vx는 약 +2.85 m/s — 물리적으로 공이 x=5m 기준면에 도달하기 전에 착지해 `forward_flight_success`를 만족하지 못한다. `analytic swing-alone` 테스트로 gear=12의 최대 접촉점 속도를 재확인(prep=-1.9→-1.298 도달에 0.1498s 소요, 도달 시 각속도 8.17rad/s, 접촉점 반경 r≈0.675m 기준 선속도 ≈5.5m/s).

gear∈{12,20,30,45,60} × 트리거 시각(analytic swing-alone 도달 시각 중심 ±0.04s, 0.001~0.002s 해상도) 탐색 결과:

| gear | swing-alone 도달시각 | 최적 trigger | exit_vx | bat_contact_vx | forward_flight_success |
| --- | --- | --- | --- | --- | --- |
| 12 | 0.1498s | 0.316 | +2.64 | 4.10 | False |
| 20 | 0.1163s | 0.346 | +6.30 | 5.57 | False |
| **30** | 0.0950s | 0.365 | **+7.30** | 6.98 | **True** |
| 45 | 0.0775s | 0.386 | -3.92 | 8.33 | False |
| 60 | 0.0673s | 0.396 | -5.54 | 10.28 | False |

gear=45/60은 접촉점 속도 자체는 더 크지만(8.3, 10.3 m/s) 목표각을 더 빠르게 지나쳐 트리거 해상도(0.001~0.002s)로는 "좋은 법선" 구간을 못 맞춰 오히려 나빠졌다 — 3b의 민감도 문제가 지배적이 됨을 보여준다. **gear=30을 채택**(9/9 대신 첫 성공 지점을 택함; 더 정밀한 탐색으로 gear=27도 성공했으나(exit_vx=6.41) gear=30이 더 큰 여유를 가짐).

**채택한 물리 파라미터** (`envs/assets/baseball_park_b1.xml`에 반영, XML 주석에 동일 근거 기록):
- `ball_geom`: `solref="0.0002 0.01" solimp="0.9 0.95 0.0001 0.5 2"` (과거: `<default>` 상속 `solref="0.01 1"`)
- `bat_motor` gear: **30** (과거: 12)

### 4. 중앙 직구(mid_mid) 최종 검증

`OracleAimController`(관측 기반이 아닌 코스 라벨 사용, 도달성 진단 전용)로 새 `CROSSING_TIME_S["mid_mid"]=(0.094091, 0.0)`(=planned_arrival 0.459091s - trigger 0.365s) 적용, seed=0:

```
contact_occurred=True
bat_contact_vx=+6.980 m/s
exit_velocity_xyz=(+7.291, +3.924, +2.068) m/s
exit_speed=8.29 m/s, launch_angle=0.256rad, spray_angle=0.494rad
forward_flight_success=True (x=5m 기준면, |y|≤x 부채꼴 안에서 통과)
first_landing_xyz=(5.545, 2.785, 0.036)
carry_distance_xy_m=5.81
end_reason=batted_ball_landing
recontact_count=0, prolonged_contact=False
```

`ScriptedAimController`(관측 전용, 사전 fit)로는 아직 확인하지 않았다 — mid_mid는 코스 라벨을 몰라도 AIM이 거의 정확해야 하는 중앙 코스라 oracle과 유사할 가능성이 높지만, 9코스 확장 단계에서 함께 재확인 예정.

영상: `demos/record_baseball_b1_mid_mid_fix.py` → `runs/env002-b1-fix-verification/mid_mid/{park_wide,batter_side}.mp4`. 기존 `demos/record_baseball_b1_episode.py`의 "접촉 전 control_dt/접촉 후 physics_dt를 같은 30fps로 저장"하던 20배속 불일치 버그(B1-BATTING-REVIEW.md에서 지적)를 구조적으로 제거했다 — phase 기반 env가 착지까지 전부 `env.step()`(항상 control_dt 해상도) 안에서 진행되므로 별도 post-contact raw-step 루프가 더 이상 필요 없다. 235 프레임을 200fps(=1/control_dt)로 저장해 실제 경과시간(1.17s)과 재생시간이 일치함을 확인(`manifest.json`).

### 5. 보상 (`batted-ball-v1`)

`RewardWeights`를 `docs/design/ENV-002-BATTED-BALL.md` §4대로 교체: `hit_success`/`contact_velocity` 필드 제거, `forward_flight_success=10.0`(최초 1회만 지급 — `test_forward_flight_success_pays_once_mere_contact_pays_nothing`으로 검증), `miss=3.0`(성공 못 한 모든 정상 종료), `control_cost=0.2`(형식 `-0.2·(u_swing²+u_tilt²)·dt`는 이전과 동일, 적분 구간만 pitch+contact+flight 전체로 확장). timeout(`timeout_pitch`/`timeout_flight`)은 truncated 처리, miss 페널티 없음(규약대로).

### 6. 회귀·범위 확인

`tests/test_baseball_b1_env.py`를 16개로 전면 재작성(기존 penetration/제어주기/9코스 격자 테스트 유지, `info["hit"]`/`END_REASON_HIT`/`hit_success` 등 폐기된 API를 쓰던 테스트는 새 phase/forward_flight_success 기준으로 교체). 9코스 전체 oracle 100%를 주장하던 기존 테스트는 **삭제**했다(mid_mid 외 8개 코스는 아직 미검증이므로 거짓 통과를 만들지 않기 위함) — 대신 mid_mid 단일 케이스에 대한 forward-hit 전체 체인 검증(`test_oracle_achieves_a_real_forward_hit_for_mid_mid`)으로 교체.

`pytest tests/` → **54 passed**(B1 16개 + 기존 38개), 회귀 없음.

**손대지 않은 것(사용자 지시대로)**: 나머지 8개 코스의 `CROSSING_TIME_S`/gear-solref 재검증, `controllers/baseball_b1.py`의 9코스 트리거 재탐색, `demos/record_baseball_b1_episode.py`(9코스 baseline·영상 러너, 여전히 `info["hit"]` 기준 요약이라 다음 단계에서 갱신 필요), exit velocity/착지위치의 dt 수렴 검증(BATTED-BALL.md §5.3), B2, 변화구, 강화학습 훈련.

**남은 위험**: gear=30·solref 조합이 mid_mid에서만 검증됐다 — 다른 8개 코스(특히 접촉각이 더 큰 in/out 코스)에서 같은 파라미터로 동일하게 forward_flight_success를 내는지는 확인 전이다. 3b에서 드러난 "트리거 시각에 대한 법선 방향/성공 민감도"가 코스마다 다른 폭을 가질 수 있어, 9코스 확장 시 코스별로 트리거 탐색 해상도를 높이거나 gear를 재검토해야 할 수 있다.


## 2026-09-16 — Codex 타격 방향 독립 진단

- c812766 코드·B1 in_mid 포수 뒤 영상의 프레임 확인.
-9코스 OracleAimController, seed0 재현. 접촉점 배트 vx 모두 음수. terminal 뒤 마지막 ctrl 유지400 substep(100ms) 진단 연장 시 공 vx 모두 음수. 중앙 배트 vx=-9.319m/s,100ms 뒤 공 vx=-30.858m/s. 상세/한계: [검토](B1-BATTING-REVIEW.md).
- 영상은 접촉 전5ms/frame, 종료 후0.25ms/frame을 같은30fps로 저장함을 확인. 시간 배율이 바뀌며 타구 추적 근거가 되지 못한다.
- 구현 파일은 수정하지 않았다. 타구 규약과 I-07b-fix를 문서화했다. 기존 전체 테스트 재실행은 하지 않았다.


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

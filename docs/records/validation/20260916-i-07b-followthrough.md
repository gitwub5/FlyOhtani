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

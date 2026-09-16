# ENV-002 야구 환경 — 현행 규약

id: ENV-002 · status: current (mid_mid만 검증, 나머지 8코스 미검증) · version: 통합 2026-09-16
(R-01 문서 정리, `docs/implementation/REFACTOR-PLAN.md`)

이 문서는 `docs/design/ENV-002-baseball.md`·`ENV-002-B1-courses.md`·
`ENV-002-BATTED-BALL.md`·`BATTING-QUALITY-AND-SWING.md` 네 문서의 **현재 유효한
규칙만** 한 곳에 모은 것이다. 네 문서에 있던 시행착오·후보 비교·완료 보고는
`docs/records/B1-BATTING-REVIEW.md`, `docs/records/validation/`(특히
`20260916-i-07b.md`, `20260916-i-07b-fix.md`, `20260916-i-07b-followthrough.md`,
`20260916-i-08a-style.md`)에 그대로 남아 있으며 이 문서는 중복하지 않는다.
구현은 `envs/baseball_b1_env.py` + `envs/baseball/{courses,reward}.py` +
`controllers/baseball_b1.py`, 자산은 `envs/assets/baseball_park_b1.xml`이다.

파리 외형(자세·색상·메시)은 [FLY-VISUAL-SPEC](FLY-VISUAL-SPEC.md)를 따로 본다 —
여기서 다루는 물리(구장/투구/배트/타구/보상)와는 독립 레이어다.

## 1. 목표와 스케일

야구장 안에서 투수가 던진 공을 타자 박스의 파리 캐릭터가 배트로 쳐, 실제
**전방(+x, 인필드) 타구를 착지까지 추적**한다. 배트 접촉 자체(예전 contact-only
기준)는 성공이 아니다 — `docs/records/B1-BATTING-REVIEW.md`가 기존 "9코스
접촉 100%"가 전부 포수 방향(-x)으로 향했던 문제를 지적했고, 이 문서의 판정은
그 정정 이후 버전이다. 구장·공은 미터 단위 실제 야구 스케일, 타자는 사람 크기로
확대한 파리 캐릭터다 — 이는 시각적·공학적 기본안이며 실제 곤충 몸의 역학이
아니다. B0(고정 직구) → B1(9코스) → B2(속도/시점) → B3(변화구) → B4(혼합/선구안)
순으로 확장한다(§9). 현재 구현은 B0 전체와 B1의 `mid_mid` 코스까지다.

## 2. 좌표계와 구장

홈플레이트 뒤쪽 꼭짓점=(0,0,0). +x는 투수판 방향(=투구가 향해 오는 방향의 반대,
즉 타구가 인필드로 나가는 방향), +y는 3루 방향, +z는 위쪽인 오른손 좌표계.
ENV-001의 +x 투구 관례와 다르므로 부호를 하드코딩하지 않는다.

공식 배치는 [2025 MLB 규칙집](https://mktg.mlbstatic.com/mlb/official-information/2025-official-baseball-rules.pdf)
부록 1-3을 참조 snapshot으로 썼고(2026년 규칙 전체 구현이 아님), I-07a-1에서
실제로 대조해 오차 2건(투수판 크기, 타자 박스 중심)을 발견·수정했다
(`docs/design/ENV-002-field-comparison.md`).

| 항목 | 값 |
| --- | --- |
| 투수판–홈 뒤 꼭짓점 거리 | 18.4404m (60ft6in) |
| 홈플레이트 폭 | 0.4318m (17in) |
| 타자 박스 | 좌우 각 폭 1.2192m × 투구 방향 길이 1.8288m |
| 공 | 질량 0.145kg, 반경 0.0366m 균일 구 |
| 배트 | 길이 0.85m 강체 |
| B0 타자 | 우타자 박스, 지지점 고정 (왼손 타자는 미구현) |

파리 발/지지점만 박스 안 판정 대상이며 배트 스윙 공간은 제외한다. 외야·관중석
장식은 비충돌 시각 자산이며 on/off가 물리 결과를 바꾸지 않는다.

## 3. 투구

B0 인공 투수 preset: release=(16.5, 0, 1.8)m, 목표 기준면 x=0.4318m, 수평
접근속도 35m/s. `T=(release_x−plane_x)/35`, `v0=(target−release−0.5gT²)/T` —
중력만 쓰는 단순 직구이며 실제 투수 측정값이 아니다. reset 시 1회 계산하고
이후 외력/충돌로만 적분한다(매 frame 목표 보정 없음). 손 위치와 공 spawn은
정확히 일치한다.

## 4. 타격 기구 — 2축 배트

B0의 수평 스윙(`bat_hinge`, world +z축)에 B1이 조준용 **틸트 힌지**를 추가했다
(`bat_tilt_hinge`, `bat_hinge`의 자식, 로컬 -y축이라 스윙 각도와 무관하게 항상
배트 길이에 수직). 관절 범위 `[-0.6, 0.6]`rad.

| 축 | gear | 비고 |
| --- | --- | --- |
| swing (`bat_hinge`) | 30 | I-07b-fix에서 12→30 재보정. 중력 토크 0 (수평축) |
| tilt (`bat_tilt_hinge`) | 6 | 별도 보정, swing과 공유하지 않음. **중력 토크 있음**(0.16s 방치 시 0.21rad 처짐) — 대기 중 능동 유지 필수 |

두 축은 같은 회전 사슬에 있어 관성이 서로 영향을 준다(스윙과 틸트를 독립
계산하면 최대 0.11rad 오차) — 컨트롤러는 두 축을 항상 동시에 구동한다(§6).

## 5. 9코스 좌표

`normalized (u,v) ∈ {-2/3, 0, +2/3}²`를 zone 중심/반폭/반높이로 변환한다.

| 항목 | 값 | 근거 |
| --- | --- | --- |
| zone 중심 | (0.4318, 0, 1.0) | B0와 동일 plate 앞면/중앙 |
| 반폭 (y) | 0.2159m | plate 반폭과 동일 |
| 반높이 (z) | 0.35m | 스트라이크존 0.65~1.35m(인공 preset)의 절반 |
| u 부호 (우타자) | u>0=몸쪽(+y) | 우타자 박스가 +y(3루측) |
| v 부호 | v>0=높은 코스(+z) | |

9코스 전부 release/수평속도가 B0와 동일해 도달시각 `T=0.45909s`로 같다(목표
y,z만 다름). `COURSES`/`ALIGNMENT`(코스별 (swing,tilt) 정렬각, 방향-무관 기하값이라
스윙 방향이 바뀌어도 불변)/`CROSSING_TIME_S`(코스별 트리거 시각)는
`envs/baseball/courses.py`에 있다.

**`CROSSING_TIME_S`는 `mid_mid`만 현재(prep_swing=-1.96, gear=30/6, I-07c-swing
이후) 물리에 맞게 재보정됐다.** 나머지 8코스는 I-07b-fix 이전(접촉-only 판정,
역방향 스윙, gear=12) 값 그대로 남아 있고 **재검증 전까지 사용 금지**다(코드
주석에도 명시). 도달 가능성 자체(기하학적으로 배트가 9개 좌표 전부에 닿을 수
있는가)는 `ALIGNMENT` 계산으로 사전 확인됐고 이건 스윙 방향과 무관해 여전히
유효하다.

## 6. 컨트롤러 — oracle과 scripted

`controllers/baseball_b1.py`. 둘은 절대 같은 범주로 결과를 섞지 않는다.

- **`OracleAimController`**: 목표 코스 이름(정답 라벨)을 직접 받아 `ALIGNMENT`의
  (swing,tilt)를 목표로, `CROSSING_TIME_S`의 트리거 시각에 각 축을 bang-bang
  전환한다. **도달성 진단 전용** — 정책이 아니다.
- **`ScriptedAimController`**: 공의 현재 위치/속도(관측 가능한 것만)로 목표면
  y,z를 매 스텝 외삽하고 9개 정렬점에 대한 선형 최소제곱 fit으로 목표/트리거를
  추정한다. 코스 이름표·seed·미래 궤적은 읽지 않는다. 선형 fit의 근사오차로
  9코스 중 5개만 성공한다(I-07b 시점 측정, mid_mid 이후 물리 변경 후 재확인 안 됨).
- **대기 중 유지**: 두 컨트롤러 모두 대기 시 강한 비례 제어(gain=50)로 준비각을
  유지한다. swing은 중력이 없어 이 게인으로 충분하지만 tilt는 중력이 있어
  필요하다.
- **접촉 후 팔로우스루**: `_SwingAxis`/`_TiltAxis` 상태기계가
  prepare→accelerate→brake→hold를 관리한다. accelerate는 접촉 관측 또는
  자신의 목표각 통과(관측 가능한 조건, 미래 정보 아님)로 1회만 래치되고 절대
  되돌아가지 않는다 — 이전에는 목표각 주변에서 최대토크 반전을 반복하는
  bang-bang이 5회 이상 발생했었다(`docs/records/validation/20260916-i-07b-followthrough.md`).
  swing은 임계감쇠 PD(측정된 실제 최대각가속도 134.4rad/s²에서 유도), tilt는
  실제 구동력이 선형 PD로는 수렴하지 않아(kp를 500까지 올려도 ctrl이 계속
  포화) 시간최적 bang-bang 후 감쇠 hold로 전환한다.
  - swing: 래치 후 0.435s 안에 정착(설계 목표 0.5s 충족), peak-to-peak 1.2e-5rad.
  - tilt: 약 0.6~0.9s 소요 — **gear=6의 실제 구동력 한계로 0.5s 설계 목표
    미충족**. 게인 튜닝이 아니라 gear 재보정이 필요하며 보류 중.
- **`FixedPoseAlwaysSwing`**: 조준 없이(tilt=0 고정) 항상 스윙만 최대 출력 —
  baseline 비교용.

## 7. 타구 추적과 접촉 이후 상태 전환

phase: `pitch → bat_contact → batted_ball → done`. 최초 접촉은 사건이며
terminal이 아니다. 접촉 이후 투구 pass_x 판정(맞지 않고 지나감)은 비활성화한다.

- 접촉 직전 상태, 접촉점/법선, 물질점 속도, 접촉 지속시간을 기록한다.
- 접촉이 사라진 최초 tick을 후보 분리시각으로 잡고 **2ms 연속 무접촉**이면
  확정한다. `exit_velocity`는 그 시각의 공 중심 선속도. 중간 재접촉이면 후보를
  취소하고 `recontact_count`를 올린다.
- 접촉 50ms 이내에 분리되지 않으면 `prolonged_contact=true` 진단 플래그(수치/재료
  모델 검토 대상 표시, 강제 성공 처리 안 함).
- 종료 사유: 첫 타구 지면 접촉(`batted_ball_landing`), 경기장 경계 통과 또는
  최대 비행 10s(`timeout_flight`, truncated). 투구 단계의 지면-우선 실패 규칙은
  유지된다.

## 8. 판정·지표·점수

`info`에 항상 채워지는 필드: `contact_occurred`, `bat_contact_vx`,
`exit_velocity_xyz`, `exit_speed`, `launch_angle_rad`(=atan2(vz,hypot(vx,vy))),
`spray_angle_rad`, `first_landing_xyz`, `carry_distance_m`,
`landing_range_from_home_m`, `scoring_valid`, `batting_score`, `status`,
`recontact_count`, `prolonged_contact`, `forward_flight_success`.

- **`forward_flight_success`**(1차 공학적 기준, `docs/design/ENV-002-BATTED-BALL.md`
  원안): 분리된 공이 지면 닿기 전 x=5m 기준면을 +x로, `|y|≤x`인 인필드 부채꼴
  안에서 통과.
- **`carry_distance_m`**: 첫 bat contact의 공 중심 → 첫 지면접촉 공 중심까지 XY
  직선거리.
- **`landing_range_from_home_m`**: 홈 기준점(월드 원점 XY, `HOME_REFERENCE_XY`)
  → 첫 착지까지 XY거리. carry와 기준점이 다르므로 별도 필드.
- **`scoring_valid`**: 정상 분리(exit_vx>0) + 실제 첫 착지 관측 + 착지가 전방 90°
  부채꼴 내부(`x_rel>0 and |y_rel|≤x_rel`) + 재접촉 0 + `prolonged_contact=false`.
  이 판정은 **거리 실험용 전방 착지 판정**이며 공식 페어/파울·안타·홈런 판정이
  아니다(수비/담장/주루 미구현).
- **`batting_score`**: `scoring_valid`면 `carry_distance_m`(1m=1점), 아니면 0.
  `status="incomplete"`(timeout/out-of-bounds로 착지 미관측)면 `null`.

이 판정 체계 전부는 `envs/baseball/reward.py`의 `compute_scoring()`에 있다.

## 9. 보상

`reward_version` 기본값은 **`batted-ball-v1`**(변경 안 함, 순수 정리 원칙).
`forward-carry-v1`은 선택 가능하며 두 버전의 `reward_terms`가 항상 `info`에
함께 채워진다(비교용). 둘을 같은 스칼라에 섞지 않는다.

| 버전 | outcome 항 | control_cost | miss/기타 |
| --- | --- | --- | --- |
| `batted-ball-v1`(기본) | `forward_flight_success`면 +10 (1회) | `-0.2∫(u_swing²+u_tilt²)dt` | 정상 종료 미성공 `-3` |
| `forward-carry-v1` | `scoring_valid`면 `0.1×batting_score`, 아니면 `-3` | 동일 | timeout/out-of-bounds는 outcome/벌점 없이 이미 쓴 control_cost만 유지 |

RL 훈련은 아직 시작하지 않았다.

## 10. 접촉 재료(calibration)

Ball–bat 접촉의 실측 `solref`는 **(0.0051, 0.505)**다 — XML의 ball geom 단독
값 (0.0002, 0.01)이 아니라 동일 priority인 두 geom의 solmix 가중평균이다
([MuJoCo 문서](https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters)).
solver/실측 파라미터/gear 스윕 전체는
`docs/design/ENV-002-B1-contact-calibration.json`에 있다(mid_mid만 검증됨을
명시). refsafe는 활성이나 실측 timeconst(5.1ms)가 안전 하한(2×dt=0.5ms)보다
훨씬 커 이 설정에서는 clamp가 작동하지 않는다.

## 11. 검증 기준과 현재 통과 상태

`docs/design/ENV-002-BATTED-BALL.md` 원안 §5의 판정 기준(양의 접촉점 vx, 양의
분리 후 vx, dt 수렴, 9코스 확장)은 mid_mid에서만 실제로 확인됐다. dt 수렴
(0.00025/0.000125/0.0000625s에서 출구속도 성분 오차 ≤max(0.5m/s, 5%), 착지
위치 오차 ≤0.5m)은 별도 재실행이 필요하며 이번 정리에서 재확인하지 않았다.
현재 검증된 수치·qpos/qvel 고정값은
`docs/records/evidence/R00-baseline-mid_mid-before-after.json`.

## 12. 영상·기록

시뮬레이션 시각 기준 30/60fps 샘플링, 접촉 전후 동일 배율(기본 1×). frame별
simulation_time과 playback_time을 저장해 renderer가 물리를 진행시키지 않게
한다. 화면에는 +x 인필드 화살표, 공 속도벡터, contact/forward_success debug
overlay(정책용 카메라에는 제외). 현재 mid_mid 전용 recorder는
`demos/record_baseball_b1_mid_mid_fix.py`, `demos/record_i07c_before_after.py`.
9코스 전체를 도는 옛 recorder(`demos/record_baseball_b1_episode.py`)는 접촉-only
시절 `hit` 필드를 읽는 legacy라 실행이 차단돼 있다(R-03,
`docs/records/evidence/R00-known-failures-at-checkpoint.md` 항목 3).

## 13. 로드맵 (B0 이후, 미구현)

| 단계 | 투구 구성 | 상태 |
| --- | --- | --- |
| B2 | 연속 위치+속도+릴리스 대기시간 변화 | 미구현 |
| B3 | 공기저항·스핀 기반 변화구(Magnus 모델) | 미구현. 계수는 [Alan Nathan의 자료](https://baseball.physics.illinois.edu/) 검토 후 별도 AIR-001 규약으로 고정 |
| B4 | 구종 혼합·스트라이크/볼·선구안 | 미구현 |

관측 profile: B0/B1은 참 공 위치/속도+몸 상태를 주는 `state` profile. 목표
코스·구종 정답·미래 통과점·RNG state는 정책 입력에서 제외(연구용 정답은 평가
로그로만 저장). 카메라 기반 `vision` profile은 별도 운영 예정.

## 14. 범위 밖 (이번 정리에 포함하지 않음)

타이밍 ±5ms 취약성 개선, tilt gear 재보정, 나머지 8코스 재보정, 왼손 타자
profile, 수비·주루·공식 페어/파울 판정, RL 훈련, I-08b(전신 역학 통합).
`docs/records/STATUS.md`의 "알려진 한계"에 각각의 현재 상태가 있다.

# KC-01a — 몸통–배트 협응 최소 역학 모델

id: KC-01a · status: current (mid_mid만, 고정 기반) · version: 1.0 · 2026-09-17
· proposed by: `docs/research/BATTING-KINETIC-CHAIN.md` · 대체 안 함:
`docs/design/BASEBALL-SPEC.md`(B0/B1, 계속 기준선으로 보존)

이 문서는 구현 전에 고정한 설계다. B1은 전혀 수정하지 않았다(`envs/baseball_b1_env.py`,
`envs/assets/baseball_park_b1.xml`, `controllers/baseball_b1.py` 무변경). KC-01a는
별도 XML(`envs/assets/baseball_park_kc01a.xml`)·별도 env(`envs/baseball_kc01a_env.py`,
`BaseballKC01aEnv`)·별도 컨트롤러(`controllers/baseball_kc01a.py`)다. 채점 로직
(`envs/baseball/reward.py`의 `compute_scoring`)만 그대로 재사용한다 — 타구 판정은
배트를 몇 개 관절이 구동했는지와 무관한 순수 함수이기 때문이다.

## 1. 몸통 회전축과 배트 스윙·틸트축의 연결 구조

```
world
 └─ torso_body  (pos 고정 = B1의 batter_body와 동일 위치(0.1, 0.9, 1.0), 이번 라운드는 이동 없음)
     │
     ├─ [joint] torso_yaw   hinge, axis (0,0,1), range ±0.6 rad, gear 30
     │  실제 유한 관성(질량 35kg, 캡슐 형상에서 inertiafromgeom로 계산,
     │  Izz≈0.334 kg·m² 단독/≈2.63 kg·m² 팔 적재 시 — §2)
     │
     ├─ [geom] torso_geom  (물리용, 투명, batter_torso와 동일 캡슐이나
     │  하단 상승 -1.0→-0.84로 지면 관통 제거 — §5 발견사항)
     │
     ├─ [include] fly_visual_body.xml  (파리 외형 전체 — torso_body의
     │  자식이므로 torso_yaw 회전을 물리 기구학으로 그대로 따라간다.
     │  별도 코드/재굽기 없음 — §3)
     │
     └─ [body] bat_body  (torso_body 기준 local pos 0.15 -0.25 0, B1과 동일)
         ├─ [joint] bat_hinge  hinge axis (0,0,1), range ±2.0, gear 30 (B1과 동일)
         └─ [body] bat_tilt_body
             ├─ [joint] bat_tilt_hinge  hinge axis (0,-1,0), range ±0.6, gear 6 (B1과 동일)
             └─ [geom] bat_geom + grip_L/grip_R sites
```

핵심: `bat_hinge`/`bat_tilt_hinge`는 **torso_body의 로컬 프레임**에 정의된다. torso가
회전하면 두 축 전체가 강체로 함께 실려 회전하므로, 배트의 월드 좌표 위치·속도는
`torso_yaw`와 `bat_hinge`(+`bat_tilt_hinge`)가 합성된 실제 운동학의 결과다 — 몸통
각도만 시각적으로 바꾸는 것이 아니라 실제 `qpos`/`qvel`이 배트 강체에 전달된다.
접촉점 속도는 `mj_jac`(전체 `qvel`에 대한 완전한 자코비안)로 계산하므로 torso_yaw의
기여가 자동으로 포함된다(코드 변경 없음, `envs/baseball_kc01a_env.py::_point_velocity`).

**반작용**: torso_yaw는 힌지이므로 토크만 world로 전달되고(1축 구속, 병진 없음), 배트/공이
torso에 가하는 반작용 토크는 `data.qfrc_actuator`/구속력으로 측정 가능하다(§4). 몸통이
번쩍 들리거나 미끄러지는 자유도는 없다 — "고정 기반"의 의미가 정확히 이것이다.

## 2. 몸통 질량·관성·가동범위·구동 한도의 선택 근거

모든 수치는 **공학적 가정**이며 실제 초파리 해부학도, 측정된 인체 데이터도 아니다.

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 몸통 질량 | 35 kg | B1의 정적 `batter_torso`(55kg, 관절 없어 동역학과 무관했던 값)를 그대로 가져오지 않음. 70kg 등가 인간 스케일 캐릭터의 체간+머리 질량 비율(약 50%, de Leva류 분절 질량비 어림)로 재산정. 다리는 이번 라운드에 별도 모델링하지 않으므로 제외 |
| 몸통 형상 | 캡슐, 반경 0.14m, `fromto` (0,0,-0.84)~(0,0,0.35) | B1의 시각적 프록시 캡슐과 동일 반경/외형. 하단을 -1.0→-0.84로 올림(§5) |
| 관성 | `inertiafromgeom`로 질량·형상에서 자동 계산 (Izz≈0.334 kg·m², 단독) | 이 코드베이스의 기존 관례(다른 모든 body와 동일 방식). 손으로 텐서를 지어내지 않음 |
| 가동범위 | torso_yaw ±0.6 rad (≈±34°) | tilt축(±0.6)과 같은 규모로 설정한 임의 공학적 선택. 실제 인체 골반-어깨 분리각 문헌과 일치시키려 하지 않음(`docs/research/BATTING-KINETIC-CHAIN.md`가 명시적으로 금지) |
| 구동 gear | 30 (`torso_motor`) | **계산이 아니라 실측**: 무공, 팔/틸트는 prep 고정, ctrl=+1 단독 구동으로 0.5rad 도달 시간을 gear별로 스윕(`scripts/kc01a_calibrate.py`). gear=25→0.33s(기준 미달), gear=30→0.300s(기준 충족, 0.30s 예산은 B1 tilt축 보정과 동일 예산). gear=30이 bat_motor와 같은 값인 것은 **우연**(다른 질량/관성/기준에서 독립적으로 나온 결과), 복사가 아님 |
| 측정 a_max | 11.41 rad/s² (gear=30, 팔 prep 적재 상태) | 몸통 단독(적재 없는 이론값)이 아니라 배트+공 관성이 실린 실제 부하 상태로 측정(§4 브레이크 게인 유도에 사용) |

## 3. 관측·행동·제어 설정과 검증 기준

**행동(3차원)**: `[torso_ctrl, swing_ctrl, tilt_ctrl]`, 각 `[-1, 1]`. B1의 2차원
`[swing_ctrl, tilt_ctrl]`과 호환되지 않는 새 계약 — 버전을 분리한다(재사용 안 함).

**관측(15차원)**: `ball_pos(3), ball_vel(3), torso_angle, torso_vel, swing_angle,
swing_vel, tilt_angle, tilt_vel, predicted_time_to_target, prev_contact,
normalized_step`. 코스 정답·미래 통과점은 포함하지 않는다(B1과 동일 원칙).

**시각 모델 추종**: `fly_visual_body.xml`가 `torso_body`의 자식이므로 렌더 시
`envs/fly_visual.py`의 앞다리 IK가 매 프레임 실제(회전한) 어깨(`LFCoxa`/`RFCoxa`)와
그립 사이트의 월드 좌표를 그대로 읽는다 — 코드 변경 없이 몸통 회전을 따라간다.
**그립 오류를 숨기지 않는다**: `FrontLegGripOverlay.update()`가 반환하는
`reach_error`(0보다 크면 실패)를 모든 조건에서 기록하고, 0이 아니면 팔을 늘리는 대신
있는 그대로 보고한다(§5).

**검증 기준(구현 전 고정, 무공 검증으로 사후 확인)**:
- torso_yaw 초기 관통 0, 전 범위(torso×swing×tilt 격자) 관통 0.
- torso_yaw 관절 방향: 양의 ctrl이 양의 각가속도를 낸다(부호 확인).
- 접촉 없는 무공 회전에서 몸통 단독/팔 단독의 각가속도가 §2의 측정값과 일치.
- 에너지 수지: 액추에이터가 한 양의 일 − 흡수된 음의 일 − 관절 damping 손실 ≈
  운동에너지 변화(고정축이므로 위치에너지 변화 없음). 무한 에너지 생성이 없음을 확인.
- 정착: 공 없는 스윙에서도 목표 통과/접촉 latch 후 0.5s 이내 각 축 `|qvel|<0.2rad/s`
  (미충족이면 B1의 tilt축처럼 원인을 그대로 보고, 임의로 게인을 올려 숨기지 않음).

## 4. 기존 B1과 달라지는 부분

| 항목 | B1 | KC-01a |
| --- | --- | --- |
| 배트 마운트 | `batter_body`, 관절 없음(용접) | `torso_body`, `torso_yaw` 실제 관절 |
| 능동 DOF | 2 (swing, tilt) | 3 (torso, swing, tilt) |
| 몸통 질량의 동역학적 역할 | 없음(용접이라 무관) | 있음(회전 관성, 반작용) |
| 행동/관측 차원 | 2 / 13 | 3 / 15 |
| 지면-몸통 접촉 | 정적-정적 쌍이라 MuJoCo가 접촉 생성 안 함(발견, §5) | 동적 body라 실제 접촉 생성 — 형상을 올려 회피 |
| 파리 외형 회전 | 없음(고정 자세) | torso_yaw를 그대로 따라감 |
| 채점/보상 판정 | `compute_scoring`/`compute_reward_terms` | `compute_scoring` 재사용, reward는 3-제어항 버전을 KC-01a 자체 구현(`_reward`) — B1의 2항 함수 시그니처를 바꾸지 않기 위해 |
| 기준 스코어/재료 | `batted-ball-v1`, ball solref 등 | 동일(변경 없음) — 궤적 차이만 비교 |

## 5. 실제 구현 중 발견한 사항 (설계에 반영됨)

- **지면-몸통 접촉의 숨은 전제**: B1의 `batter_body`는 관절이 없어(용접) MuJoCo가
  정적-정적 geom 쌍의 접촉을 아예 생성하지 않는다 — 캡슐 하단이 실제로는 지면 아래
  14cm까지 뚫려 있었지만 동역학적으로 전혀 문제되지 않았다. `torso_yaw`를 추가해
  body가 동적이 되는 순간 이 잠재적 관통이 실제 활성 접촉/`_check_no_initial_penetration()`
  실패로 나타났다 — 캡슐 하단을 올려(§2) 해결했다. 순수 시각 표시(alpha=0)라 렌더에는
  영향 없다.
- **torso_only는 유효 타구를 만들지 못했다**: 최선의 트리거 시각(0.310s)에서도
  접촉점 속도 최대 ≈3.08 m/s로, swing 단독(최대 ≈7-10 m/s대)에 크게 못 미친다.
  gear를 swing과 동일하게 맞춰도 몸통(35kg)의 관성이 배트(0.9kg)보다 훨씬 커서
  유효 타격을 만들기엔 부족했다 — **몸통 추가가 개선을 보장하지 않는다는 사실을
  그대로 보고한다**(비목표를 가정하지 않음). 상세 수치는 `docs/records/KC-01a-COMPARISON.md`.

## 6. 비교 조건 (구현 후 실행)

| 조건 | torso | swing | tilt |
| --- | --- | --- | --- |
| `arm_only` | 고정(0) | 트리거 0.09425316355759385s → -1.298 | 고정(0) |
| `torso_only` | 트리거 0.310s → +0.496 | 고정(-1.96) | 고정(0) |
| `simultaneous` | 트리거 0.096s → -0.4 | 트리거 0.096s(동시) → -0.726 | 고정(0) |
| `staggered` | 트리거 0.242s → -0.4 (swing보다 0.12s 먼저) | 트리거 0.122s → -0.726 | 고정(0) |

네 조건 모두 **같은 하드웨어**(같은 gear/range)를 쓰고 어느 축이 언제 움직이는지만
다르다 — "모터 추가 효과"와 "협응 시점 효과"를 분리하는 설계다. 실측 결과·에너지/
피크출력표·영상은 `docs/records/KC-01a-COMPARISON.md`.

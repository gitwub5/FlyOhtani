# 파리 외형 — 현행 규약

id: FLY-VISUAL · status: current · version: 통합 2026-09-16
(R-01 문서 정리, `docs/implementation/REFACTOR-PLAN.md`)

`docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md`(C절, 연구용 파리 모델 선택)와
`docs/design/FLY-BATTING-STANCE-AND-COLOR.md`의 현재 유효 규칙을 한 곳에
모았다. 시행착오·좌표 버그 경위는 `docs/records/FLY-VISUAL-REVIEW.md`와
`docs/records/validation/20260916-i-08a.md`/`20260916-i-08a-fix.md`/
`20260916-i-08a-style.md`에 있다. 배트/스윙 물리는 이 문서의 범위가 아니다 —
[BASEBALL-SPEC](BASEBALL-SPEC.md)을 본다.

구현: `scripts/build_fly_visual_asset.py`(정적 리그 생성기) +
`envs/fly_visual.py`(앞다리 동적 IK 오버레이) + `envs/fly_visual_mesh.py`(STL
정점 측정 유틸) + `envs/assets/fly_visual_{assets,body,front_legs}.xml` +
`envs/assets/mesh_neuromechfly/*.stl`(45개).

## 1. 자산 출처

[NeuroMechFly/FlyGym](https://neuromechfly.org/) — 공식 설명상 실제 성체
**암컷** 파리의 micro-CT 기반 모델. PyPI `flygym==1.2.1`(Apache-2.0,
NeLy-EPFL)을 `pip download --no-deps`로 받아 실제 사용한 메시 45개(STL)와
라이선스만 `envs/assets/mesh_neuromechfly/`에 vendoring했다. 출처·해시·재획득
절차는 `docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json`과
`THIRD_PARTY_NOTICES.md`, 데이터 정책은 `docs/RESEARCH_SOURCES.md`에 있다.

**NeuroMechFly(암컷 외형)와 신경회로 트랙의 MaleCNS(수컷 연결망)는 같은
개체/성별의 디지털 복제가 아니라 명시적으로 별도인 데이터 계층이다.** 하나를
다른 하나의 증거로 쓰지 않는다.

## 2. 자세 — 다리

| 다리 | 역할 | 구현 |
| --- | --- | --- |
| 뒷다리 (LH/RH) | 지면 지지 | 정적 리그(Coxa+Femur+Tibia+Tarsus1), 발이 world z=0에 닿도록 배치 |
| 중간다리 (LM/RM) | 접어서 몸 옆에 고정 | 정적 리그, Femur -120°/Tibia -150°(원본 조인트 그리드서치, 완전히 편 상태 대비 약 87% 접힘), 지면 비접촉·장식 |
| 앞다리 (LF/RF) | 배트 그립(동적) | 매 렌더 프레임 `envs/fly_visual.py`의 3구간 IK(Femur+Tibia→"손목", Tarsus1→그립)로 재계산, mocap body(관절·DOF 없음) |

**전신 동일 배율(K=400)**: 이전(I-08a)에는 좌표 버그로 실측 어깨-그립 거리가
과대평가돼 앞다리만 K=1200(3배)으로 확대했었다. I-08a-fix에서 좌표 버그(아래
3절)를 고치자 몸통과 동일한 K=400의 자연 팔 길이(Femur+Tibia+Tarsus1=0.580m)만
으로 전체 에피소드 내내 도달 오차 0을 확인했다 — 부위별 확대는 하지 않는다.

## 3. 좌표계 — 반드시 지킬 것

I-08a-fix가 고친 근본 원인(재발 방지를 위해 여기 명시):

1. **부모 world offset 상쇄**: fly_visual body가 `batter_body`(world z=1.0)
   안에 중첩되므로, 발을 world z=0에 놓으려면 `local_pos.z = -batter_world_z -
   min_sole_z`로 부모 offset을 명시적으로 빼야 한다. 로컬 z=0만 맞추면 실제로는
   1m 위에 뜬다.
2. **geom origin ≠ mesh surface**: 접지/그립 측정은 geom의 로컬 원점이 아니라
   `envs/fly_visual_mesh.py`의 `geom_world_vertices()`로 **실제 STL 정점을
   world로 변환**한 값을 써야 한다. 원점 기준으로는 최대 8cm까지 어긋난다.
3. **회전 피벗 재중심화**: 회전 피벗(FlyBody 원점)이 몸통(Thorax) 자신의
   중심이 아니면 회전만으로 몸통이 수평으로 밀려난다(최대 0.52m 확인됨) —
   Thorax 회전 후 위치가 `batter_body` 기준 (0,0)에 오도록 XY를 재중심화한다.

## 4. 타자 자세 — 옆선·머리만 투수 방향

월드 좌표로 정의한다(카메라 화면 기준 아님). 홈→투수 수평 벡터를 p, 몸통의
해부학적 전방을 수평 투영한 벡터를 f로 둔다.

- **몸통**: f·p가 약 90°(설계 허용 80~100°) — 몸은 투수에게 옆면을 보인다.
  양 어깨를 잇는 축은 투구 방향과 대략 평행.
- **머리**: 목 부착점을 피벗으로 별도 회전(눈·더듬이·입 등 Head 자식도 함께
  변환). 시각적 전방축이 투수 릴리스 위치(RELEASE=(16.5,0,1.8))를 향하도록
  한다(설계 허용 오차 10° 이하).
- 몸통/머리 회전은 접지·박스 안 배치·양손 도달성에 영향을 주므로 매번
  재계산해 검증한다. 물리 `batter_body`/배트 피벗은 통째로 돌리지 않는다.
- 이 자세는 준비~접촉까지 고정이다. 공을 매 순간 추적하는 머리 애니메이션,
  스윙 중 몸통 회전은 구현하지 않았다(새 능동 관절도 추가하지 않음).

의인화된 시각 자세이며 실제 초파리의 자연 자세·목 가동범위 재현이 아니다.

## 5. 색상

flygym==1.2.1의 `flygym/config.yaml` appearance와 `flygym/fly.py`의
`_set_geom_colors`를 기준으로 부위별 원본 material/texture를 그대로 적용했다
(임의 단색이 아님).

| 부위 | 원본 설정 |
| --- | --- |
| 눈 | rgba (0.67, 0.21, 0.12, 1), 적갈색 |
| 머리/흉부 | texture rgb1/rgb2 (0.59, 0.39, 0.12), 황갈색 + 표면 패턴 |
| 다리 | 구간별 황갈색 texture, femur→tibia→tarsus 점차 밝아짐 |
| 복부 | 갈색~밝은 갈색 gradient |
| 날개 | rgba (0.8, 0.8, 0.9, 0.3), 반투명 |

동적 mocap 앞다리에도 동일 매핑을 적용한다. 원본 config/loader 버전·해시와
가져온 항목은 manifest에 기록돼 있다.

## 6. 물리 불변성 (외형은 물리에 영향을 주지 않음)

`batter_torso`(원래 캡슐 타자)는 질량·충돌·제외 규칙을 그대로 두고 rgba
alpha만 0으로 만들어 렌더링만 숨긴다. 모든 파리 geom은 `contype=0
conaffinity=0` + 질량 없음. mocap 갱신은 `mj_forward()`만 재호출하며(qpos/qvel
적분 없음) 배트/공 동역학에 관여하지 않는다. **검증 방법**: mid_mid 정확값
회귀 테스트로 `bat_contact_vx`/`exit_velocity_xyz`/`forward_flight_success`가
외형 변경 전후 소수점까지 동일함을 확인한다(`tests/test_baseball_b1_env.py`).

## 7. 검증 기준과 현재 통과 상태

| 기준 | 목표 | 현재 측정값 |
| --- | --- | --- |
| 뒷발 world sole z | ≤5mm | LH −1.1e-7m, RH 3.9e-4m |
| 앞발-그립 오차 | ≤5mm, 전 에피소드 매 스텝 | 항상 <1mm, 도달 초과 0 |
| 다리 미끄러짐 | 0 (정적 리그, 관절 없음) | 0 (원천적으로 불가능한 구조) |
| 몸통-투수 각 | 80~100° | 90.00° |
| 머리-릴리스 각 오차 | ≤10° | 4.72°(실제 배치 씬 기준) |
| 타자 박스 안 배치 | 예/아니오 | 확인됨 |
| 전신 동일 배율 | K=400 전 부위 | 확인됨(앞다리 3배 확대 없음) |
| 물리 정확값 불변 | 소수점까지 동일 | 확인됨 |

## 8. 알려진 남은 문제 (임의로 고치지 않고 그대로 보고)

- **서 있는 키 증가**: 약 1.53m(이전 2다리+시각 버그 시절 1.17m) — 뒷다리
  2개 지지로 바뀐 부수 효과. 목표 신장을 정한 적은 없다.
- **목 관절 고정**: 시선 추적 없음, 머리는 준비 자세에서 고정.
- **Tarsus 단순화**: 대부분 1분절로 단순화(원본은 여러 분절).
- **팔꿈치 굽힘 평면**: world -Z로 임의 선택, 해부학적 근거 아님.
- I-08b(전신 역학 통합)·나머지 8코스 재보정·RL은 범위 밖.

## 9. 진단 자산

`runs/env002-b1-neuromechfly/mid_mid/`(gitignore, 로컬)에 정면·측면·그립
근접 정지화면(준비/접촉/정착)과 영상, `stance_axis_diagnostic.png`(몸통 전방·
어깨축·머리 방향·투수 벡터 오버레이)가 있다. manifest는
`docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json`.

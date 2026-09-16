# 현재 상태

## 2026-09-16 — I-08a-style + I-07c-score + I-07c-swing 완료: 옆선 자세·원본 색상, 비거리 점수, 스윙 windup 개선 (최신)

[통합 규약](../design/BATTING-QUALITY-AND-SWING.md)의 A(자세·색상)→B(점수/보상)→C(스윙) 순서를 완료했다. 8코스 확대·B2·변화구·RL 훈련·전신 역학(I-08b)은 진행하지 않았다. 상세 수치·코드 경로는 `docs/records/VALIDATION_LOG.md`(동일 날짜 항목)에 있다. 여기서는 **테스트 통과**와 **실제 외형·타격 개선**을 구분해 보고한다.

**A. 옆선 자세·원본 색상** — 실제 외형 개선: 몸통이 투수에게 옆면(f·p=90.00°, 설계 허용 80~100°)을, 머리만 투수 릴리스 지점(RELEASE=(16.5,0,1.8))을 향하도록(실제 배치 씬 기준 오차 4.72°, 설계 허용 10° 이내 — 빌드 스크립트가 보고했던 고립 프로브 기준 0.00°와는 다른 숫자이니 혼동 주의) 렌더로 확인했다. flygym==1.2.1의 `config.yaml`(SHA-256 기록) appearance를 그대로 옮겨 45개 메시 전부에 원본 부위별 재질(황갈색 몸통/다리, 적갈색 눈, 반투명 날개)을 적용했다. 두 발 접지·양손 그립·동일 배율·기존 타격 물리 불변은 전부 재검증(테스트 통과 + 직접 렌더 확인)했다. 진단 이미지: `runs/env002-b1-neuromechfly/mid_mid/stance_axis_diagnostic.png`.

**B. 비거리 점수/`forward-carry-v1` 보상** — 순수 계산 로직 추가(물리에 영향 없음, qpos/qvel 불변을 직접 확인): `carry_distance_m`(첫 접촉~첫 착지)/`landing_range_from_home_m`/`scoring_valid`(전방90° 부채꼴+정상분리+재접촉0)/`batting_score`(유효 시 carry, 아니면0)/`status`("complete"/"incomplete"/미확정 시 null 점수)를 `info`에 추가했다. 기존 `reward_terms`(활성, 기본값 `batted-ball-v1` 유지, 하위호환 무변경)와 별도로 `forward_carry_v1.reward_terms`를 항상 병기해 신·구 보상을 같은 episode에서 비교 가능하게 했다. RL 훈련은 시작하지 않았다.

**C. 스윙 windup 개선** — 실제 타격 개선(테스트 통과와 별개로 눈으로/영상으로도 확인): 기존 준비각 -1.9rad을 관절범위(`bat_hinge` [-2.0,2.0], 불변) 안에서 -1.96rad까지 넓히고 트리거를 재계산했다. gear/질량/관성/재료/dt/투구는 전부 고정, 목표 접촉각(ALIGNMENT, 방향무관 기하값)도 불변 — 오직 "얼마나 뒤에서 준비해 가속 구간을 길게 쓰는가"만 바꿨다. 결과(중앙 mid_mid, 동일 oracle): 접촉점 속도 7.19→7.62m/s, exit_speed 8.53→8.61m/s, carry 5.82→8.48m, **batting_score +46%**, 정착시간 0.431s(0.5s 목표 이내)·정착 후 p-p 4.25e-5rad(0.02rad 목표 이내) 유지, 두 발 접지·양손 그립 전 구간 재확인(reach_error 항상 0). **정직하게 보고하는 한계**: (1) 발사각이 14°→41°로 크게 높아졌다 — 더 빠른 직선타가 아니라 궤적 형태 자체가 달라진 것이며 의도적으로 고른 결과가 아니라 트리거 재계산의 부산물이다. (2) 트리거 시각을 단 한 control step(0.005s)만 어긋나도 판정이 뒤집히는 취약성을 발견했는데, **이는 기존(prep=-1.9) 스윙에도 이미 있던 문제**이며 이번에 고치지 않았다(별도 재설계 과제로 기록). 전후 비교: 영상(`runs/env002-b1-i07c-swing/{before,after}/`, 동일 카메라 1×, 화면에 실거리/점수/상태 오버레이), 배트 궤적 그림(`runs/env002-b1-i07c-swing/bat_tip_trajectory_before_after.png`), 수치표(`runs/env002-b1-i07c-swing/final_comparison_table.json`).

**테스트**: `pytest tests/` **87 passed**(A/B/C 전체 완료 시점, 신규 23개: B 19개 + C 4개). 옛 물리 회귀 테스트 2개는 새 수치로 재고정하되 이전 값·변경 이유를 테스트 docstring에 그대로 남겼다(옛 정답만 바꾸고 통과라 부르지 않기 위함).

**남은 문제**: 나머지 8코스는 여전히 I-07b-fix 이전 기준으로 미보정(원래도 "사용 금지"), tilt축 0.5s 정착 목표 미충족(I-07b-followthrough에서 이미 보고된 gear=6 한계, 이번 범위 밖)은 그대로 남아 있다. 트리거 타이밍 취약성·41° 발사각은 위에 정직하게 남겼다.

## 2026-09-16 — I-08a-fix: 외형 좌표 버그 수정·자세 재정의 완료

- [외형 재검토와 수정 규약](FLY-VISUAL-REVIEW.md)의 요구를 그대로 따랐다. I-08b(전신 역학)·나머지8코스·B2/변화구/RL은 진행하지 않았다.
- **근본 원인 확인**: 뒷발이 떠 있던 이유는 `scripts/build_fly_visual_asset.py`가 발을 fly_visual의 **로컬** z=0에 맞췄는데, 그 body가 **world z=1.0인 batter_body** 안에 중첩되면서 접지 보정이 상쇄되지 않고 그대로 1m 위로 올라간 것이었다(좌표계 혼동). 추가로 geom **origin**을 발바닥으로 취급해 실제 메시 최하단(발바닥) 대비 약8cm를 더 놓쳤다. 앞다리는 이 문제 때문에(도달거리를 잘못된 위치에서 측정) 실제로는 불필요했던3배 확대를 했었다.
- **좌표 수정**: (1) `local_pos.z = -batter_world_z - min_sole_z`로 부모의 world z를 명시적으로 상쇄, (2) `scripts/fly_mesh_utils.py`를 새로 만들어 geom origin이 아니라 **실제 STL 정점을 world로 변환**해 발바닥·손끝을 측정, (3) 회전 피벗(FlyBody 원점)이 몸통(Thorax) 자신의 중심이 아니어서 회전만으로 몸통이 X축으로 약0.52m 밀려나던 것을 발견해 **XY 재중심화**(Thorax 회전후 위치가 batter_body 기준(0,0)에 오도록 fly_visual의 pos.xy를 보정)를 추가했다.
- **자세 재정의(사용자 지시대로)**: 뒷다리(LH/RH)만 지면 지지, 중간다리(LM/RM)는 몸 옆으로 접음(Femur -120°·Tibia -150°, 원본 조인트 그리드서치로 탐색, 완전 편 상태 대비 약87% 접힘), 앞다리(LF/RF)만 동적 그립. 기존 "4다리 지지" 설계를 대체했다.
- **앞다리 3배 확대 제거**: 좌표 버그를 고치고 나니 몸통과 **동일한 K=400**의 자연 팔 길이(Femur+Tibia+Tarsus1=0.580m)만으로 **전체 에피소드(준비→가속→접촉→감속→정착) 내내 도달 오차 0** — 이전 보고된 "1.265m 필요"는 좌표 버그가 만든 착시였다(실측으로 확인, 팔을 늘리지 않고도 해결됨을 직접 검증했으며 도달 불가능 사례는 없었다).
- **앞다리에 Tarsus1(발끝) 복원**: 기존엔 Femur+Tibia만으로 Tibia 끝을 "손"으로 썼으나, 이제 3구간 IK(Femur+Tibia로 "손목"까지, Tarsus1이 손목→그립까지)로 실제 발끝 메시가 그립을 잡는다.
- **검증(설계 문서의 완료 기준대로)**: 뒷발 world sole z 오차(LH: -1.1e-7m, RH: 3.9e-4m) 5mm 기준 이내, 타자 박스 안(좌표로 확인); 다리는 정적 리그라 준비~정착 간 미끄러짐이 원천적으로 0(관절 없음, 실측으로도 확인); 앞다리 발끝-그립 오차 <1mm(기준 5mm)를 전체 에피소드 매 스텝 확인, 도달 초과 0; 앞다리 메시 스케일이 몸통과 동일함을 직접 확인(3배 확대 제거); 물리 불변성(정확값 회귀)은 그대로 유지.
- 정면·측면·그립 근접 정지화면(준비/접촉/정착)과 영상을 `runs/env002-b1-neuromechfly/mid_mid/`(stills/ + park_wide/behind_catcher/batter_side/grip_closeup.mp4)에 재기록.
- manifest(`docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json`)를 좌표 수정·자세 재정의·45개 메시(43개 아님, LFTarsus1/RFTarsus1도 이제 사용)·동일 스케일 근거로 갱신.
- `pytest tests/` → **64 passed**(B1 30개: 기존26 + 신규4), `ruff` 클린.
- **남은 문제(외형)**: 서 있는 키(약1.53m)가 이전(1.17m)보다 커짐(2다리 지지로 변경된 부수 효과, 목표 신장을 정한 적은 없음); 머리 목 관절 고정·시선 없음; 다리 Tarsus 대부분 1분절로 단순화; 팔꿈치 굽힘 평면은 임의 선택(world -Z, 해부학적 근거 아님); I-08b·나머지8코스·RL은 범위 밖.
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — I-08a 외형 수용 실패: 수정 우선

원본 wheel/STL 동일성은 확인했지만 뒷발이 약0.92m 떠 있고 앞다리만3배 확대됐다. 사용자 자세 기준은 앞다리2개 그립·뒷다리2개 접지·중간다리 접기다. **다음 작업은 I-08a-fix**이며 기존 완료 보고보다 [외형 재검토와 수정 규약](FLY-VISUAL-REVIEW.md)을 우선한다. 과거 기록은 보존한다.

## 2026-09-16 — I-08a: NeuroMechFly 연구용 시각 모델 적용

- `docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md`의 C(연구용 파리 모델)를 진행했다. **나머지 8코스 재보정·전신 역학 통합(I-08b)·강화학습은 진행하지 않았다.**
- **자산 도입**: PyPI `flygym==1.2.1`(Apache-2.0, NeLy-EPFL)을 `pip download --no-deps`로 받아 실제 사용한 메시 43개(STL)와 라이선스만 `envs/assets/mesh_neuromechfly/`에 vendoring했다. 버전·해시·출처·재획득 절차는 `docs/design/ENV-002-NEUROMECHFLY-ASSET-MANIFEST.json`과 `THIRD_PARTY_NOTICES.md`에, 연구 데이터 정책은 `docs/RESEARCH_SOURCES.md`에 기록했다. NeuroMechFly는 성체 암컷 개체이며 신경 서킷 트랙의 MaleCNS(수컷)와는 별도 데이터 계층임을 명시했다.
- **일어선 자세**: 원본 리그(몸통이 수평인 정상 곤충 자세)를 MuJoCo 자체 forward kinematics로 재포즈했다 — 전체를 Y축 -90°로 회전(머리-꼬리 축을 수직으로) 한 뒤, 6개 다리 각각의 Coxa 관절에 동일 축 +90° 보정을 걸어(원본과 동일 축이라 정확히 상쇄) 다리 모양은 원본의 "지면 지지" 형태를 유지한 채 몸통만 세웠다. 시행착오(평탄화 추출 방식은 MuJoCo의 메시 배치 합성을 이중 적용해 머리가 몸통에서 분리되는 버그를 냄 → 원본의 중첩 body 트리를 직접 편집하는 방식으로 전환해 해결)를 `docs/records/VALIDATION_LOG.md`에 남겼다.
- **양손 그립(동적)**: 앞다리 2개(Femur+Tibia만 사용, Tarsus 생략)는 정적 리그에서 제외하고 매 렌더 프레임 `envs/fly_visual.py`의 2관절 IK로 자세를 계산해 mocap 바디 4개(관절·DOF 없음)에 적용한다 — 고정된 어깨(LFCoxa/RFCoxa)에서 배트 손잡이 위의 이동하는 그립 사이트(`grip_L`/`grip_R`, 손잡이 쪽 x=0.05/0.12)까지 매 스텝 추적. 실측 어깨-그립 최대거리(1.265m, 준비자세가 고정 어깨에서 멀기 때문)가 몸통 스케일(K=400)의 팔 자연 길이(0.489m)를 크게 초과해, 앞다리 메시만 K=1200으로 별도 확대했다 — 명시적으로 기록한 스케일 조정.
- **중간·뒷다리 4개**: 정적 리그에 포함(Coxa+Femur+Tibia+Tarsus1, Tarsus2-5는 생략), 발이 지면(z=0)에 닿도록 전체를 이동. 타자 박스 안에 서 있음(원본 곤충의 다리 벌림 형태를 그대로 물려받아 좌우로 다소 모여 있음 — 실제 파리 행동 재현이 아닌 캐릭터 설정임을 명시).
- **물리 불변성**: `batter_torso`는 질량·충돌·제외 규칙을 전혀 건드리지 않고 rgba alpha만 0으로 만들어 렌더링만 숨겼다(batter_body는 관절이 없어 질량이 애초에 동역학에 무관함도 확인). 모든 파리 geom은 contype=0/conaffinity=0/질량 없음. **중앙 직구(mid_mid) 정확값 회귀 테스트**로 검증: bat_contact_vx·exit_velocity_xyz·forward_flight_success가 I-07b-followthrough 시점 기록과 소수점까지 동일. `mj_forward()` 재호출(mocap 갱신 후 파생량만 갱신, qpos/qvel 적분 없음)이 물리에 영향 없음도 실행으로 확인.
- **회귀**: `tests/test_baseball_b1_env.py`에 4개 신규(시각 geom 비충돌 확인, 중앙 직구 정확값 불변, 그립 도달성, 등) — `pytest tests/` → **61 passed**(B1 27개+기존34개... 정확 수는 커밋 diff 참고), `ruff` 클린.
- **영상**: `demos/record_baseball_b1_neuromechfly.py` → `runs/env002-b1-neuromechfly/mid_mid/{park_wide,behind_catcher,batter_side,grip_closeup}.mp4`(동일 200fps 실시간 축, 준비→타격→정착→착지 전체).
- **남은 문제(외형)**: 중간·뒷다리가 좌우로 모여 있어 안정적인 4다리 지지처럼 보이지 않음(원본 곤충 다리 벌림을 그대로 사용); 앞다리가 몸통 대비 과도하게 길고 가늚(스케일 불일치의 시각적 대가); 머리 관절(3DOF)은 원본 정지각 고정, 시선 타기팅 없음; Tarsus 생략(발가락 단순화); I-08b(전신 역학 통합)·나머지 8코스·RL은 범위 밖.
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — I-07b-followthrough: 팔로우스루 안정화·접촉 재료 설명 정정

- `docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md`를 먼저 읽고 A(팔로우스루 안정화)·B(접촉 설명 정정)를 진행했다. **C(NeuroMechFly 시각 모델)와 나머지 8코스 재보정은 진행하지 않았다** — 지시대로 이 둘이 먼저 안정화된 뒤 진행한다.
- **원인 확인**: Codex가 지적한 5회 토크 부호 반전은 실제로 재현됐다 — 원인은 `OracleAimController`가 목표각 통과 후에도 `1.0 if target>angle else -1.0`를 계속 반환해 목표각 주변에서 영원히 bang-bang을 반복하는 구조였다. **접촉(0.459~0.468s) 자체의 배트 속도·타구 결과에는 영향이 없었다** — sign flip은 전부 분리(0.468s) 이후에 시작됐다(최초 flip t=0.565s).
- **`_SwingAxis`/`_TiltAxis` 상태기계 도입** (`controllers/baseball_b1.py`): prepare→accelerate→brake→hold. accelerate는 접촉 관측 또는 자기 자신의 목표각 통과(미래 정보 아님, 관측 가능한 스윙 진행 조건)로 딱 1회 래치되며, 이후 절대 accelerate로 되돌아가지 않는다. 스윙축은 감쇠 PD(brake), 틸트축은 시간최적 bang-bang(brake) — 두 축의 물리가 근본적으로 달라 하나의 게인 세트로 안 됐다(아래).
- **스윙축(gear=30) 안정화 — 설계 목표 달성**: 실측 a_max=134.4rad/s²(ctrl=1)로 유효관성 I≈0.223kg·m² 역산, kp=8·ζ=0.9 임계감쇠 PD로 목표 팔로우스루각(-0.898rad, 접촉각+0.4rad)에 수렴. **래치 후 0.435s 안에 |qvel|<0.2rad/s 도달(설계기준 0.5s 이내), 이후 0.2s간 각도 peak-to-peak=1.0e-5rad(기준 0.02rad 이내), 오버슈트 없음.**
- **틸트축(gear=6) — 설계 목표 미달, 원인은 실제 토크 한계**: 초기에 스윙과 같은 방식(감쇠 PD)을 시도했으나 kp를 4~500까지 올려도 결과가 전혀 안 바뀌었다 — 실제 교란(충돌 반동으로 각속도 -3.3rad/s, 각도 변위 0.4rad)에서는 ctrl이 항상 ±1로 포화되어 있어 PD 게인 선택 자체가 무의미했다(사실상 bang-bang과 동일). 실측 a_max=10.07rad/s²(ctrl=1, 기하 추정치 27.7의 절반 이하 — 실제 관성이 예상보다 큼)로 시간최적 bang-bang을 적용해 반전/발산은 제거했지만(각도 최종 -0.0002rad, 속도 0.06rad/s로 실질 수렴), **정착에 실제로 약 0.6~0.9s가 걸려 0.5s 설계 기준을 충족하지 못한다** — gear=6의 실제 구동력 한계이며 튜닝으로 해결되는 문제가 아니다(정확한 0.5s 충족은 gear 재보정이 필요, 이번 범위 밖). 타구 판정(공이 착지)이 먼저 끝나 에피소드 안에서는 최종 40스텝 연속 수렴 확인이 완료되지 못했다.
- **중앙 직구 결과는 완전히 동일하게 보존됨**: bat_contact_vx=+6.980, exit_velocity_xyz=(+7.291,+3.924,+2.068), forward_flight_success=True, 착지 (5.545,2.785,0.036) — 팔로우스루 재작성 전/후 소수점까지 동일(접촉 이전 로직은 변경하지 않았기 때문).
- **2차 발견 — `FixedPoseAlwaysSwing` 방향 오류**: 이전 I-07b-fix에서 놓친 잔여 버그. 이 baseline의 ctrl이 여전히 `-1.0`(구 역방향 스윙 기준)이라 새 `prep_swing=-1.9`에서는 -2.0 관절한계로 그대로 박혀 접촉이 전혀 없었다. `+1.0`으로 수정.
- **B. 접촉 재료 설명 정정**: 실제 ball–bat 접촉의 solref는 **(0.0051, 0.505)**이며 이는 ball_geom 단독값 (0.0002,0.01)이 아니라 **동일 priority·solmix인 두 geom의 산술평균**(ball 0.0002·bat 0.01 → 0.0051; solimp[2]도 0.0001/0.001→0.00055로 일치)임을 직접 측정해 확인했다. 기존 "softer/lower-priority가 이긴다"는 XML 주석 설명은 틀렸다 — [MuJoCo 공식 문서](https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters)의 혼합 규칙대로 정정했다. refsafe는 활성 상태이며 실측 timeconst(5.1ms)가 안전 하한(2×dt=0.5ms)보다 훨씬 커 이번 설정에서는 clamp가 작동하지 않았음도 확인했다.
- **calibration manifest 신규**: `docs/design/ENV-002-B1-contact-calibration.json`에 solver 설정, 선언된/실측 접촉 파라미터, gear 스윕 표, 실측 a_max, 중앙 직구 최종 결과를 모두 기록했다(9코스 중 mid_mid만 검증됨을 명시).
- 영상·timeline 재기록: `runs/env002-b1-fix-verification/mid_mid/{park_wide,batter_side}.mp4` + `timeline.json`(각도·속도·ctrl·state·접촉 per-step 기록).
- `pytest tests/` → **58 passed**(B1 20개: 기존16 + 팔로우스루/접촉재료 신규4), `ruff` 클린.
- **남은 문제**: 틸트축의 0.5s 설계 기준 미충족(gear 재보정 필요, 보류); NeuroMechFly 시각 모델(I-08a) 미착수; 나머지 8코스 재보정 미착수; B2·변화구·RL은 여전히 범위 밖.
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — 중앙 타격 재현·팔로우스루 진단·외형 계획

- 현재 미커밋 수정본에서 중앙 oracle의 전방 타격/출구 속도/착지를 Codex가 재현했다.9코스 전체 완료로 확대하지 않는다.
- 접촉 후 최대 스윙 토크 부호5회 반전, 각도 약[-1.599,-0.960]rad. 충돌 반동과 목표각 bang-bang의 반복 작용을 분리해 안정화한다.
- 실제 ball–bat solref=(0.0051,0.505): XML ball 단독값(0.0002,0.01)과 다르며 혼합 규칙 설명 정정 필요.
- [새 계획](../design/FOLLOWTHROUGH-AND-FLY-MODEL.md): 팔로우스루 감속/정착 → NeuroMechFly 연구용 메시의 시각 적용 →8코스 재보정. 전신 역학 통합은 별도 단계.
- 이번 작업에서 구현 코드는 바꾸지 않았고 전체 테스트/영상 검증이나 asset 취득은 하지 않았다.


## 2026-09-16 — I-07b-fix: 중앙 직구(mid_mid) 실제 타구 검증 완료

- `docs/records/B1-BATTING-REVIEW.md`와 `docs/design/ENV-002-BATTED-BALL.md`를 먼저 읽고 진행했다. **B2·변화구·강화학습 훈련은 진행하지 않았고, 9코스 확장도 시작하지 않았다** — 지시대로 중앙 직구만 검증했다.
- **스윙 방향**: `prep_swing`을 1.0(과거) → **-1.9**로 바꾸고, 증가하는 각도(양의 ctrl) 방향으로 스윙하도록 고쳤다. 같은 접촉각(-1.298rad)이라도 회전 방향이 반대이면 배트 접촉점 속도의 x부호가 반대임을 직접 확인(θ=-1.298에서 dθ/dt=+1→(+0.819,+0.229,0), dθ/dt=-1→(-0.819,-0.229,0))했고, 새 prep 각에서 관통 없음·양의 ctrl이 각도를 증가시킴을 확인 후 반영했다.
- **접촉-only 판정 제거**: `envs/baseball_b1_env.py`를 phase 상태기계(`pitch → bat_contact → batted_ball → done`)로 재작성했다. 접촉은 더 이상 종료 사유가 아니며, 2ms 연속 무접촉으로 분리를 확정하고 그 시각의 공 속도를 exit velocity로 기록, 착지(`batted_ball_landing`)까지 같은 스텝 루프 안에서 추적한다. 재접촉 시 분리 후보를 취소하는 로직, 50ms 초과 시 `prolonged_contact` 진단 플래그도 구현했다. `docs/design/ENV-002-BATTED-BALL.md`의 지표(contact_occurred, bat_contact_vx, exit_velocity_xyz, exit_speed, launch/spray angle, first_landing_xyz, carry_distance_xy, forward_flight_success 등)를 전부 `info`에 채운다.
- **물리 재보정(중요, 예상 밖 발견)**: 스윙 방향만 고쳐서는 여전히 실패했다 — 접촉점 속도가 양수(+6.7 m/s)여도 공은 거의 그대로(-31 m/s대)로 계속 진행했다. 원인은 두 가지였다: (1) 기본 `solref="0.01 1"`(10ms 임계감쇠)가 35m/s 공과 배트의 1~3서브스텝(0.75~1ms)짜리 접촉에 비해 너무 무름 — 공 지오멤에 `solref="0.0002 0.01"`(더 뻣뻣하고 저감쇠/바운시)로 재정의. dt를 5e-6s(25배 더 세밀)까지 낮춰도 결과가 수렴해 변하지 않아 이산화 문제가 아니라 실제 접촉 모델 거동임을 확인했다. (2) gear=12(과거, 타이밍 맞추기용으로만 보정됨)는 접촉점 속도를 최대 ~7m/s밖에 못 냄 — 순수 탄성 충돌 추정으로는 이 정도도 충분해야 하나 실제로는 거의 무접촉처럼 그레이징됐다. gear∈{12,20,30,45,60} × 트리거 시각 탐색 결과 **gear=30**이 처음으로 확실한 양의 exit velocity를 냈다(gear=45/60은 목표각을 너무 빨리 지나쳐 탐색 해상도로 못 맞춤). 접촉 법선 방향(거의 X축 정렬)도 트리거 시각에 매우 민감함을 확인했다(구체 수치는 VALIDATION_LOG).
- **중앙 직구 최종 검증 결과**(`OracleAimController`, `envs/assets/baseball_park_b1.xml`의 gear=30·공 solref 반영): bat_contact_vx=+6.98 m/s, exit_velocity_xyz=(+7.29, +3.92, +2.07) m/s, forward_flight_success=True(x=5m 기준면을 |y|≤x 부채꼴 안에서 통과), 착지 (5.54, 2.78, 0.036), end_reason=batted_ball_landing. 영상: `runs/env002-b1-fix-verification/mid_mid/{park_wide,batter_side}.mp4`(control_dt 기준 200fps로 일관된 실시간 축, 기존 20배 배속 불일치 버그 없음).
- **보상**: `RewardWeights`를 `batted-ball-v1`로 교체했다(hit_success/contact_velocity 필드 제거, forward_flight_success=+10 1회, miss=-3, control_cost=-0.2∫u²dt는 형식 그대로 유지).
- **9코스 중 mid_mid만 재보정됨**: `CROSSING_TIME_S`는 mid_mid만 새 값(0.094091, 0.0)으로 갱신했고 나머지 8개는 과거(gear=12·역방향 스윙 기준) 값 그대로 남겨 코드 주석과 문서에 "미검증/사용 금지"로 명시했다. `controllers/baseball_b1.py`는 구조 변경 없이 새 prep_swing/gear에서도 그대로 동작함을 확인(문서만 갱신).
- `pytest tests/` → **54 passed**(B1 16개 전면 재작성 + 기존 38개), `demos/record_baseball_b1_episode.py`(9코스 baseline/영상 러너)는 아직 갱신하지 않았다 — 9코스 확장 단계에서 다룬다.
- **남은 문제**: 8개 코스의 `CROSSING_TIME_S`/게인 재탐색, `demos/record_baseball_b1_episode.py`의 `info["hit"]` 기반 요약 갱신, exit velocity/착지 위치의 dt 수렴 검증(BATTED-BALL.md 5.3)은 다음 단계(9코스 확장)로 미뤘다. gear=30·solref 조합이 다른 8개 코스에서도 동일하게 작동하는지는 미확인.
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — 타격 방향 오류 확인

- 기준 c812766. Codex가 저장 영상 프레임·코드·9코스 oracle을 확인했다. 접촉 시 배트 vx가 모두 음수이며, 마지막 ctrl 유지100ms 진단 연장 뒤에도 공 vx가 모두 음수였다.
- 이전 성공률은 접촉률로 제한한다. 실제 인필드 방향 타구 성공은 미검증/미구현이다. 원인과 수치는 [검토](B1-BATTING-REVIEW.md).
- 다음은 I-07b-fix. 접촉 종료를 타구 추적으로 바꾸고 스윙 방향·판정·보상·영상 시간축을 고친다. 새 코드 구현은 하지 않았다.


## 2026-09-16 — I-07b B1 완료: 배트 조준(틸트)과 9개 코스 (최신)

- 구현 전 `docs/design/ENV-002-B1-courses.md`에 코스 좌표·조준 방식·평가 목록·통과 기준을 먼저 고정한 뒤 구현했다(§4는 이후 실제 시행착오로 갱신).
- B0(`envs/baseball_env.py`, `envs/assets/baseball_park.xml`)는 **전혀 수정하지 않았다** — B1은 별도 파일(`envs/assets/baseball_park_b1.xml`, `envs/baseball_b1_env.py`)로 분리해 회귀 위험을 차단했다.
- **조준 기구**: 기존 수평 스윙에 자식 힌지 `bat_tilt_hinge`(스윙과 함께 회전하는 로컬 -y축)를 추가해 높이 조준. 별도 gear 재보정(6, 스윙의 12와 다름). 틸트축은 스윙축과 달리 **중력 토크가 있어**(0.16초 방치 시 0.21rad 처짐) 능동 유지가 필요함을 확인했다.
- **9개 코스**: zone 중심(0.4318,0,1.0), 반폭0.2159m(=plate 반폭), 반높이0.35m(=스트라이크존 0.65~1.35m). 릴리스·수평속도35m/s는 B0와 동일, 9개 코스 전부 도달시간 T=0.45909s로 동일.
- **도달성(oracle) — 9/9 코스 100%**: 도달 불가능한 코스는 없었다(몸 구조/구동 한계 재설계 불필요). 시행착오 끝에 "두 축을 동시에 실제 구동한 채 코스별 트리거 시각을 직접 탐색"하는 방식으로 정착했다 — 연속 PD, 2단계 bang-bang, 축별 독립 계산은 전부 실패했고(스윙-틸트 관성 결합을 무시했기 때문) 문서에 그대로 남겼다.
- **관측 기반(scripted) — 9개 중 5개만 100%, 4개는 0%**: 선형 조준 fit의 근사오차 때문(코스별 실패 원인을 표로 기록). oracle(9/9)과 명확히 분리 보고했다 — oracle은 도달성 진단 전용, scripted가 "공정한" 기준선.
- **baseline 비교(9코스 × 5종 + oracle)**: zero_torque/held_rest/random/always_swing_fixed_pose는 9개 코스 전부 0% — 특히 "조준 없이 항상 스윙"도 mid_mid조차 못 맞혀, 조준 기능 자체의 기여를 확인했다.
- 코스별 영상 9×4카메라를 `runs/env002-b1-demo/video/<course>/*.mp4`에 저장(hit 5개, miss 4개 모두 기록).
- `pytest tests/` → **53 passed**(B1 신규15 + 기존38), `ruff` 클린.
- **남은 문제**: scripted 선형 fit의 4개 코스 실패는 수정 안 함(측정·보고만); 왼손 타자 profile 미구현; 스윙-틸트 관성 결합의 정량 해석은 안 함; 구속 변화·변화구·선구안·강화학습 훈련은 진행 안 함(사용자 지시).
- 상세 실행 증거는 `docs/records/VALIDATION_LOG.md`.

## 2026-09-16 — I-07a-1 완료: B0 접촉 수렴·보상·구장 대조

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

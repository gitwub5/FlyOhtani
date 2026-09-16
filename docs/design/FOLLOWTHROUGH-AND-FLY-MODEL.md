# 팔로우스루 안정화와 NeuroMechFly 외형 도입

2026-09-16 · 계획/인계 문서. 구현은 Claude가 진행한다. 검토 대상은 c812766 이후의 현재 미커밋 중앙 타격 수정본이며, commit만으로 이번 상태를 재현할 수 없으므로 구현자가 소스 해시/변경분을 저장한다.

## 현재 결과의 판단

Codex가 중앙 oracle을 재실행해 bat_contact_vx=6.9798m/s, exit_velocity=(7.2909,3.9244,2.0676)m/s, forward_flight_success=true, landing=(5.5447,2.7847,0.03643)m, recontact_count=0을 재현했다. 중앙 전방 타구의 공학적 smoke는 성립한다. 다른8코스는 재보정 전이며 이 결과로 성공을 확대하지 않는다. 실제 야구 반발계수/안타/홈런 재현이 입증된 것은 아니다.

## A. 팔로우스루: 지금 안정화

현재 `controllers/baseball_b1.py`는 `_swinging` 이후에도 목표각보다 작으면+1, 크면-1을 계속 반환한다. `_hold`도 속도 감쇠 없는 높은 위치 이득이다. 접촉 뒤 중앙 oracle의 스윙 입력 부호는5번 바뀌었고, 각도는 약[-1.599,-0.960]rad 범위에서 왕복했다. 접촉 직후 angular velocity의 반전에는 실제 충돌 반동도 들어 있으므로 모든 흔들림을 하나의 원인으로 단정하지 않는다. 그러나 접촉각을 계속 최대토크로 추적하는 제어는 팔로우스루 정지 제어가 아니다.

### 다음 구현 I-07b-followthrough

- 제어기 상태를 prepare/accelerate/follow_through/brake/hold로 분리하고 한 스윙에서 상태를 역으로 되돌리지 않는다. 접촉각을 지나간 뒤 거기로 복귀하라는 bang-bang을 반복하지 않는다.
- contact 관측 또는 사전 정의한 스윙 진행 조건으로 follow_through를1회 latch한다. 놓친 공도 brake/hold로 진행해야 한다. 정답 코스/미래 분리시각을 관측 정책에 넘기지 않는다.
- 관절 한계와 몸 간섭에 여유 있는 후속 목표 자세를 고정한다. 위치오차와 각속도를 함께 쓰는 감쇠 제어(예: 제한된 PD 토크), 부드러운 목표궤적과 입력 변화율 제한을 적용한다. gains/limits는 gear30과 두 축 결합에서 새로 검증한다. 이전 PD 실패가 모든 감쇠 제어의 불가능성을 의미하지 않는다.
- 실제 상태 적분은 유지한다. 시각 프레임 smoothing으로 숨기거나 qvel=0/qpos 강제고정으로 팔을 순간 정지시키지 않는다. held_pose는 여전히 진단용이다.
- 중앙 접촉 직전 동작과 접촉 재료는 우선 고정하고 후속 제어를 변경한다. 실제 충돌 지속 중에는 후속 토크도 타구에 영향을 주므로 출구 속도/분리/착지를 다시 검증한다. 유효했던 과거 타구 수치를 목표값으로 강제하지 않는다.

수용 기준(설계값): 중앙 전방 타구 유지, 추가 ball–bat 재접촉0, 한계/몸 충돌로 정지하지 않음. 공 없는 동일 스윙과 miss에서도 제어기 진입 후0.5s 안에 각 축 |qvel|<0.2rad/s, 이후0.2s 동안 각도 peak-to-peak<0.02rad. 첫 충격 반동은 별도 보고하고 정착 뒤 반복적인 최대토크 반전을 허용하지 않는다. 각도/각속도/torque/state/contact timeline과 같은1×배율 영상을 남긴다. 물리 damping 변경은 별도 모델 변경이며 단순 시각적 수정으로 취급하지 않는다.

## B. 접촉 설명의 정정과 재료 고정

현재 XML ball의 solref는(0.0002,0.01)이지만 실제 ball–bat contact에서 확인한 값은 **(0.0051,0.505)**, solimp=(0.9,0.95,0.00055,0.5,2)였다. 동일 priority의 양의 solref는 solmix 가중평균을 쓰기 때문이다. XML 주석의 ‘softer/lower-priority’ 설명과 공 단독 값이 실제 접촉값이라는 해석은 수정해야 한다. [MuJoCo 공식 설명](https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters)

다음 작업에서 geom 설정/실제 contact 설정/solver timestep·refsafe를 모두 calibration manifest에 저장한다. 공의 설정 변경은 공–지면 등 다른 조합에도 영향을 준다. explicit pair로 분리할 경우 현재 실제 접촉값을 보존한 채 시작하고, 값이나 접촉검출 방식이 바뀌면 재보정한다. 수렴은 수치적 안정성 근거이며 실제 야구 재료의 정확성 증명은 아니다. 반발·에너지/impulse 검증 없이 단지5m gate를 통과하도록 재료를 계속 변경하지 않는다.

## C. 연구용 파리 모델: NeuroMechFly 선택

첫 외형은 [NeuroMechFly/FlyGym](https://neuromechfly.org/)로 정한다. 공식 설명은 실제 성체 암컷 파리의 micro-CT 기반 모델이라고 밝힌다. [공식 모델 API](https://neuromechfly.org/api_reference/flygym/compose/fly/neuromechfly/)에는 body segment STL과 rigging 설정이 있으며 단순화 mesh는 패키지에 포함되고 fullsize는 별도로 내려받는다고 설명한다. 첫 적용은 단순화 mesh를 쓴다.

현재 FlyGym2.x와 예전 Gymnasium API는 다르다. 메시를 가져오기 위해 야구 환경 전체를 FlyGym으로 갈아엎을 필요는 없다. [공식 저장소](https://github.com/NeLy-EPFL/flygym)의 [루트 라이선스](https://github.com/NeLy-EPFL/flygym/blob/main/LICENSE)는 Apache2.0이며, 실제 취득한 mesh·하위 자산의 별도 조건과 provenance도 확인해 기록한다.

### I-08a — 연구 모델의 외형 적용 (외형 수용 실패, 수정 필요)

**2026-09-16 최신 정정:** [I-08a-fix](../records/FLY-VISUAL-REVIEW.md)를 우선한다. 앞다리2개로 그립, 뒷다리2개로 지면에 서고 중간다리는 접는다. 모든 부위 동일 배율이며 앞다리만3배 확대는 허용하지 않는다.

1. 공식 모델의 특정 tag/commit/package와 asset 버전을 고정한다. 원 mesh·rigging 파일/해시·라이선스·인용·원 좌표 단위·수정 내역을 `assets_manifest.json`과 THIRD_PARTY_NOTICES에 기록한다. 파일 경로는 선택한 버전의 모델 loader에서 확인하고 추측하지 않는다.
2. 원본 메쉬를 보존하고 원본→미터→야구장 캐릭터의 단위 변환·uniform scale·자세 변환을 명시한다. 확대된 파리 캐릭터이며 실제 크기 초파리의 야구 역학으로 부르지 않는다.
3. 기존 타격 물리를 유지한 별도 시각 layer로 머리·흉부·복부·6다리·날개/더듬이를 표현한다. 뒷다리만 지지 자세, 중간다리는 몸 옆에 접는 자세, 앞다리는 배트 그립 목표를 따라가는 시각용 IK/pose mapping을 사용한다. 검증된 타구 경로를 몸 그림에 맞추려고 바꾸지 않는다. 도달 불가능한 외형 자세는 모델 pose/전체 uniform scale/손잡이 안 그립 부착점을 명시적으로 조정한다. 부위별 확대는 금지하며 불가능하면 도달성 충돌을 보고한다.
4. 앞다리 애니메이션은 실제 신경근육 제어가 아니라 기존 두 축 동작의 시각적 대응이라고 표시한다. 공과 충돌하는 것은 기존 배트/간단 collider다. visual mesh를 default inertiafromgeom에 섞거나 새 활성관절·질량·접촉을 추가하지 않는다. 가장 안전한 초기 경로는 저장된 물리 궤적을 별도 render scene에 재생하는 방식이다.
5. 연구 모델 pose와 확대된 야구 pose를 나란히 보여주고 무엇을 바꿨는지 설명한다. MaleCNS 수컷 연결 데이터와 암컷 NeuroMechFly 외형은 같은 개체/성별의 디지털 복제가 아니며, 현재는 별도의 데이터 계층이라는 점도 기록한다.

완료: mesh on/off에서 동일 물리 궤적·접촉·타구 지표(동일 backend, 상태 절대오차1e-10 이내), dynamics 질량/관성·DOF/actuator 불변, 정면/측면/포수 뒤1×영상, 앞다리–배트 그립의 일관된 연결, 가려짐·발 미끄러짐·부위 관통 점검. 정책용 vision은 외형이 바뀌면 관측이 달라지므로 별도 버전으로 취급한다.

### I-08b — 실제 전신 역학 (후속)

NeuroMechFly의 관절/질량/접촉/감각을 그대로 쓰는 통합은 별도 embodied 환경이다. 원 스케일에서 보행·자세·감각 baseline부터 재현하고 신경회로-운동 제어 매핑을 설계한다. 확대 시 관성/힘/시간을 재검토해야 하며 mm 모델을 사람 크기로 키우고 질량만 유지하지 않는다. 모델을 가져왔다고 실제 파리 뇌가 배트를 제어하게 되는 것은 아니다. 야구용 I-08a와 결과를 구분한다.

## 진행 순서

1. I-07b-followthrough + 실제 접촉 설정 기록/설명 정정.
2. I-08a 시각 모델 도입(소스 조사·취득은1과 독립 가능).
3. 안정화된 제어/재료를 고정한 뒤 나머지8코스 재보정.
4. B2/RL은9코스의 전방 타구 수용 이후. 실제 뇌 학습 경로 I-02/I-04/I-05는 계속 별도로 유지한다.

## 추가 외형 요구

I-08a-fix 후 [I-08a-style](FLY-BATTING-STANCE-AND-COLOR.md): 몸통은 옆선, 머리는 투수 방향, 원본 부위별 색상 적용. 접지/그립을 다시 검증한다.

# Research Sources

외부 과학 데이터·코드·인용·라이선스 제약을 추적한다.

## 반입 전 기록 의무

외부 신경 형태/연결 행렬/주석 테이블/파생 부분집합을 추가하기 전에 다음을
전부 남긴다. 하나라도 비면 반입하지 않는다.

- source URL
- dataset version 또는 snapshot
- citation
- license (상업적 이용 가능 여부 포함)
- 파생 데이터가 들어가는 로컬 파일 경로
- 체크섬

저장소 코드는 자체 라이선스(MIT)를 쓰지만, **커넥톰 데이터와 그 파생
파일은 원 데이터의 라이선스 조건을 그대로 유지한다.**

## 현재 상태

**이 저장소에 커넥톰 데이터는 없다.** 반입된 외부 자산은 아래 NeuroMechFly
메시 하나뿐이며, 그것은 연결망 데이터가 아니라 형태(mesh) 데이터다.

## 반입됨: NeuroMechFly mesh assets

`flyohtani/assets/mesh_neuromechfly/*.stl` (45개) + Apache-2.0 라이선스
전문. 출처는 PyPI `flygym==1.2.1` (NeLy lab, EPFL).
파일별 SHA-256, 소스 wheel의 SHA-256, byte-identity 검사 결과는
`flyohtani/assets/mesh_neuromechfly/PROVENANCE.json`에 있고, 라이선스
고지는 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)에 있다.

**형태 데이터이며 연결망 데이터가 아니다.** 또한 NeuroMechFly의 파리는
암컷이고, 이 프로젝트의 신경 트랙이 목표하는 MaleCNS는 수컷이다 — 같은
개체도 같은 성별도 아니며, 명시적으로 분리된 두 데이터 층이다.

## 인용했으나 반입하지 않음: flygym 원본 MJCF/포즈/제어 기본값

`flyohtani/units.py`와 [선행 발견](records/PRIOR-FINDINGS.md) §1의
관절 구조·DOF 목록·위치제어 기본값·정지 포즈 각도·세그먼트 질량 비율은
같은 `flygym==1.2.1` 패키지를 `pip download flygym==1.2.1 --no-deps`로
받아 raw MJCF(`flygym/data/mjcf/neuromechfly_seqik_kinorder_ypr.xml`),
`flygym/fly.py`, `flygym/preprogrammed.py`,
`flygym/data/pose/{pose_stretch,pose_tripod}.yaml`에서 직접 읽은 값이다.
이 조사로 저장소에 추가된 파일은 없다 — 코드와 문서에 인용된 수치뿐이다.

### 단위 규약 (확정)

> "we use millimeter and gram as base units for length and mass instead of
> their SI counterparts, meter and kilogram... forces read out from the
> simulation are in g·mm·s⁻¹ (i.e., micronewton, μN)"
> — [NeuroMechFly: Advanced model composition](https://neuromechfly.org/tutorials/1b_advanced_model_composition/)

즉 길이=mm, 질량=g, 힘/토크=μN(g·mm·s⁻²). 모델의 `gravity="0 0 -9810"`과
정합한다. 전신 질량 ~0.001 g(~1 mg)은 성체 *D. melanogaster* 질량으로 흔히
인용되는 자릿수와 같으나, **그 정확한 수치에 대한 특정 문헌 인용은 아직
확보하지 않았다.**

> 한 번 틀렸던 지점: raw XML을 정규식으로 합산하면 질량 합이 ~1.0으로
> 나온다. 시각화용 메타데이터 `<statistic meanmass="1.0">`까지 잘못 세는
> 것이며 물리량이 아니다. 질량은 MuJoCo의 컴파일된 `model.body_mass`에서
> 센다.

## 다음 반입 대상: MaleCNS (커넥톰)

[PLAN](PLAN.md) D19에 따라 첫 대상은 **루밍(looming) 검출 계열 뉴런과 그
하류 서브그래프**다. 게이트 G4에서 다음을 실제로 확인한 뒤에만 진행한다:

- 해당 뉴런 타입이 MaleCNS v1.0에 **어떤 이름·규모로 실제 존재하는지**
  (문헌에서 익숙한 타입 이름을 데이터에 있다고 가정하지 않는다)
- 배포 형식, 버전, 체크섬, 라이선스, 상업적 이용 가능 여부
- hemibrain 시절 주석을 자동으로 물려받지 않는다

다운로드: <https://male-cns.janelia.org/download/>

## 후속 비교 후보

### FlyWire

- 홈: <https://home.flywire.ai/> · Codex: <https://codex.flywire.ai/>
- 인용 지침: <https://join.flywire.ai/guidelines> (v783, **CC BY-NC 4.0**)
- 비상업 제한이 있으므로 상업적 산출물에 섞지 않는다. 주석 snapshot을
  별도로 기록한다.
- Dorkenwald, S. et al. "Neuronal wiring diagram of an adult brain."
  *Nature* 634, 124-138 (2024). <https://doi.org/10.1038/s41586-024-07558-y>
- Schlegel, P. et al. "Whole-brain annotation and multi-connectome cell
  typing of Drosophila." *Nature* 634, 139-152 (2024).
  <https://doi.org/10.1038/s41586-024-07686-5>

### Janelia FlyEM Hemibrain

- <https://www.janelia.org/node/65250> · CC-BY (데이터셋별 고지가 우선)

### FlyGym API

- <https://neuromechfly.org/migration/> — 2026년 2.x는 이 프로젝트가 인용한
  1.2.1과 다르다. 논문 인용과 함께 **소프트웨어 버전을 고정**한다.

## README 고지 문구

커넥톰 유래 배선을 포함하게 되면 README에 추가한다:

```text
Connectome data attribution: portions of the connectome-derived wiring are
derived from [dataset/version]. Dataset license: [license].
Please cite [papers].
```

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

## 현재 상태 (2026-09-17 갱신)

반입된 외부 자산은 셋이다:

1. NeuroMechFly **메시**(Apache-2.0) — 형태 데이터
2. NeuroMechFly **원본 MJCF**(Apache-2.0) — Phase 1의 앞다리 빌드 소스
3. NeuroMechFly **보행 운동학**(Apache-2.0) — LIT-01의 실측 대상
4. MaleCNS **루밍 부분회로**(CC-BY) — 실제 연결망 데이터, G4에서 반입

## 반입됨: NeuroMechFly mesh assets

`flyohtani/assets/mesh_neuromechfly/*.stl` (69개: v1의 45개 + 2026-09-17 타석
장면용 Tarsus2-5 24개, `PROVENANCE-tarsus-additions.json`) + Apache-2.0 라이선스
전문. 추가 반입 시 wheel sha256을 재다운로드로 다시 대조했고, 기존 45개도 같은
wheel과 여전히 바이트 단위로 일치함을 확인했다. 출처는 PyPI `flygym==1.2.1` (NeLy lab, EPFL).
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

## 반입됨: 원본 MJCF (Phase 1)

`flyohtani/assets/mjcf_neuromechfly/neuromechfly_seqik_kinorder_ypr.xml`
(47,382 B, sha256 `413b3a1d…2e05a`), 같은 `flygym==1.2.1` wheel에서 수정 없이
복사. Apache-2.0. v1은 이 파일을 매번 wheel에서 읽었으나, Phase 1의 몸체
빌드를 네트워크 없이 재현 가능하게 하려고 반입했다. 상세:
`flyohtani/assets/mjcf_neuromechfly/PROVENANCE.json`.

wheel sha256 `5db9bb89b7f57e2fda8d716fd8205b0ba7ac9a46e7c194ea6e752e38964f390d`은
v1이 기록한 값과 재다운로드로 대조해 일치를 확인했다.

## 반입됨: 보행 운동학 (LIT-01, 2026-09-17)

`flyohtani/assets/behavior_neuromechfly/walking-joint-angles-210902-pr-fly1.npz`
(626 KB). 같은 `flygym==1.2.1` wheel의 `flygym/data/behavior/210902_pr_fly1.pkl`을
**무손실로** npz 변환(값 불변, 정확 일치 확인). Apache-2.0.

테더된 보행 파리 1마리, 2 kHz, 42 다리 DOF, 1초. 원 파일명
`joint_angles__210902_PR_Fly1.pkl`, time_range (3.0, 4.0) s. 체크섬과 변환
내역은 `behavior_neuromechfly/PROVENANCE.json`.

인용:

> Wang-Chen, S., Stimpfling, V. A., Lam, T. K. C., Özdil, P. G., Genoud, L.,
> Hurtak, F. & Ramdya, P. (2024). NeuroMechFly v2: simulating embodied
> sensorimotor control in adult *Drosophila*. *Nature Methods* **21**(12),
> 2353–2362. [doi:10.1038/s41592-024-02497-y](https://doi.org/10.1038/s41592-024-02497-y)

## 문헌 인용 — 다리 성능 (LIT-01)

수치를 쓴 논문만 적는다. 검색 요약만 보고 인용하지 않으며, 확인하지 못한
수치는 [LIT-01](records/LIT-01-FLY-LEG-LIMITS.md) §6에 "사용하지 않음"으로
남긴다.

> Card, G. & Dickinson, M. (2008). Performance trade-offs in the flight
> initiation of *Drosophila*. *J. Exp. Biol.* **211**(3), 341–353.
> [doi:10.1242/jeb.012682](https://doi.org/10.1242/jeb.012682)
> — 탈출 점프 다리 신전 3.3 ms, 이륙 속도 0.48 ± 0.01 m/s. 원문 직접 확인.

> Zumstein, N. et al. (2004). Distance and force production during jumping in
> wild-type and mutant *Drosophila melanogaster*. *J. Exp. Biol.* **207**(20),
> 3515–3522. [PMID 15339947](https://pubmed.ncbi.nlm.nih.gov/15339947/)
> — 중간다리 최대 점프 힘 101 ± 4.4 μN. 초록 확인.

> Swank, D. M. (2011). Mechanical analysis of *Drosophila* indirect flight and
> jump muscles. *Methods* **56**(1), 69–77.
> [doi:10.1016/j.ymeth.2011.10.015](https://doi.org/10.1016/j.ymeth.2011.10.015)
> — **수치를 쓰지 않았다.** 검색 요약이 이 논문에 있다고 한 "6.1 ML/s"가
> 원문에는 없다(원문은 6 μm/s). 반례로 기록해 둔다.

## 반입됨: MaleCNS 루밍 부분회로 (G4, 2026-09-17)

**이 프로젝트의 첫 실제 연결망 데이터다.** 상세: [G4 보고](records/G4-CONNECTOME-ACCESS.md).

| 항목 | 값 |
| --- | --- |
| dataset | MaleCNS **v1.0** |
| license | **CC-BY** — 상업적 이용 허용, 저작자 표시 필요 |
| 배포처 | <https://male-cns.janelia.org/download/> |
| 협력 기관 | FlyEM (HHMI Janelia), Univ. of Cambridge (Dept. of Zoology), MRC LMB, Google Research |
| 파생 파일 | `flyohtani/assets/connectome/looming-subgraph-male-cns-v1.0.json` (49 KB) |

원본 파일과 체크섬:

| 파일 | 크기 | SHA-256 |
| --- | --- | --- |
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 14,483,314 | `2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2` |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 1,051,241,946 | `e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1` |

원본 두 파일은 **저장소에 넣지 않았다**(1 GB). 파생 부분회로만 반입했고, 그
파일 자체에 provenance 블록을 넣어 라이선스 표시가 파일과 함께 이동하도록 했다
— 문서에만 적으면 파일을 복사하는 순간 표시가 끊긴다.

`weight`는 공표된 시냅스 개수 그대로다. 재가중·임계·정규화하지 않았다.

### hemibrain 주석을 물려받지 않는다

MaleCNS의 타입 이름은 MaleCNS 주석 테이블에서 직접 조회해 확인했다(LC4 n=126,
LPLC2 n=185, DNp01(GF) n=2). 문헌이나 hemibrain에서 익숙한 이름이 이 데이터셋에
있다고 가정하지 않았다.

### 아직 받지 않은 것

- 신경전달물질 예측(`body-neurotransmitters`, 42 MB) — 흥분/억제 부호에 필요
- SWC skeleton / 좌표 — 뷰어의 3D 뇌 배치에 필요
- LC4/LPLC2의 **입력** 경로

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

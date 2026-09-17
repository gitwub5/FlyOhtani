# 검증 기록 색인

실행한 명령과 그 결과를 시간순으로 남긴다. **테스트 통과는 구현이 도는
것이고, 연구 가설의 검증은 별개다** — 이 문서는 전자를 기록한다.

새 항목 형식: 날짜 · 작업 ID · 실행 명령 · 결과 · 원자료 경로.

---

## 2026-09-17 · Phase 0 · 정리 후 회귀

| 명령 | 결과 |
| --- | --- |
| `.venv/bin/python -m pytest -q` | 20 passed |
| `.venv/bin/pytest -q` | 20 passed (두 진입점 일치 확인) |
| `.venv/bin/ruff check .` | All checks passed |
| `pip install -e ".[dev]"` | 성공(`flyohtani`, `flyohtani.sense`) |

단위 규약 환산 확인 (`flyohtani/units.py`), v1에서 검증된 값과 대조:

| 항목 | 모델 단위 | SI 환산 | v1 기록값 |
| --- | --- | --- | --- |
| 중력 | 9810 mm/s² | 9.81 m/s² | 일치 |
| `kp` | 45 μN·mm/rad | 4.5e-8 N·m/rad | 일치 |
| `forcerange` | ±65 μN·mm | ±6.5e-8 N·m | 일치 |
| 전신 질량 | 1e-3 g | 1e-6 kg (1 mg) | 일치 |
| 앞다리 세그먼트 비율 합 | — | 1.0 | 일치 |
| 능동 DOF 수 | — | 7 | 일치 |

**이번에 검증하지 않은 것**: 렌더 기반 공 검출(대상 rig 없음), 접촉 물리,
관절 구동, 커넥톰 로딩. 전부 미구현이다.

v1 시점의 원자료(실행 명령·evidence JSON·영상)는 git 태그
`archive/human-scale-v0`에 있다.

비editable wheel 설치 확인 (`pip wheel --no-deps` → 임시 venv에 설치 →
**저장소 밖에서** import; 저장소 안에서 돌리면 소스 디렉터리를 집어 검사가
무효가 된다 — 실제로 첫 시도가 그렇게 무효였고 `site-packages` 경로 assert를
추가해 잡았다):

| 항목 | 결과 |
| --- | --- |
| STL 메시 | 45개 전부 포함 |
| Apache-2.0 라이선스 전문 | 포함 |
| PROVENANCE.json | 포함 |
| `flyohtani.units` import | 정상 |

---

## 2026-09-17 · G1 · 앞다리 스윙 측정

| 명령 | 결과 |
| --- | --- |
| `.venv/bin/python -m flyohtani.body.g1_sweep` | 240런, 발산 0, 최대 16,820 mm/s |
| dt 수렴 (1e-4 → 1.5625e-6) | 가장 미세한 두 dt 차이 **0.07%** |
| 적분기 교차검증 (Euler/implicitfast/RK4 @ 1.5625e-6) | 편차 **0.02%** |
| `boundmass` 민감도 (1e-6 vs 1e-9) | 16,820 vs 18,215 mm/s (**8.3%**) |

원자료: `evidence/G1-swing-sweep.json` · 보고: [G1](G1-FORELEG-SWING.md)

원본 모델 대조(수정하지 않은 flygym MJCF를 그대로 컴파일, 스크래치 공간):
앞다리 7개 능동 DOF의 대각 관성 측정 — `Coxa_roll` 2.914e-08,
`Femur_roll` 1.784e-08 vs 나머지 1.0e-06 ~ 2.8e-05 g·mm². 이 대조는 저장소가
의도적으로 반입하지 않은 Tarsus2-5 메시를 필요로 하므로 **오프라인 테스트로
재현되지 않는다** — 테스트는 같은 결론을 우리 빌드에서 재측정한다.

**이번에 검증하지 않은 것**: 접촉 물리, 렌더 기반 검출, 회로 시뮬레이션.

## 2026-09-17 · G4 · 커넥톰 접근

| 단계 | 결과 |
| --- | --- |
| MaleCNS v1.0 주석 다운로드 (14.5 MB) | http 200, sha256 `2177e246…a3b2` |
| MaleCNS v1.0 연결 가중치 다운로드 (1.05 GB) | http 200, sha256 `e35da783…afc1` |
| 주석 조회 | 211,577 뉴런. LC4 n=126, LPLC2 n=185, DNp01(GF) n=2 실재 확인 |
| 부분회로 추출 | 151,856,684 간선 중 1,343개 선택 (311→12 뉴런, 39,549 시냅스) |
| 파생 파일 | `flyohtani/assets/connectome/looming-subgraph-male-cns-v1.0.json` (49 KB) |

보고: [G4](G4-CONNECTOME-ACCESS.md) · 재추출:
`flyohtani.brain.connectome.extract_looming_subgraph()`

## 2026-09-17 · Phase 1 · 회귀

| 명령 | 결과 |
| --- | --- |
| `.venv/bin/python -m pytest -q` | 54 passed |
| `.venv/bin/pytest -q` | 54 passed (두 진입점 일치) |
| `.venv/bin/ruff check .` | All checks passed |

flygym 1.2.1 wheel sha256 `5db9bb89b7f57e2fda8d716fd8205b0ba7ac9a46e7c194ea6e752e38964f390d`
— v1이 기록한 값과 일치함을 재다운로드로 확인(provenance 체인 검증).

비editable wheel 재확인(저장소 밖에서 import): STL 45 + Apache-2.0 라이선스 +
메시 PROVENANCE + 원본 MJCF + MJCF PROVENANCE + 커넥톰 부분회로가 모두 실리고,
설치본만으로 부분회로 로드(1,343간선, CC-BY)와 몸체 빌드(nv=nu=5)가 된다.

---

## 2026-09-17 · LIT-01 · 다리 속도·힘 상한

실측(이 저장소가 수행): flygym 배포 관절각 시계열을 미분.

| 대상 | 결과 |
| --- | --- |
| 원본 | `flygym/data/behavior/210902_pr_fly1.pkl`, 2 kHz, 42 DOF, 1.00 s |
| 반입 | npz 무손실 변환(정확 일치 확인), 626 KB |
| 우리 5 DOF 보행 최대 \|ω\| | **98.6 rad/s** (`joint_RFTibia`), p95 65.2 |
| 42 DOF 전체 최대 | 231.1 rad/s (`joint_LFTarsus1`) |

문헌(원문/초록 직접 확인): Card & Dickinson 2008 — 탈출 점프 다리 신전
3.3 ms, 이륙 0.48 ± 0.01 m/s. Zumstein 2004 — 중간다리 최대 점프 힘
101 ± 4.4 μN.

유도: 점프 관절 각속도 240~516 rad/s(유효 반경 2.00~0.93 mm). **측정 아님.**

채택: 설계 상한 300 rad/s → G1 격자에서 배트 팁 최대 **4,533 mm/s**
(240런 중 38런 적합, 포화 0.0%).

검증하지 않은 것: 개체 변이, 앞다리의 최대 노력 성능, 근육 힘-속도 곡선.
사용하지 않은 수치와 그 이유는 [LIT-01](LIT-01-FLY-LEG-LIMITS.md) §6.

비editable wheel 재확인: 설치본만으로 보행 데이터 42 DOF 로드,
`joint_RFTibia` 98.6 rad/s 재현, 인용문 포함.

| 명령 | 결과 |
| --- | --- |
| `.venv/bin/python -m pytest -q` / `.venv/bin/pytest -q` | 66 passed (일치) |
| `.venv/bin/ruff check .` | All checks passed |

---

## 2026-09-17 · G2 · 파리 스케일 접촉

| 단계 | 커밋 | 결과 |
| --- | --- | --- |
| v1 사전 등록 | `ea7dff9` | 기준·격자·선택 규칙, 실행 전 |
| v1 실행 (25 s, 10 workers) | `ea85352` | **FAIL** 0/40. 전 후보 C3/C4 |
| 사후 진단 (1 후보, 3 구성, τ/4~τ/512) | `ea85352` | e → 0.42~0.45 수렴. 해상도 부족 |
| v2 사전 등록 (탐색) | `3266983` | dt 사다리만 변경 + hold-out 10 |
| 리팩터 후 v1 재실행 | — | 커밋된 10,400런과 **비트 동일** |
| v2 실행 (6 m 56 s, 10 workers) | 이번 커밋 | **PASS** 4/40 → RK4 통과 → hold-out 통과 |

선택: τ=3e-6 s, ζ=0.3, solimp default, production dt 2.344e-8 s.
원자료: `evidence/G2-contact.json.gz`(v1), `evidence/G2v2-contact.json.gz`(v2).

계산 경로 검증: 유효질량(블록·배트 중심·배트 편심) 해석해와 9자리 일치,
운동량 잔차 ~1e-16, gzip 증거 파일 이름 무관 바이트 동일.

비용 측정(이 맥, G2 v2가 전 코어 사용 중이라 느리게 나옴): 물리 2.6 μs/스텝,
128px 렌더 5.2 ms/프레임, LIF 2.9 μs/스텝.

| 명령 | 결과 |
| --- | --- |
| `.venv/bin/python -m pytest -q` / `.venv/bin/pytest -q` | 94 passed |
| `.venv/bin/ruff check .` | All checks passed |

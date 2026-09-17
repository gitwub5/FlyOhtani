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

## 2026-09-17 · 시각 보고서와 굵은 dt 실측

사용자 요청으로 진행 상황을 시각 보고서로 만들었다(claude.ai 아티팩트, 비공개).
모든 그림·수치는 저장소 코드와 커밋된 증거 파일에서 다시 계산했다.

보고서를 만들며 새로 실측한 것:

| 대상 | 결과 |
| --- | --- |
| 스윙 dt(2.5e-5 s)로 G2 선택 파라미터 충돌, 위상 25개 | e 0.056~2.722, KE 비 0.59~3.62 — **에너지 생성** |
| 같은 충돌 τ/8 | e 0.387~0.500 |
| 같은 충돌 τ/128 | e 0.449~0.455 |
| 통과(tunneling) 여부 | **없음** — 이전 "통과할 수 있다" 서술을 정정 (G2 §8.1, STATUS) |
| −0.5 rad 스윙 렌더 | 관절 최대 264 rad/s(상한 300 안), 2 ms에 배트 끝 3.72 m/s |
| 눈 카메라 화면 | **파리 자신의 더듬이가 시야 대부분을 가림** — Phase 1 임시 위치 문제 |

---

## 2026-09-17 · 타석 장면 (D26~D29)

| 단계 | 커밋 | 결과 |
| --- | --- | --- |
| 장면 + 기준 K1~K6 (실행 전) | `b16b212` | 테스트 114 passed |
| 충돌 확인 1차 실행 | — | PASS, 그러나 **반발계수 측정 버그**(팔 길이 미회전) — 결과 폐기 |
| 측정 버그 수정 후 재실행 | 이번 커밋 | **PASS** K1~K6, 반발계수 0.412~0.462, KE 비 ≤ 0.350 |

1차 실행 원자료는 폐기 전 스크래치에 복사해 대조했다(속도 3000에서 반발계수
0.638~0.672 → 수정 후 0.412~0.435).

만들며 테스트가 잡은 결함: 파리가 박스 밖(몸통 오프셋 1.3 mm), 배트 질량 +8%(비볼록
메시의 legacy 부피), 데모 스윙이 배트로 땅을 긁음(짧은 방향 관절 경로).

비용: 물리 6.0 μs/스텝, 두 눈 렌더 5.7 ms, 0.1 s 에피소드 0.64 s.

---

## 2026-09-17 · 녹화 모듈

| 명령 | 결과 |
| --- | --- |
| `python -m flyohtani.record pitch` | 맞힘, 타구 602 mm/s, 발사각 −24°, 비거리 1.96 mm, 페어, 207 프레임 |
| `... pitch --timing-ms 4` | 헛스윙 |
| `... pitch --speed-scale 0.5` | 맞힘, 타구 435 mm/s, 발사각 −37°, 비거리 1.00 mm |
| `... swing` | 관절 최대 215 rad/s, 254 프레임 |
| 녹화 유무 비교 | 충돌 시각·타구 속도·발사각 동일 (`tests/test_record.py`) |
| 장면 표시 변경(무한 평면, 평행광) 후 `batter_check` | PASS, 수치 동일 |
| `pytest` 두 진입점 | 120 passed · ruff 클린 |

Python 최소 버전을 3.11로 올렸다(D07과 일치, `typing.Self` 사용).

---

## 2026-09-17 · 뇌 뷰어 (fly-connectome-template, D30)

| 단계 | 결과 |
| --- | --- |
| 템플릿 클론, 커밋 `38f5533` | 42개 파일 반입(`.github/` 제외), 바이트 동일 확인 |
| 원본 그대로 `npm ci / npm test / npm run build / check:assets` | 4 passed · 빌드 성공 · 해시 검증 (Node 24.21, npm 11.19) |
| 원본 반입 커밋 | `6b7c42d` (README 제작자 표시 동시 추가) |
| 우리 회로 323개 vs 템플릿 지도 | 323/323 존재·표시 대상, 그룹 일치 |
| `python -m flyohtani.brain.replay --run runs/record/hit` | 번들 생성, Python 검증 통과 |
| 템플릿 자체 `parseReplay`로 대조 | 수락(프레임 6, synthetic); 없는 bodyId는 거부 |
| 수정 후 `npm test / build / check:assets` | 4 passed · 빌드 · 해시 검증 |
| 헤드리스 Chrome 캡처 (`?t=1.6/3.1/4.6/6.1`) | LC4 → LPLC2 → DN 12개 → 전체 순으로 실제 뇌 위치에서 켜짐 |
| `pytest` 두 진입점 | 139 passed · ruff 클린(`viewer/`는 제외 — 제3자 코드) |

---

## 2026-09-18 · VM-01 눈 프레임률과 투구 가시성

| 단계 | 결과 |
| --- | --- |
| 기준·그리드·테스트 선행 커밋(결과 없음) | `193a1e2` |
| 디버깅 중 발견(그리드 실행 전) | 느린 공이 로브가 됨(0.125배에서 +73°), 접촉 순간 공이 시야 밖(79°) → `DISTANCE_SCALES`·V5·FOV 기록 추가 |
| `python -m flyohtani.sense.eye_rate` (180조합, 47 s) | **0/180 usable.** V1 160, V2 2, V3 **0**, V4 126, V5 120 |
| 진단 | 결정 시점(접촉 −45 ms)에 검출 픽셀이 0~1로 깜빡여 크기 변화 없음 — 에일리어싱. fps는 병목이 아님(240 Hz까지 예산 여유) |
| `pytest tests/test_sense_eye_rate.py` | 9 passed |

전체 보고 [VM-01-EYE-RATE.md](VM-01-EYE-RATE.md), 원자료
`evidence/VM-01-eye-rate.json`.

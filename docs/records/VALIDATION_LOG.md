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

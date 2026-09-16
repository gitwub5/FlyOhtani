# R-00 — 정리 시작 시점의 알려진 실패/차이 목록

2026-09-16. `docs/implementation/REFACTOR-PLAN.md` R-00.3. 커밋
`c812766`(체크포인트 직전 HEAD) + 아래 미커밋 변경 기준. 정리 작업이 이 목록을
"전부 통과"로 조용히 바꾸지 않았는지 R-03/완료 보고에서 다시 확인한다.

| # | 실패/차이 | 근거 | 정리에서의 처리 |
| --- | --- | --- | --- |
| 1 | `pytest tests/ -q`(콘솔 스크립트)가 `python -m pytest tests/ -q`와 다른 결과: `test_ground_legs_soles_touch_the_true_world_ground_inside_the_batter_box`가 `ModuleNotFoundError: No module named 'scripts'`로 실패 | [R00-pytest-console-script-invocation.txt](R00-pytest-console-script-invocation.txt) vs [R00-pytest-module-invocation.txt](R00-pytest-module-invocation.txt) | R-02/R-03: `scripts/fly_mesh_utils.py`를 설치 가능한 `envs/` 하위 모듈로 이동해 두 진입점 모두에서 `import`가 성립하게 한다 |
| 2 | `ruff check envs controllers encoders train analysis demos scripts tests` 7건 | [R00-ruff-before.txt](R00-ruff-before.txt) | R-03: 각 파일에서 미사용 언패킹 변수에 `_` 접두, `dict()` 리터럴 치환. 동작 변경 없음 |
| 3 | 과거 B1 recorder가 삭제된 `hit` 키를 `info.get("hit", False)`로 읽어 항상 `False`인 잘못된 요약을 낼 수 있음 (ENV-001/B0의 `hit`는 별도 유효 계약이므로 전역 치환 금지) | REFACTOR-PLAN.md 구조 근거 | R-03: 해당 legacy recorder만 현행 schema로 교체하거나 실행 차단. 대상 파일은 실제 조사 후 확정 |
| 4 | `reward_version` 기본값은 여전히 `batted-ball-v1`. `forward-carry-v1`은 선택 가능하지만 기본이 아님 | `envs/baseball_b1_env.py` 생성자 기본값 확인 | 정리 대상 아님. 이번 순수 리팩토링에서 기본값을 바꾸지 않는다. 다음 실험은 원하는 버전을 명시해야 한다 |
| 5 | 중앙 고정 투구(mid_mid)의 스윙 타이밍이 ±5ms 수준에서 취약할 수 있다는 가설이 미검증 | `docs/design/BATTING-QUALITY-AND-SWING.md`, REFACTOR-PLAN.md 비목표 | 이번 정리의 범위 밖. 완료 후 별도 실험으로 다룬다 |
| 6 | tilt 축 정착(follow-through 이후 안정화)이 전 코스에서 검증되지 않음 | `docs/design/FOLLOWTHROUGH-AND-FLY-MODEL.md` | 이번 정리의 범위 밖 |
| 7 | mid_mid 외 나머지 8코스가 재보정되지 않음 (`docs/design/ENV-002-B1-courses.md`) | REFACTOR-PLAN.md 구조 근거 | 이번 정리의 범위 밖 |
| 8 | `pyproject.toml`의 `[tool.setuptools.package-data]`가 `envs = ["assets/*.xml"]`만 지정해 `envs/assets/mesh_neuromechfly/*.stl`, 하위 라이선스, `fly_visual_*.xml` 등 중첩 자산이 wheel에서 빠질 위험 | `pyproject.toml` 확인 | R-03: package-data를 재귀 패턴으로 확장하고 clean wheel 설치로 실측 검증 |
| 9 | `scripts`가 `pyproject.toml`의 `[tool.setuptools] packages`에 없어 설치된 패키지로 배포되지 않음 (CLI 전용 스크립트이므로 이 자체는 설계 의도일 수 있으나, 런타임/테스트가 이를 import하면 실패 1과 동일한 문제가 재발) | `pyproject.toml`, 실패 #1 | R-02: 런타임이 필요로 하는 계산은 설치 모듈로 옮기고 `scripts/`는 CLI 전용으로 유지 |

## 재현 명령

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/pytest tests/ -q
.venv/bin/ruff check --output-format=concise envs controllers encoders train analysis demos scripts tests
.venv/bin/python <capture_baseline_script>  # R00-baseline-mid_mid-before-after.json 생성
```

## 관련 증거 파일

- [R00-baseline-mid_mid-before-after.json](R00-baseline-mid_mid-before-after.json) — 중앙 투구 전/후 설정·qpos/qvel·사건시각·에피소드 누적 보상·최종지표
- [R00-pytest-module-invocation.txt](R00-pytest-module-invocation.txt)
- [R00-pytest-console-script-invocation.txt](R00-pytest-console-script-invocation.txt)
- [R00-ruff-before.txt](R00-ruff-before.txt)
- [R00-env-versions.txt](R00-env-versions.txt)

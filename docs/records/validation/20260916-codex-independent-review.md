## 2026-09-16 — Codex 독립 검토

- 기준 commit e2447bb. `.venv/bin/python -m pytest tests/test_fly_batter_env.py -q`:8 passed in0.23s.
- reset 직후 contact 검사 및 seed0/frame_skip1/zero torque 재현: ground–limb dist=-0.1449m, thorax–limb dist=-0.0567m; +1.1rad→약0.712s hit 때 -1.2466rad. 재현 절차와 한계는 [REVIEW](../REVIEW_2026-09-16.md).
- in-memory 모델에서 thorax/ball collision을 제외한 actuator 분리 측정: 최대 음의 입력0.5s, q0=0→-0.03173rad, q0=0.5→0.44742rad. 원본 XML/gear는 수정하지 않았다.
- ENV 후보의 고정 준비각+0.5/목표(0.5,0,0.52)/27개 표본 궤적에서 최소 표면 여유 약0.166m. 전체 동역학/baseline 성공률 검증 아님.
- 과거 아래 기록의 ‘geometry confirmed’·‘motionless’ 해석은 최신 검토로 정정한다. 이전 측정값은 보존한다.


Record command results here so experiment state remains recoverable.

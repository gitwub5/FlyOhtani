"""KC-01a (docs/design/KC-01a-TORSO-BAT-COORDINATION.md, proposed by
docs/research/BATTING-KINETIC-CHAIN.md): torso-bat coordination model.
Config/calibration constants live in `envs.kc01a.config`; the environment
itself is `envs.baseball_kc01a_env.BaseballKC01aEnv` (kept alongside the
other staged baseball environments rather than nested in this package, for
the same reason `BaseballB1Env` lives in `envs/baseball_b1_env.py` next to
`envs/baseball/` rather than inside it)."""

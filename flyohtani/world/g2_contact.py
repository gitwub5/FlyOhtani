"""G2 (docs/PLAN.md Phase 2): does ball-bat contact meet the pre-registered
acceptance criteria at fly scale?

Every constant in this module is fixed in docs/records/G2-CONTACT.md
sections 2-5, which were committed BEFORE this gate was run. Changing a
number here without changing that document -- and saying so -- breaks the
one thing that makes a solo-run gate trustworthy.

Isolated contact only: no gravity, no air, no friction, no fly. Two bodies
meet once. A bat attached to an actuated leg is a later, separate check.

Two protocols live here and both stay runnable exactly as registered:

  v1  section 2-5 of the record, commit ea7dff9. Ran and FAILED.
  v2  section 9, an EXPLORATORY protocol designed after seeing v1: the same
      criteria and candidates on a finer dt ladder, plus hold-out configs.

Run:  .venv/bin/python -m flyohtani.world.g2_contact --protocol v2
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import platform
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import partial
from itertools import product
from pathlib import Path

import mujoco
import numpy as np

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

# --- section 2: fixed setup (CHOSEN) ---------------------------------------

BALL_RADIUS_MM = 0.1
BALL_MASS_G = 2.9e-6
BAT_RADIUS_MM = 0.05
BAT_HALF_LENGTH_MM = 2.0
BAT_MASSES_G = (2e-6, 2e-5)
HIT_HEIGHTS_MM = (0.0, 1.5)
IMPACT_SPEEDS_MM_S = (250.0, 500.0, 1000.0, 2000.0, 4500.0)
BAT_IMPACT_ANGLES_DEG = (0.0, 20.0, 35.0)
BLOCK_HALF_SIZE_MM = 1.0
APPROACH_TIMECONSTS = 5.0

# --- section 3: candidate grid ----------------------------------------------

TIMECONSTS_S = (1e-5, 3e-6, 1e-6, 3e-7)
DAMPRATIOS = (0.1, 0.2, 0.3, 0.5, 1.0)
SOLIMPS = {
    "default": (0.9, 0.95, 0.001, 0.5, 2.0),
    "stiff": (0.99, 0.999, 0.001, 0.5, 2.0),
}
# Per-protocol dt ladders are defined with the Protocol objects below.

# --- section 4: acceptance criteria -----------------------------------------

MAX_PENETRATION_MM = 0.3 * min(BALL_RADIUS_MM, BAT_RADIUS_MM)
COR_BAND = (0.3, 0.7)
REL_TOL = 0.02
COR_ABS_TOL = 0.01
PEN_ABS_TOL = 0.01 * MAX_PENETRATION_MM
MAX_ENERGY_RESIDUAL = 0.05
MAX_MOMENTUM_RESIDUAL = 0.01
TIMEOUT_TIMECONSTS = 2000.0
CHATTER_TIMECONSTS = 20.0

# The designed contact normal, pointing from target to ball.
N0 = np.array([-1.0, 0.0, 0.0])

# --- section 9.3: hold-out values, absent from v1 and from the diagnostic ---

HOLDOUT_SPEEDS_MM_S = (750.0, 3000.0)
HOLDOUT_ANGLES_DEG = (10.0, 28.0)
HOLDOUT_HIT_HEIGHTS_MM = (0.75,)


@dataclass(frozen=True)
class Config:
    kind: str  # "block" or "bat"
    speed_mm_s: float
    angle_deg: float
    bat_mass_g: float | None
    hit_height_mm: float

    @property
    def label(self) -> str:
        if self.kind == "block":
            return f"block v={self.speed_mm_s:g}"
        return (f"bat m={self.bat_mass_g:g} z={self.hit_height_mm:g} "
                f"v={self.speed_mm_s:g} a={self.angle_deg:g}")


@dataclass(frozen=True)
class Candidate:
    timeconst_s: float
    dampratio: float
    solimp: str

    @property
    def label(self) -> str:
        return f"tau={self.timeconst_s:g} zeta={self.dampratio:g} solimp={self.solimp}"


@dataclass(frozen=True)
class Protocol:
    name: str
    dt_divisors: tuple[int, ...]
    production_divisor: int
    use_holdout: bool
    evidence_name: str

    def __post_init__(self) -> None:
        if self.production_divisor not in self.dt_divisors:
            raise ValueError("production divisor must be on the ladder")
        if min(self.dt_divisors) < 2:
            raise ValueError("dt above timeconst/2 would trigger MuJoCo's silent clamp")

    @property
    def finest(self) -> int:
        return max(self.dt_divisors)

    @property
    def second_finest(self) -> int:
        return sorted(self.dt_divisors)[-2]


V1 = Protocol("v1", (2, 4, 8, 16), 4, use_holdout=False, evidence_name="G2-contact.json.gz")
V2 = Protocol("v2", (64, 128, 256, 512), 128, use_holdout=True, evidence_name="G2v2-contact.json.gz")
PROTOCOLS = {p.name: p for p in (V1, V2)}


@dataclass(frozen=True)
class ContactResult:
    config: Config
    candidate: Candidate
    timestep_s: float
    integrator: str
    separated: bool
    chatter: bool
    normal_flip: bool
    warnings: dict[str, int]
    max_penetration_mm: float
    normal_impulse: float
    cor: float
    duration_s: float
    energy_residual: float
    momentum_residual: float | None
    m_eff_g: float


def all_configs() -> list[Config]:
    out = [Config("block", v, 0.0, None, 0.0) for v in IMPACT_SPEEDS_MM_S]
    for m, z, v, a in product(BAT_MASSES_G, HIT_HEIGHTS_MM, IMPACT_SPEEDS_MM_S, BAT_IMPACT_ANGLES_DEG):
        out.append(Config("bat", v, a, m, z))
    return out


def holdout_configs() -> list[Config]:
    out = [Config("block", v, 0.0, None, 0.0) for v in HOLDOUT_SPEEDS_MM_S]
    for m, z, v, a in product(BAT_MASSES_G, HOLDOUT_HIT_HEIGHTS_MM, HOLDOUT_SPEEDS_MM_S, HOLDOUT_ANGLES_DEG):
        out.append(Config("bat", v, a, m, z))
    return out


def all_candidates() -> list[Candidate]:
    return [Candidate(t, z, s) for t, z, s in product(TIMECONSTS_S, DAMPRATIOS, SOLIMPS)]


def _xml(cfg: Config, cand: Candidate, dt: float, integrator: str) -> str:
    si = " ".join(repr(v) for v in SOLIMPS[cand.solimp])
    common = (f'condim="1" friction="0 0 0" margin="0" '
              f'solref="{cand.timeconst_s!r} {cand.dampratio!r}" solimp="{si}"')
    if cfg.kind == "block":
        b = BLOCK_HALF_SIZE_MM
        target = (f'<body name="target">'
                  f'<geom name="target" type="box" size="{b} {b} {b}" {common}/>'
                  f'<site name="hit" pos="{-b} 0 0"/></body>')
    else:
        h = BAT_HALF_LENGTH_MM
        target = (f'<body name="target"><freejoint/>'
                  f'<geom name="target" type="capsule" fromto="0 0 {-h} 0 0 {h}" '
                  f'size="{BAT_RADIUS_MM}" mass="{cfg.bat_mass_g!r}" {common}/>'
                  f'<site name="hit" pos="{-BAT_RADIUS_MM} 0 {cfg.hit_height_mm}"/></body>')
    ball = (f'<body name="ball" pos="-50 0 0"><freejoint/>'
            f'<geom name="ball" type="sphere" size="{BALL_RADIUS_MM}" mass="{BALL_MASS_G!r}" {common}/>'
            f'</body>')
    return (f'<mujoco model="g2">'
            f'<compiler angle="radian" boundmass="1e-06" boundinertia="1e-12"/>'
            f'<option timestep="{dt!r}" gravity="0 0 0" viscosity="0" density="0" '
            f'integrator="{integrator}"/>'
            f'<worldbody>{target}{ball}</worldbody></mujoco>')


def _surface_x(cfg: Config) -> float:
    return -BLOCK_HALF_SIZE_MM if cfg.kind == "block" else -BAT_RADIUS_MM


def run_contact(cfg: Config, cand: Candidate, dt: float, integrator: str = "Euler") -> ContactResult:
    if dt > cand.timeconst_s / 2 * (1 + 1e-12):
        raise ValueError("dt above timeconst/2: MuJoCo would silently raise the timeconst")

    m = mujoco.MjModel.from_xml_string(_xml(cfg, cand, dt, integrator))
    d = mujoco.MjData(m)

    ball_b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "ball")
    tgt_b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "target")
    ball_g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "ball")
    tgt_g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "target")
    hit_s = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "hit")
    ball_q = m.jnt_qposadr[m.body_jntadr[ball_b]]
    ball_v = m.jnt_dofadr[m.body_jntadr[ball_b]]
    free_bat = cfg.kind == "bat"
    tgt_v = m.jnt_dofadr[m.body_jntadr[tgt_b]] if free_bat else None

    a = math.radians(cfg.angle_deg)
    vhat = np.array([math.cos(a), math.sin(a), 0.0])
    contact_centre = np.array([_surface_x(cfg) - BALL_RADIUS_MM, 0.0, cfg.hit_height_mm])
    gap = APPROACH_TIMECONSTS * cand.timeconst_s * cfg.speed_mm_s
    d.qpos[ball_q:ball_q + 3] = contact_centre - gap * vhat
    d.qpos[ball_q + 3:ball_q + 7] = (1.0, 0.0, 0.0, 0.0)
    d.qvel[ball_v:ball_v + 3] = cfg.speed_mm_s * vhat
    mujoco.mj_forward(m, d)

    site_vel = np.zeros(6)

    def normal_rel_speed() -> float:
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_SITE, hit_s, site_vel, 0)
        return float((d.qvel[ball_v:ball_v + 3] - site_vel[3:]) @ N0)

    def linear_momentum() -> np.ndarray:
        p = m.body_mass[ball_b] * d.qvel[ball_v:ball_v + 3]
        if free_bat:
            p = p + m.body_mass[tgt_b] * d.qvel[tgt_v:tgt_v + 3]
        return p

    full_m = np.zeros((m.nv, m.nv))

    def kinetic_energy() -> float:
        mujoco.mj_fullM(m, d, full_m)
        return float(0.5 * d.qvel @ full_m @ d.qvel)

    def effective_mass() -> float:
        jb = np.zeros((3, m.nv))
        jt = np.zeros((3, m.nv))
        mujoco.mj_jacBodyCom(m, d, jb, None, ball_b)
        mujoco.mj_jacSite(m, d, jt, None, hit_s)
        row = N0 @ (jb - jt)
        mujoco.mj_fullM(m, d, full_m)
        return float(1.0 / (row @ np.linalg.solve(full_m, row)))

    pair = {ball_g, tgt_g}
    force = np.zeros(6)
    max_steps = math.ceil((APPROACH_TIMECONSTS * 3 + TIMEOUT_TIMECONSTS) * cand.timeconst_s / dt)
    chatter_steps = math.ceil(CHATTER_TIMECONSTS * cand.timeconst_s / dt)

    had_contact = separated = chatter = flip = False
    pre = None
    max_pen = impulse = 0.0
    t_first = t_last = 0.0
    post_steps = 0
    post = None

    for _ in range(max_steps):
        snapshot = (d.qvel.copy(), normal_rel_speed(), linear_momentum(), kinetic_energy())
        t_start = float(d.time)
        mujoco.mj_step(m, d)

        touching = False
        for i in range(d.ncon):
            c = d.contact[i]
            if {c.geom1, c.geom2} != pair:
                continue
            touching = True
            n = np.array(c.frame[:3]) * (1.0 if c.geom2 == ball_g else -1.0)
            if n @ N0 <= 0.0:
                flip = True
            max_pen = max(max_pen, -float(c.dist))
            mujoco.mj_contactForce(m, d, i, force)
            impulse += float(force[0]) * dt

        if touching:
            if not had_contact:
                had_contact = True
                pre = snapshot
                t_first = t_start
                m_eff = effective_mass()
            if separated:
                chatter = True
                break
            t_last = t_start + dt
        elif had_contact:
            if not separated:
                separated = True
                post = (normal_rel_speed(), linear_momentum(), kinetic_energy())
            post_steps += 1
            if post_steps >= chatter_steps:
                break

    warnings = {
        mujoco.mjtWarning(i).name: int(d.warning[i].number)
        for i in range(mujoco.mjtWarning.mjNWARNING)
        if d.warning[i].number
    }

    nan = float("nan")
    if pre is None or post is None:
        return ContactResult(cfg, cand, dt, integrator, separated, chatter, flip, warnings,
                             max_pen, impulse, nan, nan, nan, None, nan)

    _, vn_before, p_before, ke_before = pre
    vn_after, p_after, ke_after = post
    cor = -vn_after / vn_before
    expected_loss = 0.5 * m_eff * vn_before**2 * (1.0 - cor**2)
    energy_res = abs((ke_before - ke_after) - expected_loss) / ke_before
    mom_res = (float(np.linalg.norm(p_after - p_before) / np.linalg.norm(p_before))
               if free_bat else None)

    return ContactResult(cfg, cand, dt, integrator, separated, chatter, flip, warnings,
                         max_pen, impulse, cor, t_last - t_first, energy_res, mom_res, m_eff)


# --- judging ------------------------------------------------------------------


def _close(a: float, b: float, abs_tol: float | None) -> bool:
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    if abs_tol is not None and abs(a - b) <= abs_tol:
        return True
    return abs(a - b) <= REL_TOL * max(abs(b), 1e-300)


def _converged(x: ContactResult, ref: ContactResult) -> bool:
    return (_close(x.cor, ref.cor, COR_ABS_TOL)
            and _close(x.max_penetration_mm, ref.max_penetration_mm, PEN_ABS_TOL)
            and _close(x.normal_impulse, ref.normal_impulse, None))


def judge_config(by_divisor: dict[int, ContactResult], protocol: Protocol) -> dict[str, bool]:
    """C1-C9 for one (candidate, config), given its runs keyed by dt divisor."""
    prod = by_divisor[protocol.production_divisor]
    finest = by_divisor[protocol.finest]
    second = by_divisor[protocol.second_finest]
    lo, hi = COR_BAND
    return {
        "C1_penetration": prod.max_penetration_mm <= MAX_PENETRATION_MM,
        "C2_cor_band": math.isfinite(prod.cor) and lo <= prod.cor <= hi,
        "C3_finest_two_converged": _converged(second, finest),
        "C4_production_converged": _converged(prod, finest),
        "C5_energy": math.isfinite(prod.energy_residual) and prod.energy_residual <= MAX_ENERGY_RESIDUAL,
        "C6_momentum": prod.momentum_residual is None or prod.momentum_residual <= MAX_MOMENTUM_RESIDUAL,
        "C7_no_normal_flip": not any(r.normal_flip for r in by_divisor.values()),
        "C8_clean_separation": all(r.separated and not r.chatter for r in by_divisor.values()),
        "C9_no_warnings": not any(r.warnings for r in by_divisor.values()),
    }


def _run_ladder(cand: Candidate, configs: list[Config], protocol: Protocol) -> list[ContactResult]:
    return [
        run_contact(cfg, cand, cand.timeconst_s / k)
        for cfg in configs
        for k in protocol.dt_divisors
    ]


def _run_candidate(cand: Candidate, protocol: Protocol) -> list[ContactResult]:
    return _run_ladder(cand, all_configs(), protocol)


def _group(cand: Candidate, runs: list[ContactResult]) -> dict[Config, dict[int, ContactResult]]:
    grouped: dict[Config, dict[int, ContactResult]] = {}
    for r in runs:
        grouped.setdefault(r.config, {})[round(cand.timeconst_s / r.timestep_s)] = r
    return grouped


def _holdout_passes(cand: Candidate, protocol: Protocol) -> tuple[bool, dict[str, list[str]], list[dict]]:
    runs = _run_ladder(cand, holdout_configs(), protocol)
    grouped = _group(cand, runs)
    failures = {}
    for cfg, by_div in grouped.items():
        bad = sorted(k for k, ok in judge_config(by_div, protocol).items() if not ok)
        if bad:
            failures[cfg.label] = bad
    return not failures, failures, [asdict(r) for r in runs]


def _rk4_matches(cand: Candidate, euler: dict[Config, ContactResult],
                 protocol: Protocol) -> tuple[bool, list[str]]:
    failures = []
    dt = cand.timeconst_s / protocol.production_divisor
    for cfg in all_configs():
        rk = run_contact(cfg, cand, dt, integrator="RK4")
        eu = euler[cfg]
        if not (_close(rk.cor, eu.cor, COR_ABS_TOL)
                and _close(rk.max_penetration_mm, eu.max_penetration_mm, PEN_ABS_TOL)):
            failures.append(f"{cfg.label}: RK4 e={rk.cor:.4f} pen={rk.max_penetration_mm:.3e} "
                            f"vs Euler e={eu.cor:.4f} pen={eu.max_penetration_mm:.3e}")
    return not failures, failures


def evaluate(protocol: Protocol = V1, workers: int | None = None) -> dict:
    cands = all_candidates()
    configs = all_configs()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        per_cand = list(pool.map(partial(_run_candidate, protocol=protocol), cands))

    report = []
    passing = []
    for cand, runs in zip(cands, per_cand, strict=True):
        grouped = _group(cand, runs)
        verdicts = {cfg: judge_config(grouped[cfg], protocol) for cfg in configs}
        failed = {k for v in verdicts.values() for k, ok in v.items() if not ok}
        prod = {cfg: grouped[cfg][protocol.production_divisor] for cfg in configs}
        cors = [p.cor for p in prod.values()]
        entry = {
            "candidate": asdict(cand),
            "passes_all_configs": not failed,
            "failed_criteria": sorted(failed),
            "n_configs_passing": sum(all(v.values()) for v in verdicts.values()),
            "production": {
                "max_penetration_mm": max(p.max_penetration_mm for p in prod.values()),
                "cor_min": float(np.nanmin(cors)),
                "cor_max": float(np.nanmax(cors)),
                "cor_mean": float(np.nanmean(cors)),
                "worst_energy_residual": float(np.nanmax([p.energy_residual for p in prod.values()])),
                "worst_momentum_residual": max(
                    (p.momentum_residual for p in prod.values() if p.momentum_residual is not None),
                    default=None),
            },
            "per_config_failures": {
                cfg.label: sorted(k for k, ok in v.items() if not ok)
                for cfg, v in verdicts.items() if not all(v.values())
            },
            "runs": [asdict(r) for r in runs],
        }
        report.append(entry)
        if not failed:
            passing.append((cand, prod, entry))

    passing.sort(key=lambda t: (-t[0].timeconst_s,
                                0 if t[0].solimp == "default" else 1,
                                abs(t[2]["production"]["cor_mean"] - 0.5)))

    selected = None
    cross_checks = []
    holdout_checks = []
    for cand, prod, _ in passing:
        ok, failures = _rk4_matches(cand, prod, protocol)
        cross_checks.append({"candidate": asdict(cand), "rk4_matches": ok, "failures": failures})
        if not ok:
            continue
        if protocol.use_holdout:
            h_ok, h_failures, h_runs = _holdout_passes(cand, protocol)
            holdout_checks.append({"candidate": asdict(cand), "passes": h_ok,
                                   "failures": h_failures, "runs": h_runs})
            if not h_ok:
                continue
        selected = cand
        break

    return {
        "gate": "G2",
        "protocol": asdict(protocol),
        "verdict": "PASS" if selected else "FAIL",
        "selected": asdict(selected) if selected else None,
        "selected_production_timestep_s": (
            selected.timeconst_s / protocol.production_divisor if selected else None),
        "n_candidates": len(cands),
        "n_configs": len(configs),
        "n_passing_before_cross_check": len(passing),
        "passing_order": [asdict(c) for c, _, _ in passing],
        "integrator_cross_checks": cross_checks,
        "holdout_checks": holdout_checks,
        "n_holdout_configs": len(holdout_configs()) if protocol.use_holdout else 0,
        "candidates": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    args = parser.parse_args()
    protocol = PROTOCOLS[args.protocol]
    if args.out is None:
        args.out = EVIDENCE / protocol.evidence_name

    result = evaluate(protocol, args.workers)
    result.update({
        "date": datetime.now(timezone.utc).date().isoformat(),
        "platform": platform.platform(),
        "mujoco_version": mujoco.__version__,
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Every run is kept (the raw data behind each verdict), which makes the
    # file several MB. gzip with mtime=0 and an empty header filename keeps it
    # small and byte-stable (GzipFile otherwise embeds the output's name).
    payload = (json.dumps(result, indent=1, default=str) + "\n").encode()
    with open(args.out, "wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as fh:
        fh.write(payload)

    print(f"wrote {args.out}")
    print(f"G2 {protocol.name}: {result['verdict']}  "
          f"({result['n_passing_before_cross_check']}/{result['n_candidates']} candidates "
          f"pass all {result['n_configs']} configs before the RK4 cross-check)")
    if result["selected"]:
        print(f"selected: {result['selected']}  "
              f"production dt = {result['selected_production_timestep_s']:.3e} s")


if __name__ == "__main__":
    main()

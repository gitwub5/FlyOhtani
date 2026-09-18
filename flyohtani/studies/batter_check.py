"""The short contact check D29 promised: with ONE fixed dt (1e-6 s) and the
softened contact, does ball-bat contact at least not break physics?

This replaces the full G2-style protocol for the batter scene, per the user's
call to keep the environment simple. It is deliberately loose. It is NOT
loose about one thing: a collision must never create energy, because a policy
would learn to exploit that.

Criteria (fixed before this was run; see docs/records/BATTER-SCENE.md):

  K1  free bat: kinetic energy after <= before, every phase, every speed
  K2  free bat: 0.3 <= COR <= 0.7
  K3  free bat: COR spread across the 10 phases <= 0.05, per speed
  K4  penetration <= 50% of min(ball radius, barrel radius)
  K5  no MuJoCo warnings
  K6  in the real scene, a pitch into the held bat: the ball leaves the bat
      (moving away from it), no warnings, penetration within K4

Speeds 500-3000 mm/s: the demo swing's sweet spot peaks at 442 mm/s and a
Froude-scaled fastball is ~1.8 m/s, so 3 m/s covers their sum.

Run:  .venv/bin/python -m flyohtani.studies.batter_check
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import mujoco
import numpy as np

from flyohtani.world import batter as B

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

SPEEDS_MM_S = (500.0, 1000.0, 2000.0, 3000.0)
N_PHASES = 10
MAX_KE_RATIO = 1.0
COR_BAND = (0.3, 0.7)
MAX_COR_SPREAD = 0.05
MAX_PEN_FRACTION = 0.5


@dataclass(frozen=True)
class FreeImpact:
    speed_mm_s: float
    phase: float
    cor: float
    ke_ratio: float
    max_penetration_mm: float
    contact_steps: int
    warnings: dict[str, int]


def _warnings(d: mujoco.MjData) -> dict[str, int]:
    return {mujoco.mjtWarning(i).name: int(d.warning[i].number)
            for i in range(mujoco.mjtWarning.mjNWARNING) if d.warning[i].number}


def free_impact(speed: float, phase: float, scene: B.Scene,
                opts: B.SceneOptions = B.DEFAULT_SCENE) -> FreeImpact:
    """The scene's own bat mesh and ball, detached: a free bat struck
    head-on at its sweet spot, no gravity. Same contact settings as the scene."""
    # plain floats: numpy 2 reprs np.float64 as "np.float64(...)", which is
    # not valid MJCF.
    s = float(scene.scale)
    rb = float(B.BAT_BARREL_RADIUS_MM * s)
    r_ball = float(scene.ball_radius_mm)
    # The detached rig must use the SCENE's ball density, not the baseball
    # constant: D31 sets size and mass separately, and hard-coding the
    # constant here silently tested a ball the scene does not contain.
    ball_density = float(B.BALL_DENSITY * opts.ball_mass_scale / max(opts.ball_scale ** 3, 1e-12))
    vs, fs = B._lathe(B.bat_profile(s))
    z_sweet = 730 * s
    xml = f"""<mujoco><compiler boundmass="{B.BOUNDMASS!r}" boundinertia="1e-14"/>
<option timestep="{B.TIMESTEP_S!r}" gravity="0 0 0" integrator="Euler"/>
<default><geom solref="{B.CONTACT_TIMECONST_S!r} {B.CONTACT_DAMPRATIO!r}"
 solimp="{' '.join(repr(v) for v in B.CONTACT_SOLIMP)}" condim="1" friction="0 0 0"/></default>
<asset><mesh name="bat" vertex="{vs}" face="{fs}" inertia="exact"/></asset>
<worldbody>
<body name="bat"><freejoint/>
 <geom type="mesh" mesh="bat" density="{B.WOOD_DENSITY!r}" contype="0" conaffinity="0"/>
 <geom name="barrel" type="capsule" size="{rb!r}" fromto="0 0 {-(600 * s + rb)!r} 0 0 {-(845 * s - rb)!r}" mass="0"/>
</body>
<body name="ball"><freejoint/>
 <geom name="ball" type="sphere" size="{r_ball!r}" density="{ball_density!r}"/>
</body></worldbody></mujoco>"""
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    bq, bv = m.jnt_qposadr[1], m.jnt_dofadr[1]
    step = speed * B.TIMESTEP_S
    reach = rb + r_ball
    d.qpos[bq:bq + 3] = (-reach - 3 * step + phase * step, 0.0, -z_sweet)
    d.qvel[bv] = speed
    mujoco.mj_forward(m, d)
    full = np.zeros((m.nv, m.nv))
    mujoco.mj_fullM(m, d, full)
    ke0 = 0.5 * d.qvel @ full @ d.qvel
    pen, steps = 0.0, 0
    for _ in range(round(40 * B.CONTACT_TIMECONST_S / B.TIMESTEP_S)):
        mujoco.mj_step(m, d)
        if d.ncon:
            steps += 1
            pen = max(pen, -min(d.contact[i].dist for i in range(d.ncon)))
    mujoco.mj_fullM(m, d, full)
    ke1 = 0.5 * d.qvel @ full @ d.qvel
    # Relative speed, along the original contact normal (+x), between the ball
    # and the MATERIAL point of the bat that was struck. The bat has rotated
    # by the time this is read, so the lever arm must be rotated with it --
    # the first run of this check left it in the body frame, and the error
    # grew with impact speed (recorded in BATTER-SCENE.md).
    rot = d.xmat[1].reshape(3, 3)
    lever = rot @ np.array([-rb, 0.0, -z_sweet])
    point_v = d.qvel[0:3] + np.cross(rot @ d.qvel[3:6], lever)
    cor = -(d.qvel[bv] - point_v[0]) / speed
    return FreeImpact(speed, phase, float(cor), float(ke1 / ke0), float(pen), steps, _warnings(d))


def in_scene_pitch(speed: float, scene: B.Scene) -> dict:
    """K6: the real scene, bat held at CONTACT_POSE, ball thrown at the
    sweet spot from the pitcher's side."""
    m = scene.model()
    d = mujoco.MjData(m)
    B.set_arm(m, d, B.CONTACT_POSE)
    sweet = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "bat_sweet")
    ball = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "ball")
    qa, va = m.jnt_qposadr[m.body_jntadr[ball]], m.jnt_dofadr[m.body_jntadr[ball]]
    g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "ball")
    target = d.site_xpos[sweet].copy()
    # The ball must START clear of the bat. A fixed 0.6 mm stand-off was fine
    # for the scale-true 0.075 mm ball, but D31's ball has a 0.603 mm radius
    # and spawned already overlapping the barrel, which read as 0.076 mm of
    # penetration before the pitch had even moved. Stand off by the contact
    # reach plus a fixed run-up instead.
    reach = float(scene.ball_radius_mm + B.BAT_BARREL_RADIUS_MM * scene.scale)
    run_up = reach + 0.6
    start = target + np.array([run_up, 0.0, 0.0])
    d.qpos[qa:qa + 3] = start
    d.qvel[va:va + 3] = (-speed, 0.0, 0.0)
    m.opt.gravity[:] = 0  # K6 isolates the hit; the pitch arc is Phase 2's job
    mujoco.mj_forward(m, d)
    pen, touched = 0.0, False
    for _ in range(round((run_up / speed) * 1.5 / B.TIMESTEP_S) + 20000):
        mujoco.mj_step(m, d)
        for i in range(d.ncon):
            c = d.contact[i]
            if g in (c.geom1, c.geom2):
                touched = True
                pen = max(pen, -c.dist)
    return {"speed_mm_s": speed, "touched": touched, "ball_vx_after": float(d.qvel[va]),
            "leaves_bat": bool(touched and d.qvel[va] > -speed * 0.999),
            "max_penetration_mm": pen, "warnings": _warnings(d)}


def run(opts: B.SceneOptions = B.DEFAULT_SCENE) -> dict:
    scene = B.build_scene(opts)
    limit = MAX_PEN_FRACTION * min(scene.ball_radius_mm, B.BAT_BARREL_RADIUS_MM * scene.scale)
    free = [free_impact(v, (k + 0.5) / N_PHASES, scene, opts)
            for v in SPEEDS_MM_S for k in range(N_PHASES)]
    pitches = [in_scene_pitch(v, scene) for v in SPEEDS_MM_S]
    per_speed = {}
    for v in SPEEDS_MM_S:
        rows = [f for f in free if f.speed_mm_s == v]
        cors = [f.cor for f in rows]
        per_speed[str(v)] = {
            "cor_min": min(cors), "cor_max": max(cors), "cor_spread": max(cors) - min(cors),
            "ke_ratio_max": max(f.ke_ratio for f in rows),
            "penetration_max_mm": max(f.max_penetration_mm for f in rows),
            "contact_steps": sorted({f.contact_steps for f in rows}),
        }
    checks = {
        "K1_no_energy_created": all(f.ke_ratio <= MAX_KE_RATIO for f in free),
        "K2_cor_band": all(COR_BAND[0] <= f.cor <= COR_BAND[1] for f in free),
        "K3_phase_spread": all(p["cor_spread"] <= MAX_COR_SPREAD for p in per_speed.values()),
        "K4_penetration": all(f.max_penetration_mm <= limit for f in free)
                          and all(p["max_penetration_mm"] <= limit for p in pitches),
        "K5_no_warnings": not any(f.warnings for f in free),
        "K6_in_scene": all(p["touched"] and p["leaves_bat"] and not p["warnings"] for p in pitches),
    }
    return {
        "check": "batter-contact",
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "settings": {"timestep_s": B.TIMESTEP_S, "timeconst_s": B.CONTACT_TIMECONST_S,
                     "dampratio": B.CONTACT_DAMPRATIO, "scale": scene.scale,
                     "ball_scale": opts.ball_scale, "ball_mass_scale": opts.ball_mass_scale,
                     "ball_radius_mm": scene.ball_radius_mm,
                     "barrel_radius_mm": B.BAT_BARREL_RADIUS_MM * scene.scale,
                     "penetration_limit_mm": limit},
        "per_speed": per_speed,
        "in_scene": pitches,
        "free_impacts": [asdict(f) for f in free],
    }


def main() -> None:
    result = run()
    out = EVIDENCE / "batter-contact-check.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(f"wrote {out}")
    print(f"batter contact check: {result['verdict']}")
    for k, v in result["checks"].items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    for v, p in result["per_speed"].items():
        print(f"  v={float(v):>6.0f}  COR {p['cor_min']:.3f}-{p['cor_max']:.3f}  KE max {p['ke_ratio_max']:.3f}  "
              f"pen {p['penetration_max_mm']:.4f} mm  steps {p['contact_steps']}")
    for p in result["in_scene"]:
        print(f"  in-scene v={p['speed_mm_s']:.0f}: touched={p['touched']} leaves={p['leaves_bat']} "
              f"pen={p['max_penetration_mm']:.4f} warn={p['warnings'] or 'none'}")
    print(f"  penetration limit {result['settings']['penetration_limit_mm']:.4f} mm")


if __name__ == "__main__":
    main()

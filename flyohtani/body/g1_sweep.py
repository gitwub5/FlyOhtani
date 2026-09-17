"""G1 (docs/PLAN.md Phase 1): can the fly's own foreleg swing a bat, and how
fast can the bat tip go?

This is a CAPABILITY MEASUREMENT, not a swing search. v1 burned 6,700 lines
hand-optimising human-style swing candidates and retracted the result, so
this deliberately does the dumbest well-defined thing: step every foreleg
actuator to the same target angle at t=0, let the position controllers
saturate against their force range, and record the peak speed the bat tip
reaches. Sweeping the target angle and both signs gives an upper bound on
bat-tip speed for a given tool, which is the number Phase 2 needs to size
the ball, the pitch and the field.

What this does NOT do, on purpose: coordinate the joints, tune a trajectory,
or claim the resulting motion resembles a swing. A number produced here is
"the fastest this arm moved a tool under a saturating step command", nothing
more.

Run:  .venv/bin/python -m flyohtani.body.g1_sweep
"""
from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import mujoco
import numpy as np

from flyohtani.body.minimal_body import ACTIVE_JOINTS, BatSpec, BuildOptions, build_minimal_body_xml

EVIDENCE = Path(__file__).resolve().parent.parent.parent / "docs" / "records" / "evidence"

# Pre-registered sweep grid (fixed before looking at any result).
BAT_MASSES_G = (5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5)
"""Bracketing the foreleg's own mass (1.389e-5 g): from ~4% of it to ~1.4x
it. A tool heavier than the limb that swings it is not interesting."""

BAT_LENGTHS_MM = (0.5, 1.0, 2.0, 4.0)
"""Foreleg reach is ~1.81 mm, so this spans a quarter of the reach to over
twice it."""

TARGET_ANGLES_RAD = (0.5, 1.0, 1.5, 2.0, 3.0)
SWING_DURATION_S = 0.05


@dataclass(frozen=True)
class SwingResult:
    bat_mass_g: float
    bat_length_mm: float
    compiled_bat_mass_g: float
    mass_was_clamped: bool
    target_rad: float
    sign: int
    timestep: float
    integrator: str
    boundmass: float
    peak_tip_speed_mm_s: float
    peak_tip_speed_time_s: float
    tip_travel_mm: float
    peak_joint_speed_rad_s: float
    mean_abs_joint_error_rad: float
    saturated_fraction: float
    stable: bool
    warnings: dict[str, int]


DEFAULT_TIMESTEP = 2.5e-5
"""Finer than the source model's 1e-4. See LOCKED_DOFS in minimal_body.py:
the published defaults cannot integrate their own roll joints under a
saturating command. Those are locked here, which makes 1e-4 admissible
again, but the margin is small enough that the sweep buys some back."""


def _run_one(
    bat: BatSpec,
    target_rad: float,
    sign: int,
    *,
    timestep: float = DEFAULT_TIMESTEP,
    integrator: str = "Euler",
    boundmass: float = 1e-6,
    duration_s: float = SWING_DURATION_S,
) -> SwingResult:
    opts = BuildOptions(timestep=timestep, boundmass=boundmass, integrator=integrator,
                        include_visual_body=False)
    model = mujoco.MjModel.from_xml_string(build_minimal_body_xml(bat=bat, opts=opts))
    data = mujoco.MjData(model)

    bat_bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "bat")
    tip_sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "bat_tip")
    jids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j) for j in ACTIVE_JOINTS]
    qadr = [model.jnt_qposadr[j] for j in jids]
    force_hi = float(model.actuator_forcerange[0][1])

    mujoco.mj_forward(model, data)
    start_tip = data.site_xpos[tip_sid].copy()
    data.ctrl[:] = sign * target_rad

    peak_speed = 0.0
    peak_t = 0.0
    peak_qvel = 0.0
    saturated = 0
    n_steps = round(duration_s / timestep)
    vel = np.zeros(6)
    for _ in range(n_steps):
        mujoco.mj_step(model, data)
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_SITE, tip_sid, vel, 0)
        speed = float(np.linalg.norm(vel[3:]))
        if speed > peak_speed:
            peak_speed, peak_t = speed, float(data.time)
        peak_qvel = max(peak_qvel, float(np.max(np.abs(data.qvel))))
        if np.any(np.abs(data.actuator_force) >= force_hi * 0.999):
            saturated += 1

    # A diverged run still produces numbers. v1's retracted result came from
    # trusting exactly that, so instability is recorded per run and the
    # summary never selects a "best" from an unstable one.
    warnings = {
        mujoco.mjtWarning(i).name: int(data.warning[i].number)
        for i in range(mujoco.mjtWarning.mjNWARNING)
        if data.warning[i].number
    }
    finite = bool(np.all(np.isfinite(data.qpos)) and np.all(np.isfinite(data.qvel)))

    errors = [abs(float(data.qpos[a]) - sign * target_rad) for a in qadr]
    return SwingResult(
        bat_mass_g=bat.mass_g,
        bat_length_mm=bat.length_mm,
        compiled_bat_mass_g=float(model.body_mass[bat_bid]),
        mass_was_clamped=bool(model.body_mass[bat_bid] > bat.mass_g * 1.001),
        target_rad=target_rad,
        sign=sign,
        timestep=timestep,
        integrator=integrator,
        boundmass=boundmass,
        peak_tip_speed_mm_s=peak_speed,
        peak_tip_speed_time_s=peak_t,
        tip_travel_mm=float(np.linalg.norm(data.site_xpos[tip_sid] - start_tip)),
        peak_joint_speed_rad_s=peak_qvel,
        mean_abs_joint_error_rad=float(np.mean(errors)),
        saturated_fraction=saturated / n_steps,
        stable=(not warnings) and finite,
        warnings=warnings,
    )


def run_sweep() -> list[SwingResult]:
    out: list[SwingResult] = []
    for mass in BAT_MASSES_G:
        for length in BAT_LENGTHS_MM:
            for target in TARGET_ANGLES_RAD:
                for sign in (+1, -1):
                    out.append(_run_one(BatSpec(mass_g=mass, length_mm=length), target, sign))
    return out


def dt_convergence(best: SwingResult, timesteps: tuple[float, ...]) -> list[SwingResult]:
    """Same command, finer physics. v1's whole coordination conclusion flipped
    under this check, so nothing here gets reported without it."""
    bat = BatSpec(mass_g=best.bat_mass_g, length_mm=best.bat_length_mm)
    return [_run_one(bat, best.target_rad, best.sign, timestep=dt) for dt in timesteps]


def integrator_cross_check(best: SwingResult, timestep: float) -> list[SwingResult]:
    """Three integrators, one command. Agreement is the evidence that the
    number is a property of the model and not of the stepping scheme."""
    bat = BatSpec(mass_g=best.bat_mass_g, length_mm=best.bat_length_mm)
    return [
        _run_one(bat, best.target_rad, best.sign, timestep=timestep, integrator=integ)
        for integ in ("Euler", "implicitfast", "RK4")
    ]


def boundmass_sensitivity(best: SwingResult) -> list[SwingResult]:
    """Does MuJoCo's mass clamping change the answer? The source model's
    boundmass (1e-6) sits inside the swept bat-mass range, so this is not a
    hypothetical."""
    bat = BatSpec(mass_g=best.bat_mass_g, length_mm=best.bat_length_mm)
    return [_run_one(bat, best.target_rad, best.sign, boundmass=bm) for bm in (1e-6, 1e-9)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=EVIDENCE / "G1-swing-sweep.json")
    args = parser.parse_args()

    results = run_sweep()
    stable = [r for r in results if r.stable]
    if not stable:
        raise RuntimeError("every run in the sweep was unstable -- nothing to report")
    best = max(stable, key=lambda r: r.peak_tip_speed_mm_s)
    dt_runs = dt_convergence(best, (1e-4, 2.5e-5, 6.25e-6, 1.5625e-6))
    bm_runs = boundmass_sensitivity(best)
    integ_runs = integrator_cross_check(best, timestep=1.5625e-6)

    speeds = [r.peak_tip_speed_mm_s for r in dt_runs[-2:]]
    dt_rel = abs(speeds[1] - speeds[0]) / max(speeds[0], 1e-12)
    integ_speeds = [r.peak_tip_speed_mm_s for r in integ_runs]
    integ_spread = (max(integ_speeds) - min(integ_speeds)) / max(min(integ_speeds), 1e-12)

    payload = {
        "gate": "G1",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "platform": platform.platform(),
        "mujoco_version": mujoco.__version__,
        "protocol": (
            "step every foreleg position actuator to the same target at t=0, "
            "run for 50 ms, record peak bat-tip speed. No trajectory tuning."
        ),
        "grid": {
            "bat_mass_g": list(BAT_MASSES_G),
            "bat_length_mm": list(BAT_LENGTHS_MM),
            "target_rad": list(TARGET_ANGLES_RAD),
            "signs": [1, -1],
        },
        "n_runs": len(results),
        "n_unstable": len(results) - len(stable),
        "best": asdict(best),
        "dt_convergence": {
            "runs": [asdict(r) for r in dt_runs],
            "finest_two_relative_difference": dt_rel,
        },
        "integrator_cross_check": {
            "runs": [asdict(r) for r in integ_runs],
            "relative_spread": integ_spread,
        },
        "boundmass_sensitivity": [asdict(r) for r in bm_runs],
        "all_runs": [asdict(r) for r in results],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {args.out}")
    print(f"runs: {len(results)}  unstable: {len(results) - len(stable)}")
    print(f"best: {best.peak_tip_speed_mm_s:.1f} mm/s tip  "
          f"({best.peak_joint_speed_rad_s:.0f} rad/s peak joint)  "
          f"bat {best.bat_mass_g:.1e} g x {best.bat_length_mm} mm, "
          f"target {best.sign * best.target_rad} rad")
    print(f"dt convergence (finest two): {dt_rel * 100:.2f}%")
    print(f"integrator spread:           {integ_spread * 100:.2f}%")


if __name__ == "__main__":
    main()

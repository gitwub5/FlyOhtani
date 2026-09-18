from __future__ import annotations

import argparse
from pathlib import Path

from flyohtani.record.scenarios import PitchSpec, run_pitch, run_swing


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m flyohtani.record",
                                     description="Record a scripted episode as video and stills.")
    sub = parser.add_subparsers(dest="scenario", required=True)
    p = sub.add_parser("pitch", help="a pitched ball meets the demo swing")
    p.add_argument("--speed-scale", type=float, default=1.0,
                   help="x the Kershaw-class fastball (default 1.0 = 1888 mm/s)")
    p.add_argument("--timing-ms", type=float, default=0.0,
                   help="ball arrives this much later than the bat (0 aims for a hit)")
    p.add_argument("--aim-z-mm", type=float, default=0.0,
                   help="raise the aim point: the scripted swing meets the ball above "
                        "its centre and chops it into the ground, and +0.05 puts the bat "
                        "under it for a line drive")
    p.add_argument("--aim-y-mm", type=float, default=0.0, help="move the aim point toward third base")
    p.add_argument("--out", type=Path, default=None)
    s = sub.add_parser("swing", help="the demo swing alone")
    s.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if args.scenario == "pitch":
        out, manifest = run_pitch(
            PitchSpec(speed_scale=args.speed_scale, timing_ms=args.timing_ms,
                      aim_offset_mm=(0.0, args.aim_y_mm, args.aim_z_mm)),
            out_dir=args.out)
        print(f"contact={out.contact}  exit={out.exit_speed_mm_s}  launch={out.launch_angle_deg}  "
              f"spray={out.spray_angle_deg}  carry={out.carry_mm} mm (~{out.carry_real_m} m real)  fair={out.fair}")
    else:
        manifest = run_swing(out_dir=args.out)
    files = manifest.get("files", {})
    print("wrote", files)


if __name__ == "__main__":
    main()

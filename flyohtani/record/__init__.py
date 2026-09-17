"""Videos and stills of simulated episodes, for people to watch.

    .venv/bin/python -m flyohtani.record pitch            # a pitched ball meets the demo swing
    .venv/bin/python -m flyohtani.record pitch --timing-ms 6   # same pitch, 6 ms late: a miss
    .venv/bin/python -m flyohtani.record swing            # the demo swing alone

Outputs land in runs/record/<time>-<scenario>/: video.mp4, sheet.png,
final.png and manifest.json (what was run, at which commit, and what
happened). runs/ is not committed.
"""

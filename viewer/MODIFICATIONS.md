# Modifications to fly-connectome-template

Required by section 4 of `LICENSE`: this directory is a modified version of
[fly-connectome-template](https://github.com/cobanov/fly-connectome-template)
by [Mert Cobanov](https://github.com/cobanov), vendored at commit
`38f55332055328d38c29e72474c4ad5b6876101f` (see `PROVENANCE.json`).

## Removed at import

- `.github/` (CI workflow; it does not run from a subdirectory of another repo).

No other file was changed at import; the vendoring commit contains the
template byte-for-byte as it was at that commit.

## Changed afterwards

Listed per change, newest last. The attribution component and every license
and notice file are unchanged.

### 2026-09-17 — show a FlyOhtani episode and its circuit

- `src/components/Environment.tsx`: replaced the example moving-spot stimulus
  with a recorded FlyOhtani episode (`public/experiment/video.mp4`) and its
  outcome (`public/experiment/experiment.json`). The video is not
  synchronised with the brain timeline; the panel says so.
- `src/App.tsx`: header renamed to FLYOHTANI; added a "Load FlyOhtani
  circuit" button that loads `public/experiment/circuit.replay.json`, and
  loads it automatically once the atlas is ready if the file exists; the
  environment panel footer now describes the recording. The template's
  synthetic-example button, the replay validation and the attribution
  footer are unchanged. A `?t=<seconds>` query opens the loaded circuit
  paused at that time.
- `src/style.css`: appended styles for the video and outcome list.
- The episode video uses `public/experiment/poster.png` (the run's final
  frame) as its poster, so the result shows before playback.
- `public/experiment/` (gitignored) is written by
  `python -m flyohtani.brain.replay`, not by hand.

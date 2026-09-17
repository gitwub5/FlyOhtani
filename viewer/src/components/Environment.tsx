import { useEffect, useState } from 'react';
import { asset } from '../lib/atlas';

/**
 * FlyOhtani modification (see MODIFICATIONS.md): the template's example
 * stimulus is replaced by a recorded FlyOhtani episode, exported by
 * `python -m flyohtani.brain.replay --run runs/record/<run>` into
 * public/experiment/. The video has its own controls; it is NOT synchronised
 * with the brain timeline, because nothing in the brain panel is driven by
 * this episode yet.
 */
type Outcome = {
  contact?: boolean; exit_speed_mm_s?: number | null; launch_angle_deg?: number | null;
  carry_mm?: number | null; carry_real_m?: number | null; fair?: boolean | null;
};
type Experiment = { run?: string; scenario?: string; scripted?: boolean; outcome?: Outcome; recorded_at_commit?: string | null };

const fmt = (v: number | null | undefined, digits = 0) => (v == null ? '—' : v.toFixed(digits));

export function Environment({ time: _time }: { time: number }) {
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    fetch(asset('experiment/experiment.json'), { signal: abort.signal })
      .then(r => (r.ok ? r.json() : Promise.reject(Error('no bundle'))))
      .then(setExperiment)
      .catch(() => { if (!abort.signal.aborted) setMissing(true); });
    return () => abort.abort();
  }, []);

  if (missing) {
    return <div className="environment">
      <p>No FlyOhtani episode exported yet.</p>
      <span>Run <code>python -m flyohtani.record pitch</code>, then <code>python -m flyohtani.brain.replay --run runs/record/&lt;run&gt;</code>.</span>
    </div>;
  }
  const o = experiment?.outcome;
  return <div className="environment flyohtani-environment">
    <video src={asset('experiment/video.mp4')} poster={asset('experiment/poster.png')} controls muted playsInline loop preload="metadata" aria-label="Recorded FlyOhtani episode" />
    {experiment && <dl className="flyohtani-outcome">
      <div><dt>Scenario</dt><dd>{experiment.scenario ?? '—'}{experiment.scripted ? ' · scripted swing' : ''}</dd></div>
      <div><dt>Contact</dt><dd>{o?.contact ? 'hit' : 'miss'}</dd></div>
      {o?.contact && <>
        <div><dt>Exit speed</dt><dd>{fmt(o.exit_speed_mm_s)} mm/s</dd></div>
        <div><dt>Launch</dt><dd>{fmt(o.launch_angle_deg)}°</dd></div>
        <div><dt>Carry</dt><dd>{fmt(o.carry_mm, 2)} mm (~{fmt(o.carry_real_m, 1)} m) · {o.fair ? 'fair' : 'foul'}</dd></div>
      </>}
    </dl>}
  </div>;
}

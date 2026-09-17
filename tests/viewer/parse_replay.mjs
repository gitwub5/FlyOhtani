// Runs viewer/src/lib/replay.ts's own parseReplay on a replay file, against
// the viewer's own atlas. Exit 0 = the viewer would accept it.
// usage: node --experimental-strip-types tests/viewer/parse_replay.mjs <replay.json>
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseReplay } from '../../viewer/src/lib/replay.ts';

const root = resolve(import.meta.dirname, '../../viewer/public/data/brain-atlas');
const manifest = JSON.parse(readFileSync(`${root}/manifest.json`, 'utf8'));
const ids = new Uint32Array(readFileSync(`${root}/ids.bin`).buffer.slice(0));
const groups = new Uint8Array(readFileSync(`${root}/groups.bin`));
if (ids.length !== manifest.count || groups.length !== manifest.count) throw Error('atlas length mismatch');
const visible = new Set(Array.from(ids).filter((_, i) => groups[i] < 3));
const replay = parseReplay(JSON.parse(readFileSync(process.argv[2], 'utf8')), visible);
console.log(JSON.stringify({ ok: true, frames: replay.frames.length, kind: replay.source.kind }));

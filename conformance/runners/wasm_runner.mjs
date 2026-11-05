// © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
// SPDX-License-Identifier: GPL-3.0-or-later
// WebAssembly conformance runner: node wasm_runner.mjs <module.wasm> <symbol> <file.vec>
import { readFileSync } from 'node:fs';
const [wasmPath, sym, vecPath] = process.argv.slice(2);
const { instance } = await WebAssembly.instantiate(readFileSync(wasmPath), {});
const f = instance.exports[sym];
if (typeof f !== 'function') { console.error(`no export ${sym}`); process.exit(2); }
let n = 0, bad = 0, unary = null;
for (const line of readFileSync(vecPath, 'utf8').split('\n')) {
  if (!line) continue;
  if (line.startsWith('#')) { if (line.startsWith('# fields:')) unary = !line.includes(' b '); continue; }
  const p = line.split(' ').map((h) => BigInt('0x' + h));
  const [a, b, r] = unary ? [p[0], 0n, p[1]] : p;
  const got = BigInt.asUintN(64, f(BigInt.asIntN(64, a), BigInt.asIntN(64, b)));
  n++;
  if (got !== r) { if (bad < 5) console.log(`MISMATCH a=${a.toString(16)} b=${b.toString(16)} expected=${r.toString(16)} got=${got.toString(16)}`); bad++; }
}
console.log(`wasm ${sym} cases=${n} disagreements=${bad}`);
process.exit(bad ? 1 : 0);

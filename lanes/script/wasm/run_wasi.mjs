// © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
// SPDX-License-Identifier: GPL-3.0-or-later
// Runs a WASI (preview1) build of APCISR's filter under Node.js: node run_wasi.mjs <module.wasm> <stdin file> <stdout file>
// Uses node:wasi as documented for Node 22 (new WASI({ version, args, stdin, stdout }), wasi.getImportObject(), wasi.start()).
import { readFileSync, openSync, closeSync } from 'node:fs';
import { WASI } from 'node:wasi';
import process from 'node:process';

const [wasmPath, inPath, outPath] = process.argv.slice(2);
const stdin = openSync(inPath, 'r');
const stdout = openSync(outPath, 'w');
const wasi = new WASI({ version: 'preview1', args: ['acii2csr'], env: {}, stdin, stdout, stderr: 2, returnOnExit: true });
const module = await WebAssembly.compile(readFileSync(wasmPath));
const instance = await WebAssembly.instantiate(module, wasi.getImportObject());
const code = wasi.start(instance);
closeSync(stdin);
closeSync(stdout);
process.exitCode = code ?? 0;

<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Teaching lab (P8.2)

Each exercise runs on the reference unit from one command, in a scratch clone under `.cache/lab/`, so the
working tree is never disturbed. Every exercise prints what it changed, what the harness predicted would
regenerate, what actually changed, and whether the two agree.

| Exercise | Command | What you watch |
|---|---|---|
| 1. Change an encoding | `lab/run.sh change-encoding` | Balanced ternary moves from the pair encoding to two bit-planes; the codec, libraries, vectors, QEMU helpers, intrinsics and hardware units regenerate, and nothing in the script lane does |
| 2. Add an operation | `lab/run.sh add-operation` | An `abs` operation is appended to the specification with its reference function; only its glue, vectors and instruction candidate appear |
| 3. Add an instruction | `lab/run.sh add-instruction` | The new operation is allocated in the ledger, assembled with `.insn`, and run in QEMU with the CPU property on and off |

Questions to ask yourself after each run are in `lab/questions.md`.

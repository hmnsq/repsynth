<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# On-board run procedure (P5.10, HDL-08): a human packet

State: **not built**. No board was at hand; nothing here has run on hardware. This page is the procedure a person
with a board follows, and what they record.

## Board and flow

- Any iCE40 UP5K board with an SG48 package and a USB programmer (for example the open UPduino or iCEBreaker
  designs). The figures in synthesis.md were placed for that part; another iCE40 part needs `repsynth hdl synth`
  rerun with its device and package.
- Open flow only: Yosys, nextpnr-ice40, icepack, iceprog (fpga-icestorm), the versions recorded in synthesis.md.

## Steps

1. `python3 -m repsynth hdl synth` (or `ops/run.sh --iteration I6`) and note the run record's tool versions.
2. Choose a unit whose measured maximum frequency is above the board clock, or divide the clock: the ripple
   adders measure about 5 to 10 MHz in the serial wrapper, below the 12 MHz oscillator common on these boards.
3. The serial wrapper (rs_wrap) shifts operands in on `sin` and results out on `sout`, one bit per clock, with
   `cap` capturing the result. Driving it from a host needs a UART or SPI front end and a clock divider; that
   front end is **not built** and is the first piece of work for this packet.
4. Flash: `iceprog .cache/hdl/synth/<unit>/run1/rs_wrap.bin` (after adding the front end, a new bitstream).
5. Drive every case of `conformance/vectors/balanced_ternary/<op>.<digits>.vec` through the front end and compare
   each result with the file's expected field.

## What to record, together (HDL-08)

- Board name and revision, the part marking, the programmer.
- Tool versions (yosys -V, nextpnr-ice40 --version, icepack and iceprog package versions) and the bitstream sha256.
- The unit, the vector file and its sha256, cases run, mismatches, the clock used.
- A run record `records/<UTC>_P5.10_onboard.json` written with repsynth/records.py, state `done` only if every
  vector passed on the board.

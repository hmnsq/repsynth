# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Script lane generators (component H9; MRD 10.11, SCR-01 to SCR-06).

refs      locates and hashes the pinned script references (P6.2)
ucd       reads the pinned Unicode Character Database files
icu       ICU 74 through its C API: UnicodeSet patterns (CLDR exemplars) and grapheme clusters
apcisr    APCISR's own table format: emitting apcisr.h and cisr2asc.h, and dumping compiled tables
derive    candidate grid tables for scripts outside the author's canon (GEN-05, SCR-02)
build     derived APCISR builds per script, native (APCISR's Makefile) and WebAssembly (wasi-libc)
"""
GENERATOR_VERSION = "repsynth.gen.script 0.3.0"
NOTICE = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI."

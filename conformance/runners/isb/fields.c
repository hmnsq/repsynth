/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Exported wrappers of the family's field functions, so the encoding round-trip property can decode
 * with the C reference instead of the Python encoder that produced the words. */
#include "word_machine_family.h"
uint64_t isb_field(uint64_t insn, uint64_t hi, uint64_t lo) { return wmf_field(insn, hi, lo); }
uint64_t isb_sfield(uint64_t insn, uint64_t hi, uint64_t lo) { return wmf_sfield(insn, hi, lo); }
uint64_t isb_place(uint64_t v, uint64_t hi, uint64_t lo) { return wmf_place(v, hi, lo); }

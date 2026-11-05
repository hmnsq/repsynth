/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Field access of the word machine family's fixed 32-bit encoding (spec/reps/machine/word_machine_family.yaml,
 * /encoding/encodings/fixed32). Restricted C11: pure, fixed-width types, no allocation, no input or output.
 * Used by the encoding round-trip property, independently of the Python encoder. */
#ifndef WORD_MACHINE_FAMILY_H
#define WORD_MACHINE_FAMILY_H
#include <stdint.h>
/* Unsigned field [hi, lo] of an instruction word. */
static inline uint64_t wmf_field(uint64_t insn, uint64_t hi, uint64_t lo)
{ return (insn >> lo) & ((((uint64_t)1) << (hi - lo + 1u)) - 1u); }
/* Signed field [hi, lo], sign-extended to 64 bits (two's complement). */
static inline uint64_t wmf_sfield(uint64_t insn, uint64_t hi, uint64_t lo)
{
  uint64_t w = hi - lo + 1u, v = wmf_field(insn, hi, lo), s = ((uint64_t)1) << (w - 1u);
  return (v ^ s) - s;
}
/* The word with value v placed in field [hi, lo] (v is truncated to the field width). */
static inline uint64_t wmf_place(uint64_t v, uint64_t hi, uint64_t lo)
{ return (v & ((((uint64_t)1) << (hi - lo + 1u)) - 1u)) << lo; }
#endif

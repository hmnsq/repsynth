/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Reference functions for binary_integer, the performance baseline (RD5, NUM-06).
 * Two's complement on 64-bit and 32-bit registers; arithmetic on unsigned types so wrapping is defined. */
#include "binary_integer.h"

static uint64_t m32(uint64_t x) { return x & 0xffffffffu; }
static int64_t s32(uint64_t x) { return (int64_t)(int32_t)(uint32_t)(x & 0xffffffffu); }

uint64_t bin_neg64(uint64_t a, uint64_t b) { (void)b; return (uint64_t)0u - a; }
uint64_t bin_neg32(uint64_t a, uint64_t b) { (void)b; return m32((uint64_t)0u - a); }
uint64_t bin_add64(uint64_t a, uint64_t b) { return a + b; }
uint64_t bin_add32(uint64_t a, uint64_t b) { return m32(a + b); }
uint64_t bin_sub64(uint64_t a, uint64_t b) { return a - b; }
uint64_t bin_sub32(uint64_t a, uint64_t b) { return m32(a - b); }
uint64_t bin_mul64(uint64_t a, uint64_t b) { return a * b; }
uint64_t bin_mul32(uint64_t a, uint64_t b) { return m32(m32(a) * m32(b)); }
uint64_t bin_cmp64(uint64_t a, uint64_t b) {
  int64_t x = (int64_t)a, y = (int64_t)b;
  return x < y ? ~(uint64_t)0 : (x > y ? 1u : 0u);
}
uint64_t bin_cmp32(uint64_t a, uint64_t b) {
  int64_t x = s32(a), y = s32(b);
  return x < y ? 0xffffffffu : (x > y ? 1u : 0u);
}
uint64_t bin_shl64(uint64_t a, uint64_t b) { return a << (b & 63u); }
uint64_t bin_shl32(uint64_t a, uint64_t b) { return m32(m32(a) << (b & 31u)); }
/* Arithmetic right shift without relying on implementation-defined signed shifts. */
uint64_t bin_shr64(uint64_t a, uint64_t b) {
  unsigned k = (unsigned)(b & 63u);
  uint64_t r = a >> k;
  if ((a >> 63) && k) r |= ~(~(uint64_t)0 >> k);
  return r;
}
uint64_t bin_shr32(uint64_t a, uint64_t b) {
  unsigned k = (unsigned)(b & 31u);
  uint64_t x = m32(a), r = x >> k;
  if ((x >> 31) && k) r |= m32(~(0xffffffffu >> k));
  return r;
}

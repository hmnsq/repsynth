/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Reference functions for balanced_ternary (NUM-02, NUM-03). The trit codec comes from the
 * generated bt_codec.h, so a change of encoding in the specification regenerates only the codec.
 * Restricted C11: every intermediate fits in int64_t (3^32 < 2^51), no undefined behaviour. */
#include "balanced_ternary.h"
#include "bt_codec.h"

static int64_t pow3(unsigned n) { int64_t m = 1; for (unsigned i = 0; i < n; i++) m *= 3; return m; }

static uint64_t word_mask(unsigned n) { return n >= 32u ? ~(uint64_t)0 : (((uint64_t)1u << (2u * n)) - 1u); }

static uint64_t reg_mask(unsigned n) { return n >= 32u ? ~(uint64_t)0 : 0xffffffffu; }

static int valid_word(uint64_t w, unsigned n) {
  for (unsigned i = 0; i < n; i++) if (bt_code_value(bt_code_get(w, i, n)) == 2) return 0;
  return 1;
}

static int64_t decode(uint64_t w, unsigned n) {
  int64_t v = 0;
  for (unsigned k = n; k > 0; k--) v = v * 3 + bt_code_value(bt_code_get(w, k - 1u, n));
  return v;
}

/* Reduce any int64 into the balanced range modulo 3^n, without overflow. */
static int64_t reduce(int64_t x, unsigned n) {
  int64_t m = pow3(n), h = (m - 1) / 2;
  int64_t r = x % m;              /* |r| < m */
  if (r > h) r -= m;
  if (r < -h) r += m;
  return r;
}

static uint64_t encode(int64_t v, unsigned n) {
  uint64_t w = 0;
  v = reduce(v, n);
  for (unsigned i = 0; i < n; i++) {
    int64_t t = v % 3;           /* -2..2 */
    if (t == 2) t = -1;
    if (t == -2) t = 1;
    w = bt_code_put(w, i, n, bt_value_code((int)t));
    v = (v - t) / 3;
  }
  return w;
}

static uint64_t invalid(unsigned n) { return word_mask(n); }

static uint64_t neg(uint64_t a, unsigned n) {
  a &= word_mask(n);
  if (!valid_word(a, n)) return invalid(n);
  return encode(-decode(a, n), n);
}
static uint64_t add(uint64_t a, uint64_t b, unsigned n) {
  a &= word_mask(n); b &= word_mask(n);
  if (!valid_word(a, n) || !valid_word(b, n)) return invalid(n);
  return encode(decode(a, n) + decode(b, n), n);
}
static uint64_t sub(uint64_t a, uint64_t b, unsigned n) {
  a &= word_mask(n); b &= word_mask(n);
  if (!valid_word(a, n) || !valid_word(b, n)) return invalid(n);
  return encode(decode(a, n) - decode(b, n), n);
}
/* Low n trits of the product: shift-and-add modulo 3^n on non-negative residues. */
static uint64_t mul(uint64_t a, uint64_t b, unsigned n) {
  a &= word_mask(n); b &= word_mask(n);
  if (!valid_word(a, n) || !valid_word(b, n)) return invalid(n);
  int64_t m = pow3(n);
  int64_t p = decode(a, n) % m; if (p < 0) p += m;
  int64_t acc = 0;
  for (unsigned i = 0; i < n; i++) {
    int t = bt_code_value(bt_code_get(b, i, n));
    if (t == 1) acc = (acc + p) % m;
    else if (t == -1) acc = (acc - p + m) % m;
    p = (p * 3) % m;
  }
  return encode(acc, n);
}
static uint64_t cmp(uint64_t a, uint64_t b, unsigned n) {
  a &= word_mask(n); b &= word_mask(n);
  if (!valid_word(a, n) || !valid_word(b, n)) return 2u;
  int64_t x = decode(a, n), y = decode(b, n);
  int64_t r = x < y ? -1 : (x > y ? 1 : 0);
  return (uint64_t)r & reg_mask(n);
}
static uint64_t shl(uint64_t a, uint64_t b, unsigned n) {
  a &= word_mask(n);
  if (!valid_word(a, n)) return invalid(n);
  unsigned k = (unsigned)(b & (n >= 32u ? 63u : 31u));
  if (k >= n) return encode(0, n);
  uint64_t w = encode(0, n);
  for (unsigned i = n; i > k; i--) w = bt_code_put(w, i - 1u, n, bt_code_get(a, i - 1u - k, n));
  return w;
}
static uint64_t shr(uint64_t a, uint64_t b, unsigned n) {
  a &= word_mask(n);
  if (!valid_word(a, n)) return invalid(n);
  unsigned k = (unsigned)(b & (n >= 32u ? 63u : 31u));
  if (k >= n) return encode(0, n);
  uint64_t w = encode(0, n);
  for (unsigned i = 0; i + k < n; i++) w = bt_code_put(w, i, n, bt_code_get(a, i + k, n));
  return w;
}
static uint64_t from_int(uint64_t a, unsigned n) {
  int64_t x = (n >= 32u) ? (int64_t)a : (int64_t)(int32_t)(uint32_t)(a & 0xffffffffu);
  /* reduce() handles INT64_MIN: % never overflows because m > 1. */
  return encode(x, n);
}
static uint64_t to_int(uint64_t a, unsigned n) {
  a &= word_mask(n);
  if (!valid_word(a, n)) return n >= 32u ? (uint64_t)1u << 63 : 0x80000000u;
  return (uint64_t)decode(a, n) & reg_mask(n);
}

/* Public entry points, one per operation and width (uniform signature). */
uint64_t bt_neg32(uint64_t a, uint64_t b) { (void)b; return neg(a, 32u); }
uint64_t bt_neg16(uint64_t a, uint64_t b) { (void)b; return neg(a, 16u); }
uint64_t bt_add32(uint64_t a, uint64_t b) { return add(a, b, 32u); }
uint64_t bt_add16(uint64_t a, uint64_t b) { return add(a, b, 16u); }
uint64_t bt_sub32(uint64_t a, uint64_t b) { return sub(a, b, 32u); }
uint64_t bt_sub16(uint64_t a, uint64_t b) { return sub(a, b, 16u); }
uint64_t bt_mul32(uint64_t a, uint64_t b) { return mul(a, b, 32u); }
uint64_t bt_mul16(uint64_t a, uint64_t b) { return mul(a, b, 16u); }
uint64_t bt_cmp32(uint64_t a, uint64_t b) { return cmp(a, b, 32u); }
uint64_t bt_cmp16(uint64_t a, uint64_t b) { return cmp(a, b, 16u); }
uint64_t bt_shl32(uint64_t a, uint64_t b) { return shl(a, b, 32u); }
uint64_t bt_shl16(uint64_t a, uint64_t b) { return shl(a, b, 16u); }
uint64_t bt_shr32(uint64_t a, uint64_t b) { return shr(a, b, 32u); }
uint64_t bt_shr16(uint64_t a, uint64_t b) { return shr(a, b, 16u); }
uint64_t bt_from_int32(uint64_t a, uint64_t b) { (void)b; return from_int(a, 32u); }
uint64_t bt_from_int16(uint64_t a, uint64_t b) { (void)b; return from_int(a, 16u); }
uint64_t bt_to_int32(uint64_t a, uint64_t b) { (void)b; return to_int(a, 32u); }
uint64_t bt_to_int16(uint64_t a, uint64_t b) { (void)b; return to_int(a, 16u); }

const char *bt_encoding_name(void) { return BT_ENCODING_NAME; }

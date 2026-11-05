/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Reference functions for packed_decimal: sign-magnitude packed BCD. The low nibble is the sign
 * (0xC plus, 0xD minus); the digit nibbles above it hold d digits, least significant first.
 * d = 15 in a 64-bit register, d = 7 in a 32-bit register. Any other sign nibble or a digit nibble
 * above 9 makes the word invalid. Overflow keeps the low d digits of the magnitude and the sign
 * (decimal truncation). Zero is always returned as +0. */
#include "packed_decimal.h"

static uint64_t wmask(unsigned d) { return d >= 15u ? ~(uint64_t)0 : (((uint64_t)1u << (4u * (d + 1u))) - 1u); }
static uint64_t pow10u(unsigned d) { uint64_t m = 1; for (unsigned i = 0; i < d; i++) m *= 10u; return m; }

static int valid(uint64_t w, unsigned d) {
  w &= wmask(d);
  unsigned s = (unsigned)(w & 0xfu);
  if (s != 0xcu && s != 0xdu) return 0;
  for (unsigned i = 1; i <= d; i++) if (((w >> (4u * i)) & 0xfu) > 9u) return 0;
  return 1;
}
/* Value as sign and magnitude; magnitude < 10^15 < 2^50. */
static int64_t value(uint64_t w, unsigned d) {
  int64_t m = 0;
  for (unsigned i = d; i >= 1u; i--) m = m * 10 + (int64_t)((w >> (4u * i)) & 0xfu);
  return ((w & 0xfu) == 0xdu) ? -m : m;
}
static uint64_t encode(int64_t v, unsigned d) {
  int neg = v < 0;
  uint64_t m = neg ? (uint64_t)0u - (uint64_t)v : (uint64_t)v;
  m %= pow10u(d);
  uint64_t w = (neg && m != 0u) ? 0xdu : 0xcu;
  for (unsigned i = 1; i <= d; i++) { w |= (m % 10u) << (4u * i); m /= 10u; }
  return w;
}
static uint64_t inval(unsigned d) { return wmask(d); }
static uint64_t rmask(unsigned d) { return d >= 15u ? ~(uint64_t)0 : 0xffffffffu; }

static uint64_t neg(uint64_t a, unsigned d) { return valid(a, d) ? encode(-value(a, d), d) : inval(d); }
static uint64_t add(uint64_t a, uint64_t b, unsigned d) { return valid(a, d) && valid(b, d) ? encode(value(a, d) + value(b, d), d) : inval(d); }
static uint64_t sub(uint64_t a, uint64_t b, unsigned d) { return valid(a, d) && valid(b, d) ? encode(value(a, d) - value(b, d), d) : inval(d); }
/* Low d digits of the product, by digit-serial multiplication modulo 10^d. */
static uint64_t mul(uint64_t a, uint64_t b, unsigned d) {
  if (!valid(a, d) || !valid(b, d)) return inval(d);
  int64_t x = value(a, d), y = value(b, d);
  uint64_t mx = (uint64_t)(x < 0 ? -x : x), m = pow10u(d), acc = 0;
  for (unsigned i = 1; i <= d; i++) {
    uint64_t dig = (b >> (4u * i)) & 0xfu;
    acc = (acc + (mx * dig) % m) % m;   /* mx < 10^15, dig <= 9: product < 2^54 */
    mx = (mx * 10u) % m;
  }
  int64_t r = (int64_t)acc;
  return encode(((x < 0) != (y < 0)) ? -r : r, d);
}
static uint64_t cmp(uint64_t a, uint64_t b, unsigned d) {
  if (!valid(a, d) || !valid(b, d)) return 2u;
  int64_t x = value(a, d), y = value(b, d);
  return x < y ? rmask(d) : (x > y ? 1u : 0u);
}
static uint64_t from_int(uint64_t a, unsigned d) {
  int64_t x = d >= 15u ? (int64_t)a : (int64_t)(int32_t)(uint32_t)(a & 0xffffffffu);
  if (x == INT64_MIN) { /* |INT64_MIN| mod 10^15, computed without overflow */
    uint64_t m = ((uint64_t)1u << 63) % pow10u(d);
    return encode(-(int64_t)m, d);
  }
  return encode(x, d);
}
static uint64_t to_int(uint64_t a, unsigned d) {
  if (!valid(a, d)) return d >= 15u ? (uint64_t)1u << 63 : 0x80000000u;
  return (uint64_t)value(a, d) & rmask(d);
}

/* Public entry points (uniform signature). */
uint64_t pd_neg15(uint64_t a, uint64_t b) { (void)b; return neg(a, 15u); }
uint64_t pd_neg7(uint64_t a, uint64_t b) { (void)b; return neg(a, 7u); }
uint64_t pd_add15(uint64_t a, uint64_t b) { return add(a, b, 15u); }
uint64_t pd_add7(uint64_t a, uint64_t b) { return add(a, b, 7u); }
uint64_t pd_sub15(uint64_t a, uint64_t b) { return sub(a, b, 15u); }
uint64_t pd_sub7(uint64_t a, uint64_t b) { return sub(a, b, 7u); }
uint64_t pd_mul15(uint64_t a, uint64_t b) { return mul(a, b, 15u); }
uint64_t pd_mul7(uint64_t a, uint64_t b) { return mul(a, b, 7u); }
uint64_t pd_cmp15(uint64_t a, uint64_t b) { return cmp(a, b, 15u); }
uint64_t pd_cmp7(uint64_t a, uint64_t b) { return cmp(a, b, 7u); }
uint64_t pd_from_int15(uint64_t a, uint64_t b) { (void)b; return from_int(a, 15u); }
uint64_t pd_from_int7(uint64_t a, uint64_t b) { (void)b; return from_int(a, 7u); }
uint64_t pd_to_int15(uint64_t a, uint64_t b) { (void)b; return to_int(a, 15u); }
uint64_t pd_to_int7(uint64_t a, uint64_t b) { (void)b; return to_int(a, 7u); }

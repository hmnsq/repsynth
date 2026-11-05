/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Reference functions for balanced_ternary (SPC-03): restricted C11, pure, fixed-width types,
 * no allocation, no input or output. One uniform signature: uint64_t f(uint64_t a, uint64_t b);
 * unary operations ignore b. Width suffix: 32 trits in a 64-bit register, 16 trits in a 32-bit one. */
#ifndef BALANCED_TERNARY_H
#define BALANCED_TERNARY_H
#include <stdint.h>
uint64_t bt_neg32(uint64_t a, uint64_t b);
uint64_t bt_neg16(uint64_t a, uint64_t b);
uint64_t bt_add32(uint64_t a, uint64_t b);
uint64_t bt_add16(uint64_t a, uint64_t b);
uint64_t bt_sub32(uint64_t a, uint64_t b);
uint64_t bt_sub16(uint64_t a, uint64_t b);
uint64_t bt_mul32(uint64_t a, uint64_t b);
uint64_t bt_mul16(uint64_t a, uint64_t b);
uint64_t bt_cmp32(uint64_t a, uint64_t b);
uint64_t bt_cmp16(uint64_t a, uint64_t b);
uint64_t bt_shl32(uint64_t a, uint64_t b);
uint64_t bt_shl16(uint64_t a, uint64_t b);
uint64_t bt_shr32(uint64_t a, uint64_t b);
uint64_t bt_shr16(uint64_t a, uint64_t b);
uint64_t bt_from_int32(uint64_t a, uint64_t b);
uint64_t bt_from_int16(uint64_t a, uint64_t b);
uint64_t bt_to_int32(uint64_t a, uint64_t b);
uint64_t bt_to_int16(uint64_t a, uint64_t b);
const char *bt_encoding_name(void);
#endif

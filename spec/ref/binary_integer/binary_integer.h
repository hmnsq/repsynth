/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BINARY_INTEGER_H
#define BINARY_INTEGER_H
#include <stdint.h>
uint64_t bin_neg64(uint64_t a, uint64_t b);
uint64_t bin_neg32(uint64_t a, uint64_t b);
uint64_t bin_add64(uint64_t a, uint64_t b);
uint64_t bin_add32(uint64_t a, uint64_t b);
uint64_t bin_sub64(uint64_t a, uint64_t b);
uint64_t bin_sub32(uint64_t a, uint64_t b);
uint64_t bin_mul64(uint64_t a, uint64_t b);
uint64_t bin_mul32(uint64_t a, uint64_t b);
uint64_t bin_cmp64(uint64_t a, uint64_t b);
uint64_t bin_cmp32(uint64_t a, uint64_t b);
uint64_t bin_shl64(uint64_t a, uint64_t b);
uint64_t bin_shl32(uint64_t a, uint64_t b);
uint64_t bin_shr64(uint64_t a, uint64_t b);
uint64_t bin_shr32(uint64_t a, uint64_t b);
#endif

/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PACKED_DECIMAL_H
#define PACKED_DECIMAL_H
#include <stdint.h>
uint64_t pd_neg15(uint64_t a, uint64_t b);
uint64_t pd_neg7(uint64_t a, uint64_t b);
uint64_t pd_add15(uint64_t a, uint64_t b);
uint64_t pd_add7(uint64_t a, uint64_t b);
uint64_t pd_sub15(uint64_t a, uint64_t b);
uint64_t pd_sub7(uint64_t a, uint64_t b);
uint64_t pd_mul15(uint64_t a, uint64_t b);
uint64_t pd_mul7(uint64_t a, uint64_t b);
uint64_t pd_cmp15(uint64_t a, uint64_t b);
uint64_t pd_cmp7(uint64_t a, uint64_t b);
uint64_t pd_from_int15(uint64_t a, uint64_t b);
uint64_t pd_from_int7(uint64_t a, uint64_t b);
uint64_t pd_to_int15(uint64_t a, uint64_t b);
uint64_t pd_to_int7(uint64_t a, uint64_t b);
#endif

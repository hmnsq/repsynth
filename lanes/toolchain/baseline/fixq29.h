/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Signed fixed point Q2.29 in int32_t (range [-4, 4), resolution 2^-29).
 * Products use a 64-bit intermediate and round half up before an
 * arithmetic right shift. The Python model in repsynth/lanes/baseline.py
 * reproduces these operations bit for bit.
 */
#ifndef REPSYNTH_FIXQ29_H
#define REPSYNTH_FIXQ29_H
#include <stdint.h>
#define Q 29
#define ONE ((int32_t)1 << Q)
static inline int32_t qmul(int32_t a, int32_t b)
{
    return (int32_t)(((int64_t)a * (int64_t)b + ((int64_t)1 << (Q - 1))) >> Q);
}
#endif

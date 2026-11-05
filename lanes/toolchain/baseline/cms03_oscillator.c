/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * CMS-03 harmonic oscillator, x'' = -w^2 x, x(0) = 1, v(0) = 0, w = 1, as a
 * fixed-point program (Q2.29). Semi-implicit (symplectic) Euler with step
 * h = 2^-8 for 1608 steps (t = 6.28125). Prints the final state and an XOR
 * checksum of every state, in hexadecimal.
 */
#include "fixq29.h"
#include "sysio.h"

#define STEPS 1608
#define HSHIFT 8

int main(void)
{
    const int32_t w2 = ONE;                                    /* w^2 = 1 */
    int32_t x = ONE, v = 0;
    uint32_t check = 0;
    for (int i = 0; i < STEPS; i++) {
        v = v - (qmul(w2, x) >> HSHIFT);
        x = x + (v >> HSHIFT);
        check ^= (uint32_t)x ^ ((uint32_t)v << 7);
        check = (check << 1) | (check >> 31);
    }
    put_str("oscillator x=");
    put_hex((uint32_t)x, 8);
    put_str(" v=");
    put_hex((uint32_t)v, 8);
    put_str(" check=");
    put_hex(check, 8);
    put_str("\n");
    return 0;
}

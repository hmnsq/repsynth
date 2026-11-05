/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * CMS-03 exponential decay, dy/dt = -k y, y(0) = 1, k = 1, as a fixed-point
 * program (Q2.29). Classical fourth-order Runge-Kutta with step h = 2^-8 for
 * 1280 steps (t = 5). Prints the final state and an XOR checksum of every
 * state, in hexadecimal.
 */
#include "fixq29.h"
#include "sysio.h"

#define STEPS 1280
#define HSHIFT 8

int main(void)
{
    const int32_t k = ONE;                                     /* k = 1 */
    const int32_t h6 = (int32_t)(((int64_t)ONE + 3 * 256) / (6 * 256)); /* round(h/6) */
    int32_t y = ONE;
    uint32_t check = 0;
    for (int i = 0; i < STEPS; i++) {
        int32_t k1 = -qmul(k, y);
        int32_t k2 = -qmul(k, y + (k1 >> (HSHIFT + 1)));
        int32_t k3 = -qmul(k, y + (k2 >> (HSHIFT + 1)));
        int32_t k4 = -qmul(k, y + (k3 >> HSHIFT));
        int64_t sum = (int64_t)k1 + 2 * (int64_t)k2 + 2 * (int64_t)k3 + (int64_t)k4;
        y = y + (int32_t)(((int64_t)h6 * sum + ((int64_t)1 << (Q - 1))) >> Q);
        check ^= (uint32_t)y;
        check = (check << 1) | (check >> 31);
    }
    put_str("decay y=");
    put_hex((uint32_t)y, 8);
    put_str(" check=");
    put_hex(check, 8);
    put_str("\n");
    return 0;
}

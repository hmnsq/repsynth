/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Start code for freestanding static Linux user programs (no C library): takes argc and argv from
 * the initial stack, calls main and exits with its result.
 */
#include "repsynth_platform.h"

extern int main(int argc, char **argv);

void __attribute__((used)) _cstart(long *sp)
{
    plat_exit(main((int)sp[0], (char **)(sp + 1)));
}

void __attribute__((naked, section(".text.init"))) _start(void)
{
    __asm__ volatile(
        ".option push\n"
        ".option norelax\n"
        "la gp, __global_pointer$\n"
        ".option pop\n"
        "mv a0, sp\n"
        "andi sp, sp, -16\n"
        "call _cstart\n");
}

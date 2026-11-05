/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Embench board support for QEMU user mode. The triggers are real functions
 * so that a counting plugin can find them by symbol; they do no work.
 */
#include <support.h>

void initialise_board(void)
{
    __asm__ volatile("li a0, 0" : : : "memory");
}

void __attribute__((noinline)) __attribute__((externally_visible)) start_trigger(void)
{
    __asm__ volatile("li a0, 0" : : : "memory");
}

void __attribute__((noinline)) __attribute__((externally_visible)) stop_trigger(void)
{
    __asm__ volatile("li a0, 0" : : : "memory");
}

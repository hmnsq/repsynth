/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Minimal start code so that picolibc programs run as static Linux user
 * programs under qemu-riscv32 and qemu-riscv64 (user mode). The kernel (or
 * QEMU's loader) provides the stack and loads every PT_LOAD segment at its
 * virtual address, so no copy of .data is needed; .bss is zeroed by the
 * loader. Thread-local storage is initialised with picolibc's own helpers.
 */
#include <picotls.h>

void _init_tls(void *tls);
void _set_tls(void *tls);
#include "sysio.h"

extern int main(int argc, char **argv);
extern char __tls_base[];

void _exit(int code)
{
    sys_exit(code);
}

void __attribute__((used)) _cstart(void)
{
    _init_tls(__tls_base);
    _set_tls(__tls_base);
    _exit(main(0, 0));
}

void __attribute__((naked, section(".text.init"))) _start(void)
{
    __asm__ volatile(
        ".option push\n"
        ".option norelax\n"
        "la gp, __global_pointer$\n"
        ".option pop\n"
        "andi sp, sp, -16\n"
        "call _cstart\n");
}

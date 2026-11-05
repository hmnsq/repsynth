/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Platform layer of the generated vector test programs for Linux user mode (QEMU user mode and a
 * booted Linux kernel): raw system calls of the generic RISC-V Linux table, so one static program
 * runs on RV32 and RV64 without a C library that targets Linux. With REPSYNTH_LINUX_INIT defined
 * the program is the /init of an initramfs and powers the machine off when it finishes.
 */
#ifndef REPSYNTH_PLATFORM_H
#define REPSYNTH_PLATFORM_H

static inline long plat_sys3(long n, long x, long y, long z)
{
    register long a0 __asm__("a0") = x;
    register long a1 __asm__("a1") = y;
    register long a2 __asm__("a2") = z;
    register long a7 __asm__("a7") = n;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
    return a0;
}

static inline long plat_sys4(long n, long x, long y, long z, long w)
{
    register long a0 __asm__("a0") = x;
    register long a1 __asm__("a1") = y;
    register long a2 __asm__("a2") = z;
    register long a3 __asm__("a3") = w;
    register long a7 __asm__("a7") = n;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a7) : "memory");
    return a0;
}

static inline int plat_open(const char *path)
{
    return (int)plat_sys4(56, -100 /* AT_FDCWD */, (long)path, 0 /* O_RDONLY */, 0);
}

static inline int plat_read(int fd, void *buf, int n)
{
    return (int)plat_sys3(63, fd, (long)buf, n);
}

static inline void plat_close(int fd)
{
    plat_sys3(57, fd, 0, 0);
}

static inline void plat_write(const char *s, int n)
{
    plat_sys3(64, 1, (long)s, n);
}

static inline void __attribute__((noreturn)) plat_exit(int code)
{
#ifdef REPSYNTH_LINUX_INIT
    /* Running as /init of a booted kernel: report the exit code, then power off (reboot(2)). */
    plat_write(code ? "INIT EXIT 1\n" : "INIT EXIT 0\n", 12);
    plat_sys4(142, 0xfee1dead, 672274793, 0x4321fedc /* LINUX_REBOOT_CMD_POWER_OFF */, 0);
#endif
    plat_sys3(93, code, 0, 0);
    for (;;) {
    }
}
#endif

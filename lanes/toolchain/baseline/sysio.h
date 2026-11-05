/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Linux system calls (write 64, exit 93) for static user programs, and a
 * hexadecimal printer that needs no stdio.
 */
#ifndef REPSYNTH_SYSIO_H
#define REPSYNTH_SYSIO_H
#include <stdint.h>

static inline long sys_write(int fd, const void *buf, unsigned long len)
{
    register long a0 __asm__("a0") = fd;
    register long a1 __asm__("a1") = (long)buf;
    register long a2 __asm__("a2") = (long)len;
    register long a7 __asm__("a7") = 64;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
    return a0;
}

static inline void __attribute__((noreturn)) sys_exit(int code)
{
    register long a0 __asm__("a0") = code;
    register long a7 __asm__("a7") = 93;
    __asm__ volatile("ecall" : : "r"(a0), "r"(a7) : "memory");
    for (;;) {
    }
}

static inline unsigned long str_len(const char *s)
{
    unsigned long n = 0;
    while (s[n])
        n++;
    return n;
}

static inline void put_str(const char *s)
{
    sys_write(1, s, str_len(s));
}

/* Writes v as `digits` lower-case hexadecimal digits. */
static inline void put_hex(uint64_t v, int digits)
{
    char buf[17];
    for (int i = digits - 1; i >= 0; i--) {
        unsigned d = (unsigned)(v & 0xf);
        buf[i] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        v >>= 4;
    }
    sys_write(1, buf, (unsigned long)digits);
}
#endif

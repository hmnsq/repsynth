/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Platform layer of the generated vector test programs for xv6-riscv user programs.
 */
#ifndef REPSYNTH_PLATFORM_H
#define REPSYNTH_PLATFORM_H
#include "kernel/types.h"
#include "kernel/fcntl.h"
#include "user/user.h"

static inline int plat_open(const char *path)
{
    return open(path, O_RDONLY);
}

static inline int plat_read(int fd, void *buf, int n)
{
    return read(fd, buf, n);
}

static inline void plat_close(int fd)
{
    close(fd);
}

static inline void plat_write(const char *s, int n)
{
    write(1, s, n);
}

static inline void __attribute__((noreturn)) plat_exit(int code)
{
    exit(code);
}
#endif

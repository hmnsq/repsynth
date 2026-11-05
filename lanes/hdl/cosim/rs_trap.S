/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Platform stubs of the co-simulation platform; the harness places this image at 0x800, outside the
 * program. rs_boot plays exec: it takes sp and the entry address from the mailbox at 0xf1000000 and
 * jumps to the program. rs_trap (at 0x1000, mtvec) plays QEMU's user-mode system call layer: it hands
 * a0, a1, a2, a7, mcause and mepc to the harness, takes a0 back and returns past the ecall. Every
 * register the trap stub touches is restored. */
    .section .text
    .globl rs_boot
rs_boot:
    lui   t0, 0xf1000
    lw    sp, 32(t0)
    lw    t1, 36(t0)
    li    t0, 0
    jr    t1
    .balign 0x800
    .globl rs_trap
rs_trap:
    csrw  mscratch, t6
    lui   t6, 0xf1000
    sw    t5, 20(t6)
    csrr  t5, mcause
    sw    t5, 24(t6)
    csrr  t5, mepc
    sw    t5, 28(t6)
    sw    a0, 0(t6)
    sw    a1, 4(t6)
    sw    a2, 8(t6)
    sw    a7, 12(t6)          /* the harness acts on this write */
    lw    a0, 16(t6)
    lw    t5, 28(t6)
    addi  t5, t5, 4
    csrw  mepc, t5
    lw    t5, 20(t6)
    csrr  t6, mscratch
    mret

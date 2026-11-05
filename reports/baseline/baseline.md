<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Binary performance baseline (P4.13, D14)

Dynamic instruction counts in QEMU user mode, counted by the pinned tree's own plugin (tests/tcg/plugins/insn.c, inline). These are emulator counts, never hardware speed. Every count was measured twice and both runs agreed.

| Workload | Suite | RV32IMAC | RV64GC | Verified |
|---|---|---:|---:|---|
| aha-mont64 | embench | 4542122 | 1920019 | yes |
| crc32 | embench | 4029057 | 4029403 | yes |
| cubic | embench | 7419868 | 1127319 | yes |
| edn | embench | 3545989 | 3486990 | yes |
| huffbench | embench | 3020727 | 3291371 | yes |
| matmult-int | embench | 3272074 | 3281807 | yes |
| minver | embench | 4939964 | 465223 | yes |
| nbody | embench | 6127726 | 53000 | yes |
| nettle-aes | embench | 4467467 | 5095478 | yes |
| nettle-sha256 | embench | 4210940 | 4281818 | yes |
| nsichneu | embench | 2238745 | 2238745 | yes |
| picojpeg | embench | 4440936 | 4481567 | yes |
| qrduino | embench | 3383993 | 3558285 | yes |
| sglib-combined | embench | 2619847 | 2647545 | yes |
| slre | embench | 2495636 | 2473765 | yes |
| st | embench | 4201516 | 79154 | yes |
| statemate | embench | 1594177 | 1016462 | yes |
| ud | embench | 3350728 | 2314480 | yes |
| wikisort | embench | 3096985 | 1871849 | yes |
| cms03_decay | cms03 | 106626 | 34894 | yes |
| cms03_oscillator | cms03 | 32694 | 24577 | yes |

Tool versions:

- embench-iot: https://github.com/embench/embench-iot tag embench-1.0 commit 0466a18e4f6b47e19598d7c6ba72916d54b68f65
- libinsn.so: tests/tcg/plugins/insn.c of the pinned tree, sha256 5e6a28dcb7e452ae98521e3743af76785f68133bae78b4ebdf5c65ab1b8f34a9
- picolibc-riscv64-unknown-elf: 1.8.6-2
- qemu-riscv32: qemu-riscv32 version 10.2.4 sha256 5d8b42b39601e556c4465c054d9c518973d6322dbadec85820ea8d06eb230036
- qemu-riscv64: qemu-riscv64 version 10.2.4 sha256 88d94d4821d6d29a4dab0694fdae7dec5ec36a1b54c87e6e053247692881c3f4
- qemu-source: hmnsq/qemu tag v10.2.4 commit 3e0bcba1ca7d6607ca49a988d165f052a3a53323 tree e0af1c7de4b0c7979bab82927f61d7c28e6f1964 (fork tag object b4263afc equals upstream qemu/qemu v10.2.4); stock build, configure --target-list=riscv64-linux-user,riscv32-linux-user,riscv64-softmmu,riscv32-softmmu --enable-plugins
- riscv64-unknown-elf-gcc: riscv64-unknown-elf-gcc (13.2.0-11ubuntu1+12) 13.2.0

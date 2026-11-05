<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Tier A benefit and promotion (P4.4)

Dynamic instructions per operation in QEMU user mode (patched v10.2.4, insn plugin). Emulator counts, not hardware speed. The binary column is the binary_integer reference function on the base ISA (the performance baseline, NUM-06); balanced ternary and packed decimal are shown beside it.

Promotion rule (working value): base/extension ratio >= 2.0 on both profiles, every count verified against the vectors and reproduced on rerun.

| Operation | Profile | Binary baseline (ref, base ISA) | Base ISA, reference function | Extension | Ratio |
|---|---|---:|---:|---:|---:|
| balanced_ternary.neg | rv64 | 10.502 | 1233.334 | 6.502 | 189.69 |
| balanced_ternary.neg | rv32 | 14.002 | 2035.627 | 7.002 | 290.72 |
| balanced_ternary.add | rv64 | 10.502 | 1794.244 | 8.502 | 211.04 |
| balanced_ternary.add | rv32 | 14.002 | 2761.154 | 9.002 | 306.73 |
| balanced_ternary.sub | rv64 | 10.502 | 1794.053 | 8.502 | 211.02 |
| balanced_ternary.sub | rv32 | 14.002 | 2762.826 | 9.002 | 306.91 |
| balanced_ternary.mul | rv64 | 10.502 | 2059.157 | 8.502 | 242.2 |
| balanced_ternary.mul | rv32 | 14.002 | 4591.216 | 9.002 | 510.02 |
| balanced_ternary.cmp | rv64 | 11.502 | 1168.003 | 8.502 | 137.38 |
| balanced_ternary.cmp | rv32 | 19.746 | 1317.875 | 9.002 | 146.4 |
| balanced_ternary.shl | rv64 | 10.502 | 975.053 | 8.502 | 114.69 |
| balanced_ternary.shl | rv32 | 14.002 | 1777.246 | 9.002 | 197.43 |
| balanced_ternary.shr | rv64 | 15.818 | 972.343 | 8.502 | 114.37 |
| balanced_ternary.shr | rv32 | 19.344 | 1779.722 | 9.002 | 197.7 |
| balanced_ternary.from_int | rv64 | n/a | 648.652 | 6.502 | 99.76 |
| balanced_ternary.from_int | rv32 | n/a | 1481.118 | 7.002 | 211.53 |
| balanced_ternary.to_int | rv64 | n/a | 595.146 | 6.502 | 91.53 |
| balanced_ternary.to_int | rv32 | n/a | 406.767 | 7.002 | 58.09 |
| packed_decimal.neg | rv64 | 10.502 | 393.378 | 6.502 | 60.5 |
| packed_decimal.neg | rv32 | 14.002 | 778.602 | 7.002 | 111.2 |
| packed_decimal.add | rv64 | 10.502 | 594.333 | 8.502 | 69.91 |
| packed_decimal.add | rv32 | 14.002 | 1137.273 | 9.002 | 126.34 |
| packed_decimal.sub | rv64 | 10.502 | 594.285 | 8.502 | 69.9 |
| packed_decimal.sub | rv32 | 14.002 | 1137.188 | 9.002 | 126.33 |
| packed_decimal.mul | rv64 | 10.502 | 856.783 | 8.502 | 100.77 |
| packed_decimal.mul | rv32 | 14.002 | 2690.899 | 9.002 | 298.92 |
| packed_decimal.cmp | rv64 | 11.502 | 460.832 | 8.502 | 54.2 |
| packed_decimal.cmp | rv32 | 19.746 | 532.279 | 9.002 | 59.13 |
| packed_decimal.from_int | rv64 | n/a | 190.131 | 6.502 | 29.24 |
| packed_decimal.from_int | rv32 | n/a | 534.428 | 7.002 | 76.33 |
| packed_decimal.to_int | rv64 | n/a | 215.914 | 6.502 | 33.21 |
| packed_decimal.to_int | rv32 | n/a | 170.904 | 7.002 | 24.41 |

| Candidate | Promoted |
|---|---|
| balanced_ternary.neg | yes |
| balanced_ternary.add | yes |
| balanced_ternary.sub | yes |
| balanced_ternary.mul | yes |
| balanced_ternary.cmp | yes |
| balanced_ternary.shl | yes |
| balanced_ternary.shr | yes |
| balanced_ternary.from_int | yes |
| balanced_ternary.to_int | yes |
| packed_decimal.neg | yes |
| packed_decimal.add | yes |
| packed_decimal.sub | yes |
| packed_decimal.mul | yes |
| packed_decimal.cmp | yes |
| packed_decimal.from_int | yes |
| packed_decimal.to_int | yes |

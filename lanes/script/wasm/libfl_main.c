/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Build glue for the WebAssembly build of APCISR's acii2csr filter (P6.3). The native build links flex's
 * libfl for main() and yywrap(); wasi-libc has no libfl, so this file gives main() the behaviour read from
 * the host's libfl.a (objdump -d: main calls yylex() until it returns 0, then exit(0); yywrap returns 1).
 * yywrap is not needed: the scanner is generated with flex --noyywrap. flex 2.6.4's --main flag was tried
 * first and emits no main() (recorded in the P6.3 run record), so this glue is used instead. */
#include <stdlib.h>
extern int yylex(void);

int main(void)
{
  while (yylex() != 0)
    ;
  exit(0);
}

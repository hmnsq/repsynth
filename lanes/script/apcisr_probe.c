/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Observation driver for APCISR (P6.4). It calls APCISR's own entry point acii2cisr(aci, cpos)
 * (acii2csr.h line 50; acii2csr.c from line 95) through libapcisr.a and prints what it returns, in
 * hexadecimal so that no console-font code (NUL, newline) can break the reading:
 *
 *   R <urdha hex> <madhya hex> <nimna hex>      the rendered rows for cpos = 1
 *   C <curpos for cpos = 1> ... <curpos for cpos = n>   the cursor column APCISR returns per input byte
 *
 * one pair of lines per input line. It changes nothing in APCISR; acii2csr.lex defines the global
 * retval the library writes into (acii2csr.lex line 43), so this driver defines it too. */
#include <stdio.h>
#include <string.h>
#include "acii2csr.h"

cisr retval;

static void hexrow(const char *s)
{
  const unsigned char *p = (const unsigned char *) s;
  if (!*p) { printf(" -"); return; }
  printf(" ");
  for (; *p; p++) printf("%02x", *p);
}

int main(void)
{
  static char line[1100];
  while (fgets(line, sizeof line, stdin)) {
    size_t n = strlen(line), k;
    cisr r;
    if (n && line[n - 1] == '\n') line[--n] = 0;
    if (n == 0 || n >= 1000) { printf("R - - -\nC\n"); continue; }
    r = acii2cisr((unsigned char *) line, 1);
    printf("R");
    hexrow(r.urdha);
    hexrow(r.madhya);
    hexrow(r.nimna);
    printf("\nC");
    for (k = 1; k <= n; k++) {
      r = acii2cisr((unsigned char *) line, (int) k);
      printf(" %d", r.curpos);
    }
    printf("\n");
  }
  return 0;
}

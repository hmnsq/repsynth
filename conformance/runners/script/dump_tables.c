/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Dumps APCISR's tables as the C compiler sees them, so that a generated apcisr.h and cisr2asc.h can be
 * compared with APCISR's own without parsing C by hand (P6.3 gate). Compiled once against APCISR's
 * headers and once against the generated headers; the two dumps must be byte-identical.
 * Every array element is printed, including elements the initialiser leaves to zero. */
#include <stdio.h>
#include <string.h>
#include "apcisr.h"
#include "cisr2asc.h"

static void hex(const char *s)
{
  const unsigned char *p = (const unsigned char *) s;
  if (!p) { printf("(null)"); return; }
  if (!*p) printf("-");
  for (; *p; p++) printf("%02x", *p);
}

int main(void)
{
  size_t i, j, n;
  printf("model _urdha=%d _madhya=%d _nimna=%d _matrik=%d _lipik=%d _purak=%d\n",
         _urdha, _madhya, _nimna, _matrik, _lipik, _purak);
  printf("cisr sizeof=%zu urdha=%zu madhya=%zu nimna=%zu\n", sizeof(cisr),
         sizeof(((cisr *) 0)->urdha), sizeof(((cisr *) 0)->madhya), sizeof(((cisr *) 0)->nimna));
  n = sizeof(apcisr_chrt) / sizeof(apcisr_chrt[0]);
  printf("APCISR_LEN=%d entries=%zu\n", APCISR_LEN, n);
  for (i = 0; i < n; i++) {
    printf("entry %zu rmn=", i);
    hex(apcisr_chrt[i].rmn);
    printf(" acii=");
    hex(apcisr_chrt[i].acii);
    printf(" purna=%d grid=", apcisr_chrt[i].purna);
    for (j = 0; j < 9; j++) printf("%d%s", apcisr_chrt[i].grid[j], j < 8 ? "," : "\n");
  }
#define DUMP(t) do { size_t k, m = sizeof(t) / sizeof(t[0]); printf(#t " size=%zu\n", m); \
    for (k = 0; k < m; k++) printf(#t " %zu %d %d\n", k, t[k][0], t[k][1]); } while (0)
  DUMP(cisr_urdha);
  DUMP(cisr_nimna);
  DUMP(cisr_madhya);
  return 0;
}

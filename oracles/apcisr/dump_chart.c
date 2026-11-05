/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Prints APCISR's grid chart (apcisr_chrt in apcisr.h, read as data, unmodified) as JSON lines:
 * index, Romenagri key, ACII bytes in hex, purna, the nine grid values in row order
 * (urdha, madhya, nimna) x (matrik, lipik, purak). Built against the pinned header by the oracle runner. */
#include <stdio.h>
#include <string.h>
#include "apcisr.h"
int main (void)
{
  int i, k;
  for (i = 0; i < APCISR_LEN; i++)
    {
      printf ("{\"index\": %d, \"rmn\": \"", i);
      for (k = 0; apcisr_chrt[i].rmn[k]; k++)
        printf (apcisr_chrt[i].rmn[k] == '"' || apcisr_chrt[i].rmn[k] == '\\' ? "\\%c" : "%c", apcisr_chrt[i].rmn[k]);
      printf ("\", \"acii\": \"");
      for (k = 0; apcisr_chrt[i].acii[k]; k++)
        printf ("%02x", (unsigned char) apcisr_chrt[i].acii[k]);
      printf ("\", \"purna\": %d, \"grid\": [", apcisr_chrt[i].purna);
      for (k = 0; k < 9; k++)
        printf ("%d%s", apcisr_chrt[i].grid[k], k < 8 ? ", " : "");
      printf ("]}\n");
    }
  return 0;
}

/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Driver for the author's traced build of APCISR (hindawiai/hindawi2026.10 docs/trace/apcisr/src: the original
 * acii2csr.c with two APCISR_TRACE lines that record state and change nothing else). For each input line (hex
 * ACII bytes) it runs acii2cisr() and prints, as one JSON line, every trace record: the cursors matrik, lipik,
 * purak, the chart entry and offset, and the working map columns 0..purak (urdha, madhya, nimna). */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "acii2csr.h"
#include "trace_apcisr.h"
cisr retval;
TR tr[TR_MAX]; int tr_n;
int main (void)
{
  char line[4096];
  static unsigned char in[2048];
  while (fgets (line, sizeof line, stdin))
    {
      int n = 0, t, k;
      line[strcspn (line, "\r\n")] = 0;
      for (k = 0; line[k] && line[k + 1]; k += 2)
        {
          char h[3] = { line[k], line[k + 1], 0 };
          in[n++] = (unsigned char) strtol (h, NULL, 16);
        }
      in[n] = 0;
      tr_n = 0;
      acii2cisr (in, 0);
      printf ("{\"input\": \"%s\", \"trace\": [", line);
      for (t = 0; t < tr_n; t++)
        {
          TR *r = &tr[t];
          int w = r->purak + 1 < TR_W ? r->purak + 1 : TR_W;
          printf ("%s{\"matrik\": %d, \"lipik\": %d, \"purak\": %d, \"purna\": %d, \"prev_hal\": %d, \"entry\": %d, "
                  "\"flag\": %d, \"offset\": %d, \"wm\": [", t ? ", " : "", r->matrik, r->lipik, r->purak, r->purna,
                  r->prev_hal, r->entry, r->flag, r->offset);
          for (k = 0; k < w; k++)
            printf ("%s[%d, %d, %d]", k ? ", " : "", r->u[k], r->m[k], r->n[k]);
          printf ("]}");
        }
      printf ("]}\n");
    }
  return 0;
}

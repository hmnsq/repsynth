/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Native conformance runner: reads one vector file, calls the named reference function from the
 * shared library built from the specification, and prints the count of disagreements.
 * Usage: native_runner <lib.so> <symbol> <file.vec> */
#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint64_t (*fn_t)(uint64_t, uint64_t);

int main(int argc, char **argv) {
  if (argc != 4) { fprintf(stderr, "usage: %s lib symbol file\n", argv[0]); return 2; }
  void *h = dlopen(argv[1], RTLD_NOW);
  if (!h) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 2; }
  fn_t f = (fn_t)(uintptr_t)dlsym(h, argv[2]);
  if (!f) { fprintf(stderr, "dlsym %s: %s\n", argv[2], dlerror()); return 2; }
  FILE *fp = fopen(argv[3], "r");
  if (!fp) { perror(argv[3]); return 2; }
  char line[512]; unsigned long n = 0, bad = 0; int unary = -1;
  while (fgets(line, sizeof line, fp)) {
    if (line[0] == '#') { if (strstr(line, "# fields:")) unary = strstr(line, " b ") == NULL; continue; }
    uint64_t a = 0, b = 0, r = 0;
    int k = unary ? sscanf(line, "%" SCNx64 " %" SCNx64, &a, &r) : sscanf(line, "%" SCNx64 " %" SCNx64 " %" SCNx64, &a, &b, &r);
    if (k != (unary ? 2 : 3)) { fprintf(stderr, "malformed line: %s", line); return 2; }
    uint64_t got = f(a, b); n++;
    if (got != r) { if (bad < 5) printf("MISMATCH a=%" PRIx64 " b=%" PRIx64 " expected=%" PRIx64 " got=%" PRIx64 "\n", a, b, r, got); bad++; }
  }
  fclose(fp);
  printf("native %s cases=%lu disagreements=%lu\n", argv[2], n, bad);
  return bad ? 1 : 0;
}

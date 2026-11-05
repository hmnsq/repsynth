<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Draft reading record of the 9-grid model (P1.6, for P6.1)

© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.

State: draft, read from source only. It awaits the author's confirmation at P6.1 (SCR-01); nothing here is assumed
beyond what the cited lines say. Source: hindawiai/chintamani at commit cf614ff2dd8da9e23f2f98c49686640e2ec2e181, folder APCISR/. The author's paper
on the 9-grid theory was not available to this reading, and the file apcisr.txt that acii2csr.c line 88 names as
the algorithm's description is not in the repository (searched: the whole chintamani tree at that commit).

## What the source defines

| Element | Reading | Cited |
|---|---|---|
| The grid | Nine cells: three rows (urdha, madhya, nimna) by three columns (matrik, lipik, purak). Row offsets 0, 3, 6; column offsets 0, 1, 2; cell = row offset + column offset | APCISR/apcisr.h lines 50 to 56 |
| A rendition (cisr) | Three byte rows urdha, madhya, nimna of 1024 columns each, and a cursor curpos | APCISR/apcisr.h lines 58 to 64 |
| A chart entry (grid9) | Romenagri key, ACII byte sequence, purna, and grid[9] | APCISR/apcisr.h lines 66 to 72 |
| The chart | 82 entries for Devanagari (APCISR_LEN) | APCISR/apcisr.h lines 41 and 74 onward |
| Lookup | The first entry whose ACII sequence is a prefix of the remaining input; chart order therefore matters (conjuncts precede their parts) | APCISR/acii2csr.c lines 173 to 186 |
| Input with no entry | Rendered in its own collapsed column with madhya 192, then the next column marked 128 | APCISR/acii2csr.c lines 224 to 292 (192 at line 246) |
| purna | A non-zero purna starts a new varna: matrik moves to the old purak, lipik and purak follow, and matrik and purak are flagged 128 as non-lipik columns | APCISR/acii2csr.c lines 324 to 340 |
| Delayed hal | After a hal, a following varna joins: the hal mark (64) is taken back from nimna and lipik advances, giving the half form | APCISR/acii2csr.c lines 341 to 384 |
| ra + hal | Shown on top of the next varna (bit 128 of urdha at lipik or purak by purna parity) | APCISR/acii2csr.c lines 308 to 323 and 504 to 516 |
| Dynamic placement rules | Lower ref, short u, visarga with o, chandrabindu, bindu, long u, ha + hal, nascent hal, short i after conjuncts: each places its bits itself (grid_job = 0) instead of the chart grid | APCISR/acii2csr.c rules at lines 409, 423, 439, 459, 474, 489, 518, 532, 558 |
| Default placement | Otherwise the entry's nine values are ORed into the working map at the matrik, lipik and purak columns | APCISR/acii2csr.c lines 582 to 613 |
| Column elimination | Visibly empty columns (madhya 160 or 128, urdha and nimna 0) are dropped before output | APCISR/acii2csr.c line 621 onward |
| Font substitution | Cell values become glyph codes through the tables cisr_urdha, cisr_nimna and cisr_madhya, for the fonts devnagri.f08 and devnagri.f16 | APCISR/cisr2asc.h lines 50, 273 and 406 |

## What execution confirmed

Every chart entry was run alone (signs after KA, ACII b3) through the author's traced build of acii2cisr()
(hindawiai/hindawi2026.10 docs/trace/apcisr/src, shown identical to the pinned APCISR apart from its two
trace lines). 79 of 82 entries put their grid bits exactly at the matrik, lipik and purak columns. The three
others (^u, ^oo and the hal sign ^) are placed by the dynamic rules above, into nimna-lipik instead of
nimna-purak; the spec records their observed cells. On APCISR's own sample test.aci, 136 of 160 token steps
show the chart bits at the cursors; 20 are rule-governed or follow a hal and were not checked by this rule; 4
are context rules (^i after a conjunct, the bindu after it, r before a hal), listed in reports/readings/apcisr.json.

## Questions for the author (P6.1)

1. Is the grid the 3 × 3 of rows urdha, madhya, nimna and columns matrik, lipik, purak, as apcisr.h lines 50 to 56 give it, or does the theory define more than the code uses?
2. Where is apcisr.txt (acii2csr.c line 88), and which paper should P6.1 read beside the code?
3. Are the dynamic rules part of the model, or Devanagari-specific adjustments that another script's instance replaces?

<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Issue text for hmnsq/paras

Command: `paras report /home/user/build/repsynth/.cache/p84/src --local --langs <76 comma-separated languages from `burp languages`> --work <dir>`

Exit code: 0

Output (summary lines):

```
   Hindawi b53530f, with paras's BURP and 48 dictionaries
[1mparas: 1 packages × 76 languages · 4 cores · publish: no[0m

[1m[1 of 1] layer 99-target · src · file:///home/user/build/repsynth/.cache/p84/src · scope - · report[0m
   → skipped: less than 2 GB free

Summary: /home/user/build/repsynth/.cache/p84/pw/SUMMARY.md · what is missing: /home/user/build/repsynth/.cache/p84/pw/reports/<package>/GAPS.md
```

Expected: 76 languages ingested and reversed. Observed: no summary line. paras 2026.10.2.

<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Issue text for hmnsq/burp: Tagalog round trip is not exact for Python keywords

BURP 2026.10.1 (burp-ilm). Commands, run on the harness's tracked sources:

    burp ingest src --langs tagalog --out tg/out     # exit 0
    burp reverse tg/out/tagalog --out tg/rev         # exit 0
    diff src/tests/prove_bounded.py tg/rev/tests/prove_bounded.py   # exit 1

```diff
34c34
<     return r
---
>     ca r
37c37
< if __name__ == "__main__":
---
> ca __name__ == "__main__":
39c39
<     for n in range(1, 7):
---
>     for n ca range(1, 7):
43c43
<     sys.exit(0 if ok else 1)
---
>     sys.exit(0 return ok if 1)
```

Observed: the Python keywords return, if and in come back as the same token 'ca', so the reverse is not byte for byte. Expected: distinct Tagalog forms for each keyword, or a collision report at ingest. The other 75 languages convert back exactly (reports/paras_roundtrip.md).

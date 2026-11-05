<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Oracle run: romenagri

© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.

Repository project-ilm/romenagri2026.10 at commit e9d762804feb0159c6739f242378d58286dbd3f0 (tree 0405b06bbeb0486fd16e0b86853525ce0bff75f3), exported with git archive and run in .cache/oracles/romenagri/work/. Driver: README.md 'Checking it'; tests/run_all.sh.

Clones unchanged after the run: project-ilm/romenagri2026.10: True.

| Step | Command | Exit code | Shows |
|---|---|---|---|
| make_all | `make -C Romenagri all` | 0 | the patched Romenagri built with its own Makefile |
| run_all | `RMN_BUILD="$ORACLE_SCRATCH/rmn_build" bash tests/run_all.sh` | 0 | the package's own quick test suite |

## make_all

`make -C Romenagri all`, exit code 0. Full log .cache/oracles/romenagri/logs/make_all.log (sha256 0766883c10ccf5e68af907e6d8c0fbfa2e88abe231054d92e9b55b3db2c52f91, 30 lines).

Standard output, last lines:

```
make: Entering directory '/home/user/build/repsynth/.cache/oracles/romenagri/work/Romenagri'
gcc -Wall -Wno-unused -o rmn2acii.o -c rmn2acii.c
gcc -Wall -Wno-unused -o acii2rmn.o -c acii2rmn.c
gcc -Wall -Wno-unused -o acii2hin.o -c acii2hin.c
gcc -Wall -Wno-unused -o stack.o -c stack.c
ar -cr librmnagri.a rmn2acii.o acii2rmn.o acii2hin.o stack.o 
flex -8 -olexyy.c acii2cf.lex
gcc -Wall -Wno-unused -o acii2cf lexyy.c -lfl -lrmnagri -L ./
flex -8 -olexyy.c acii2pcf.lex
gcc -Wall -Wno-unused -o acii2pcf lexyy.c -lfl -lrmnagri -L ./
flex -8 -olexyy.c acii2hin.lex
gcc -Wall -Wno-unused -o acii2hin lexyy.c -lfl -lrmnagri -L ./
flex -8 -olexyy.c acii2rmn.lex
gcc -Wall -Wno-unused -o acii2rmn lexyy.c -lfl -lrmnagri -L ./
flex -8 -olexyy.c fixuninum.lex
gcc -Wall -Wno-unused -o fixuninum lexyy.c -lfl -lrmnagri -L ./
flex -8 -olexyy.c rmn2acii.lex
gcc -Wall -Wno-unused -o rmn2acii lexyy.c -lfl -lrmnagri -L ./
gcc -Wall -Wno-unused -o main.o -c main.c
gcc -o testme main.o -lrmnagri -L ./
gcc -Wall -Wno-unused -o acii2uni acii2uni.c
gcc -Wall -Wno-unused -o uni2acii uni2acii.c
make: Leaving directory '/home/user/build/repsynth/.cache/oracles/romenagri/work/Romenagri'
```

Standard error, last lines:

```
(empty)
```

## run_all

`RMN_BUILD="$ORACLE_SCRATCH/rmn_build" bash tests/run_all.sh`, exit code 0. Full log .cache/oracles/romenagri/logs/run_all.log (sha256 1033cec9373a03c53e22fd304b0b3c3aad24e386857fdea6def167e58426c006, 241 lines).

Standard output, last lines:

```
     11.6  old: U+2190 comes back as a control character                                          ok
     11.6  old: U+1F600 gives the bytes 3D 00                                                     ok
     11.6  new: U+00A0 comes back as ' '                                                          ok
     11.6  new: U+00AD comes back as 'ऐ'                                                          ok
     11.6  new: U+00B7 comes back as 'ङ'                                                          ok
     11.6  new: U+00D7 comes back as 'स'                                                          ok
     11.6  new: U+00E9 comes back as '़'                                                          ok
     11.6  new: U+20B9 comes back as 'छ'                                                          ok
     11.6  new: U+2022 comes back as '"'                                                          ok
     11.6  new: U+2122 comes back as '"'                                                          ok
     11.6  new: U+2026 comes back as '&'                                                          ok
     11.6  new: U+2020 comes back as ' '                                                          ok
     11.6  new: U+FFFD comes back as '}'                                                          ok
     11.6  new: U+0934 comes back as '4'                                                          ok
     11.6  new: U+1CD0 comes back as 'ऱ'                                                          ok
     11.6  new: U+2002-U+2019, U+201C, U+201D (including ZWNJ U+200C and ZWJ U+200D) all come back as control characters ok
     11.6  new: ZWNJ comes back as U+000C (form feed) and ZWJ as U+000D (carriage return)         ok
     11.6  new: U+2190 comes back as a control character                                          ok
     11.6  new: U+1F600 gives the bytes 3D 00                                                     ok
     11.6  the double danda U+0965 came back as `e` before the patch and comes back as itself now ok
   RESULT: PASS
== doc_tables_in_sync
   generated blocks: 12, out of date or missing: 0
== table_lint_old (informational: the unpatched tables)
   ERROR  T7 X+C ebb8 does not survive acii2rmn + rmn2acii:  -> '_3cha' -> e833b8
   T7: 37 consonants x 53 letters, both orders: 74 failures
   14 error(s)
== end-to-end: skipped (hincc not on PATH)

================ SUMMARY
  table_lint_new         PASS
  unicode                PASS
  saral                  PASS
  parser_vs_model        PASS
  roundtrip              PASS
  corpus                 PASS
  recipes                PASS
  limitations            PASS
  doc_tables_in_sync     PASS
  logs: /home/user/build/repsynth/.cache/oracles/romenagri/scratch/rmn_build/logs
```

Standard error, last lines:

```
(empty)
```

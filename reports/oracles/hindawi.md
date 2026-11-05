<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Oracle run: hindawi

© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.

Repository hindawiai/hindawi2026.10 at commit b53530f624a0dd3065f9370ff439223a43d49994 (tree 0a1dd02d62d07b96eb87b294f21409d1d7730e64), exported with git archive and run in .cache/oracles/hindawi/work/. Driver: README.md 'Start here'; VERIFY.md steps 1 to 3; scripts/build.sh; scripts/fetch.sh.

Clones unchanged after the run: hindawiai/hindawi2026.10: True.

| Step | Command | Exit code | Shows |
|---|---|---|---|
| install | `bash install.sh --prefix "$ORACLE_PREFIX"` | 0 | the toolchain built from the pinned Chintamani the original way, and Urdu and Telugu quick_sort.c compiled and run |
| doctor | `python3 bin/hindawi doctor` | 0 | every required tool and the Chintamani toolchain |
| test | `python3 bin/hindawi test` | 1 | the repository's own regression suite (VERIFY.md step 3) |
| chintamani_others | `for d in fasm qb2c; do echo "== $d"; make -C .build/chintamani/Hindawi/others/$d all || exit $?; done` | 0 | fasm and qb2c built with their own Makefiles, as Chintamani's install script does (lines 108 to 118); Hindawi's build.sh does not build them |
| shaili_round_trip | `bash "$ORACLE_RUNNERS/hindawi/shaili_round_trip.sh"` | 0 | each built Chintamani shaili transducer, forward (h2X) and reverse (X2h), on the shaili's own Hindi samples |

## install

`bash install.sh --prefix "$ORACLE_PREFIX"`, exit code 0. Full log .cache/oracles/hindawi/logs/install.log (sha256 1009be25c273a7018db8b72ee4780499ec144e9bc19d1bb43a75c5aaf1dcc5c9, 67 lines).

Standard output, last lines:

```
  ok       flex
  ok       make
  ok       iconv
  ok       git
  ok       g++
  ok       bison
  ok       docker
  absent   arduino-cli (optional)
== the Hindawi toolchain, from the pinned source (the first run fetches it from GitHub)
fetch: chintamani 3ad8778, seabios rel-1.16.3
build: guru      ok
build: shraeni   ok
build: yantra    ok
build: kritrima  ok
build: praatha   ok
build: soochee   ok
build: wyaaka    ok
build: shabda    ok
== the commands
  /home/user/build/repsynth/.cache/oracles/hindawi/prefix/bin/hindawi -> /home/user/build/repsynth/.cache/oracles/hindawi/work/bin/hindawi
  /home/user/build/repsynth/.cache/oracles/hindawi/prefix/bin/hindawicc -> /home/user/build/repsynth/.cache/oracles/hindawi/work/lang/hindawi/hindawicc
  /home/user/build/repsynth/.cache/oracles/hindawi/prefix/share/man/man1/hindawi.1
== proof: a GATE program compiled from Urdu and from Telugu, run, and compared with English
hindawi 2026.10.4
  ok    python3      
  ok    gcc          
  ok    g++          
  ok    flex         
  ok    make         
  ok    iconv        
  ok    git          
  ok    bison        
  ok    docker       
  absent  arduino-cli  (optional)
  ok    Chintamani toolchain in .build/chintamani 
doctor: ready
  urdu: quick_sort.c compiles from urdu and prints: 1 3 8 14 29 40 55 72 
  telugu: quick_sort.c compiles from telugu and prints: 1 3 8 14 29 40 55 72 
install.sh: add /home/user/build/repsynth/.cache/oracles/hindawi/prefix/bin to PATH, for example: echo 'export PATH="/home/user/build/repsynth/.cache/oracles/hindawi/prefix/bin:$PATH"' >> ~/.bashrc
install.sh: installed. Start with: hindawi --help, man hindawi, and docs/hindawi/MANUAL.md
```

Standard error, last lines:

```
Note: switching to 'a6ed6b701f0a57db0569ab98b0661c12a6ec3ff8'.

You are in 'detached HEAD' state. You can look around, make experimental
changes and commit them, and you can discard any commits you make in this
state without impacting any branches by switching back to a branch.

If you want to create a new branch to retain commits you create, you may
do so (now or later) by using -c with the switch command. Example:

  git switch -c <new-branch-name>

Or undo this operation with:

  git switch -

Turn off this advice by setting config variable advice.detachedHead to false
```

## doctor

`python3 bin/hindawi doctor`, exit code 0. Full log .cache/oracles/hindawi/logs/doctor.log (sha256 8bcf383faa13d66456ee6e5802292188bad73769b7bf1ef162618105b4b60ad2, 20 lines).

Standard output, last lines:

```
hindawi 2026.10.4
  ok    python3      
  ok    gcc          
  ok    g++          
  ok    flex         
  ok    make         
  ok    iconv        
  ok    git          
  ok    bison        
  ok    docker       
  absent  arduino-cli  (optional)
  ok    Chintamani toolchain in .build/chintamani 
doctor: ready
```

Standard error, last lines:

```
(empty)
```

## test

`python3 bin/hindawi test`, exit code 1. Full log .cache/oracles/hindawi/logs/test.log (sha256 c88db4824239f42ee1f29bc9dc6480b4943efa296908f970f37efce799fc0f24, 763 lines).

Standard output, last lines:

```
  PASS  T-47 has a work package carrying the originator's credit
  PASS  T-52 has a work package carrying the originator's credit
  PASS  T-54 has a work package carrying the originator's credit
  PASS  T-62 has a work package carrying the originator's credit
  FAIL  T-63 has a work package carrying the originator's credit
  FAIL  T-64 has a work package carrying the originator's credit
  FAIL  T-68 has a work package carrying the originator's credit
  FAIL  T-69 has a work package carrying the originator's credit
== the compilation path shows every stage, and compiles what it shows
  PASS  Urdu shows source, script filter, Romenagri and C
  PASS  to_c is the last stage shown
  PASS  a whole tree lowered at once gives, file for file, what each file gives alone
162 passed, 5 failed

== fundamental regression
Hindawi fundamental regression
  PASS  F1  the Chintamani copy is Chintamani
  PASS  F2  Wave 0: 8 of 8 samples reach their host source
  PASS  F3  guru: HindiC.uhin to host and back
  PASS  F3  shraeni: HindiC++.uhin to host and back
  NOTE  F3  yantra: HindiASM.uhin: the original Hindawi h2y and y2h are not round-trip stable on its own assembly sample
  PASS  F3  kritrima: HindiJAVA.uhin to host and back
  PASS  F3  praatha: HindiBASIC.uhin to host and back
  PASS  F3  wyaaka: HindiYACC.uhin to host and back
  PASS  F3  shabda: HindiLEX.uhin to host and back
  PASS  F4  ingestion (BURP) puts the project's keywords in Hindi, with one dictionary for both files
  PASS  F4  hindawicc compiles both native files with gcc's flags passed through
  PASS  F4  the project comes back to its original C through the same dictionary
  PASS  F5  योगफल becomes the ELF symbol yoagaphala and comes back through Romenagri
  12 passed, 0 failed

== notebooks: structure, and demos built through the original pipeline
notebooks: 288 passed, 0 failed

== summary
   PASS  originals byte for byte
   PASS  the build's own suite
   FAIL  standards, review data, trademarks, register, stages
   PASS  fundamental regression
   PASS  notebooks: structure, and demos built through the original pipeline
```

Standard error, last lines:

```
test_no_json_in_multilingual_payload (test_hindawi_multilingual.HindawiMultilingualTests.test_no_json_in_multilingual_payload) ... ok
test_registry_is_csv_and_profiles_are_distinct (test_hindawi_multilingual.HindawiMultilingualTests.test_registry_is_csv_and_profiles_are_distinct) ... ok
test_sanskrit_keyword_inventory_is_csv_and_source_is_preserved (test_hindawi_multilingual.HindawiMultilingualTests.test_sanskrit_keyword_inventory_is_csv_and_source_is_preserved) ... ok
test_duplicate_surface_requires_explicit_policy (test_nirgundi_baseline.NirgundiBaselineTests.test_duplicate_surface_requires_explicit_policy) ... ok
test_empty_form_rejected (test_nirgundi_baseline.NirgundiBaselineTests.test_empty_form_rejected) ... ok
test_longest_first_and_stable_ids (test_nirgundi_baseline.NirgundiBaselineTests.test_longest_first_and_stable_ids) ... ok
test_longest_first_prevents_short_form_stealing_longer_form (test_nirgundi_baseline.NirgundiBaselineTests.test_longest_first_prevents_short_form_stealing_longer_form) ... ok
test_occurrences_only_report_matches_that_actually_fire (test_nirgundi_baseline.NirgundiBaselineTests.test_occurrences_only_report_matches_that_actually_fire) ... ok
test_residual_is_preserved (test_nirgundi_baseline.NirgundiBaselineTests.test_residual_is_preserved) ... ok
test_shorter_form_does_not_match_inside_longer_token (test_nirgundi_baseline.NirgundiBaselineTests.test_shorter_form_does_not_match_inside_longer_token) ... ok
test_evam_does_not_consume_devam_and_vichheda_can (test_nirgundi_cycle.CycleTests.test_evam_does_not_consume_devam_and_vichheda_can) ... ok
test_next_rules_consume_only_listed_stems (test_nirgundi_cycle.CycleTests.test_next_rules_consume_only_listed_stems) ... ok
test_stops_when_no_rule_consumes (test_nirgundi_cycle.CycleTests.test_stops_when_no_rule_consumes) ... ok
test_residual_agrees_with_statistics (test_nirgundi_experiment.ExperimentArtifactTests.test_residual_agrees_with_statistics) ... skipped 'the external Cologne MW lexicon and prior RV experiment artifacts are not bundled; see docs/nirgundi/source-gaps.md'
test_sutra_conversion_covers_every_record (test_nirgundi_experiment.ExperimentArtifactTests.test_sutra_conversion_covers_every_record) ... ok
test_extract_deduplicates_and_sorts_longest_first (test_observed_form_bootstrap.ObservedFormBootstrapTests.test_extract_deduplicates_and_sorts_longest_first) ... ok
test_full_corpus_run_is_repeatable_and_keeps_all_records (test_observed_form_bootstrap.ObservedFormBootstrapTests.test_full_corpus_run_is_repeatable_and_keeps_all_records) ... ok

----------------------------------------------------------------------
Ran 26 tests in 3.503s

OK (skipped=1)
+ /usr/local/bin/python3 /home/user/build/repsynth/.cache/oracles/hindawi/work/tests/check_standards_register.py
+ /usr/local/bin/python3 /home/user/build/repsynth/.cache/oracles/hindawi/work/tests/fundamental.py
+ /usr/local/bin/python3 /home/user/build/repsynth/.cache/oracles/hindawi/work/tests/check_notebooks.py
```

## chintamani_others

`for d in fasm qb2c; do echo "== $d"; make -C .build/chintamani/Hindawi/others/$d all || exit $?; done`, exit code 0. Full log .cache/oracles/hindawi/logs/chintamani_others.log (sha256 d15e2faf7aa51af1e9cc3a6c5a53fa19e5f02a83678edc69051f503f906ec14e, 16 lines).

Standard output, last lines:

```
== fasm
make: Entering directory '/home/user/build/repsynth/.cache/oracles/hindawi/work/.build/chintamani/Hindawi/others/fasm'
make: Nothing to be done for 'all'.
make: Leaving directory '/home/user/build/repsynth/.cache/oracles/hindawi/work/.build/chintamani/Hindawi/others/fasm'
== qb2c
make: Entering directory '/home/user/build/repsynth/.cache/oracles/hindawi/work/.build/chintamani/Hindawi/others/qb2c'
gcc -std=gnu89 -c -ansi -w -O2 x11int.c rotated.c gifencode.c gifdecode.c pickpalette.c
ar -cr libqbX11.a x11int.o rotated.o gifencode.o gifdecode.o pickpalette.o
make: Leaving directory '/home/user/build/repsynth/.cache/oracles/hindawi/work/.build/chintamani/Hindawi/others/qb2c'
```

Standard error, last lines:

```
(empty)
```

## shaili_round_trip

`bash "$ORACLE_RUNNERS/hindawi/shaili_round_trip.sh"`, exit code 0. Full log .cache/oracles/hindawi/logs/shaili_round_trip.log (sha256 6a17a04219e37e30a8e69edece07b48b0f1a6fcfade614444aff59441e12c340, 120 lines).

Standard output, last lines:

```
< %%
< "अ"a+"अ"	{म_लिखो("ओ");}
## HindiYACC: 59 lines differ
1,59c1,59
< <शैली व्याक>
< %अणु
< #समावेश <प्रकार.स>
< #समावेश <मानकपन.स>
< #घोषणा व्याक_ढेर_प्रकार द्विगुन
--- compile output (hincc)
## HindiASM
संकलन के परिणाम
============
flat assembler  version 1.67.7  (16384 kilobytes memory)
3 passes, 244 bytes.
## HindiBASIC
संकलन के परिणाम
============
qb2c: translating  tempfil0123.tmphin.bas  -->  tempfil0123.tmphin.c
Translation done in 0.02 sec.
## HindiBASICgraphics
संकलन के परिणाम
============
qb2c: translating  tempfil0123.tmphin.bas  -->  tempfil0123.tmphin.c
Translation done in 0.05 sec.
## HindiC++
संकलन के परिणाम
============
## HindiC
संकलन के परिणाम
============
## HindiJAVA
संकलन के परिणाम
============
## HindiLEX
संकलन के परिणाम
============
## HindiYACC
संकलन के परिणाम
============
```

Standard error, last lines:

```
(empty)
```

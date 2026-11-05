<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Oracle run: apcisr

© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.

Repository hindawiai/chintamani at commit cf614ff2dd8da9e23f2f98c49686640e2ec2e181 (tree c3f5dfa69d513c3f9afa0351a573731fcf41c3af), exported with git archive and run in .cache/oracles/apcisr/work/. Driver: APCISR/Makefile (targets all, libapcisr, filters); APCISR/test.aci.

Clones unchanged after the run: hindawiai/chintamani: True.

| Step | Command | Exit code | Shows |
|---|---|---|---|
| make_all | `make -C APCISR all` | 0 | libapcisr.a and the acii2csr filter built with APCISR's own Makefile |
| render_test_aci | `cd APCISR && ./acii2csr < test.aci` | 0 | the filter run on APCISR's own sample, test.aci |

## make_all

`make -C APCISR all`, exit code 0. Full log .cache/oracles/apcisr/logs/make_all.log (sha256 cb6ea5c7ae86c307286900ccf6cd94ae4e324e2bf316670e077412e1eba4ab34, 83 lines).

Standard output, last lines:

```
make: Entering directory '/home/user/build/repsynth/.cache/oracles/apcisr/work/APCISR'
gcc -Wall -Wno-unused -o acii2csr.o -c acii2csr.c
ar -cru libapcisr.a acii2csr.o
flex -8 -olexyy.c acii2csr.lex
gcc -Wall -Wno-unused -o acii2csr lexyy.c -lfl -lapcisr -L ./
make: Leaving directory '/home/user/build/repsynth/.cache/oracles/apcisr/work/APCISR'
```

Standard error, last lines:

```
      |                       ^~~
      |                       |
      |                       unsigned char *
/usr/include/string.h:350:34: note: expected ‘const char *’ but argument is of type ‘unsigned char *’
  350 | extern char *strstr (const char *__haystack, const char *__needle)
      |                      ~~~~~~~~~~~~^~~~~~~~~~
acii2csr.c:234:37: warning: pointer targets in passing argument 1 of ‘strlen’ differ in signedness [-Wpointer-sign]
  234 |           if (lnfnd == 0 && strlen (aci) < l_aci)
      |                                     ^~~
      |                                     |
      |                                     unsigned char *
/usr/include/string.h:407:35: note: expected ‘const char *’ but argument is of type ‘unsigned char *’
  407 | extern size_t strlen (const char *__s)
      |                       ~~~~~~~~~~~~^~~
ar: `u' modifier ignored since `D' is the default (see `U')
acii2csr.lex: In function ‘yylex’:
acii2csr.lex:47:17: warning: pointer targets in passing argument 1 of ‘acii2cisr’ differ in signedness [-Wpointer-sign]
   47 | .*      { dvn=acii2cisr(yytext,1); cisr_printf_con(dvn); }
      |                 ^~~~~~
      |                 |
      |                 char *
In file included from acii2csr.lex:41:
acii2csr.h:50:41: note: expected ‘unsigned char *’ but argument is of type ‘char *’
   50 |   extern cisr acii2cisr (unsigned char *aci_in, int cpos);
      |                          ~~~~~~~~~~~~~~~^~~~~~
```

## render_test_aci

`cd APCISR && ./acii2csr < test.aci`, exit code 0. Full log .cache/oracles/apcisr/logs/render_test_aci.log (sha256 62f58796488a45bb52a6cc24af4ffda19111e2dcbc3dae26798a10fc372d13a6, 52 lines).

Standard output, last lines:

```
                          ┌┐  ┌┐            
è∩ ï  î∩ ì∩ Ä∩            Θà∞ àφ     ╧∞ ╓∩
 
                                            
                                          
Å  É  æ  Æ  ô∩             à∞ à∞     ≈ °
 
                           ╘  ╙           
                                      ┌┐      ┌┐  
ö∩ ò∩ û  ù∩ ÿ∩             à∞        è≡àà∞ Ö∩ààφ
 
      ·                    ╫                      
                           ⁿ  ²               ┌Σ  ┌Σ ┌┐  
Ö∩ Ü∞ ¢∩ £∩ ¥∩             à∞ à∞     î∩¢≡ÿ∩-ä-ΘÑû ΘÑûí≡
 
                                     ∙╘         ·   ·    
                            ⁿ  ²      ┌┐    ┌        
₧∩ ƒ  á∩ í∩ ó∩             àφ àφ     Ö≡╟∩ ¢∩Ü∞ ª∞¥∩
 
                                                     
                            .     ■  
ú∩ ñ∩ Ñ  æ  Æ              à∞ àΩ à∞
 
         ∙  ∙                        
          
╟∩ ╡∩ ╩∩
 
          
       
╗∩ ╦∩
 
       
   
▓
 
   
   
 
 
   
```

Standard error, last lines:

```
(empty)
```

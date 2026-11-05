<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->
# paras and BURP round trip of hmnsq/repsynth (P8.4)

Gate: `burp check <tracked sources> --langs <76 languages>`, exit 1: 75 of 76 languages convert back byte for byte.

Secondary: `paras report <same folder> --local --langs <76 languages>`, exit 0: no summary line.

Finding for paras's next round: given the full language list, paras report processed fewer languages than requested. Issue text: reports/paras_issue.md.

Untranslated names, comments and keywords are gaps for the next round, not failures.

```
arabic                       ARABIC        310/310    yes  yes     yes     yes  yes   
aramaic                      ARABIC        310/310    yes  yes     yes     no   yes   
assamese                     BENGALI       310/310    yes  yes     yes     yes  yes   
awadhi                       DEVANAGARI    310/310    yes  yes     yes     yes  yes   
balinese                     BALINESE      310/310    yes  yes     yes     no   no    
balochi                      ARABIC        310/310    yes  yes     yes     yes  yes   
batak                        BATAK         310/310    yes  yes     yes     no   no    
bengali                      BENGALI       310/310    yes  yes     yes     yes  yes   
bhojpuri                     DEVANAGARI    310/310    yes  yes     yes     yes  yes   
bodo                         DEVANAGARI    310/310    yes  yes     yes     yes  yes   
buginese                     BUGINESE      310/310    yes  yes     yes     no   no    
bulgarian                    CYRILLIC      310/310    yes  yes     yes     no   no    
burmese                      MYANMAR       310/310    yes  yes     yes     no   no    
chhattisgarhi                DEVANAGARI    310/310    yes  yes     yes     yes  yes   
chinese                      CJK           310/310    yes  yes     yes     no   no    
dari                         ARABIC        310/310    yes  yes     yes     yes  yes   
dogri                        DEVANAGARI    310/310    yes  yes     yes     yes  yes   
dzongkha                     TIBETAN       310/310    yes  yes     yes     no   no    
gujarati                     GUJARATI      310/310    yes  yes     yes     yes  yes   
hausa_ajami                  ARABIC        310/310    yes  yes     yes     yes  yes   
hebrew                       ARABIC        310/310    yes  yes     yes     no   yes   
hindi                        DEVANAGARI    310/310    yes  yes     yes     yes  yes   
japanese                     HIRAGANA      310/310    yes  yes     yes     no   no    
javanese                     JAVANESE      310/310    yes  yes     yes     no   no    
kannada                      KANNADA       310/310    yes  yes     yes     yes  yes   
kashmiri                     ARABIC        310/310    yes  yes     yes     yes  yes   
kashmiri_dev                 DEVANAGARI    310/310    yes  yes     yes     yes  yes   
khmer                        KHMER         310/310    yes  yes     yes     no   no    
konkani                      DEVANAGARI    310/310    yes  yes     yes     yes  yes   
korean                       HANGUL        310/310    yes  yes     yes     no   no    
kurdish_sorani               ARABIC        310/310    yes  yes     yes     yes  yes   
lao                          LAO           310/310    yes  yes     yes     no   no    
lepcha                       LEPCHA        310/310    yes  yes     yes     no   no    
limbu                        LIMBU         310/310    yes  yes     yes     no   no    
magahi                       DEVANAGARI    310/310    yes  yes     yes     yes  yes   
maithili                     DEVANAGARI    310/310    yes  yes     yes     yes  yes   
malay_jawi                   ARABIC        310/310    yes  yes     yes     yes  yes   
malayalam                    MALAYALAM     310/310    yes  yes     yes     yes  yes   
mandaic                      ARABIC        310/310    yes  yes     yes     yes  yes   
manipuri_beng                BENGALI       310/310    yes  yes     yes     yes  yes   
marathi                      DEVANAGARI    310/310    yes  yes     yes     yes  yes   
marwari                      DEVANAGARI    310/310    yes  yes     yes     yes  yes   
nabataean                    ARABIC        310/310    yes  yes     yes     yes  yes   
nepali                       DEVANAGARI    310/310    yes  yes     yes     yes  yes   
newari                       DEVANAGARI    310/310    yes  yes     yes     yes  yes   
odia                         ORIYA         310/310    yes  yes     yes     yes  yes   
pali                         DEVANAGARI    310/310    yes  yes     yes     yes  yes   
pashto                       ARABIC        310/310    yes  yes     yes     yes  yes   
persian                      ARABIC        310/310    yes  yes     yes     yes  yes   
phoenician                   ARABIC        310/310    yes  yes     yes     no   yes   
prakrit                      DEVANAGARI    310/310    yes  yes     yes     yes  yes   
punjabi                      GURMUKHI      310/310    yes  yes     yes     yes  yes   
punjabi_shahmukhi            ARABIC        310/310    yes  yes     yes     yes  yes   
rajasthani                   DEVANAGARI    310/310    yes  yes     yes     yes  yes   
russian                      CYRILLIC      310/310    yes  yes     yes     no   no    
samaritan                    ARABIC        310/310    yes  yes     yes     yes  yes   
sanskrit                     DEVANAGARI    310/310    yes  yes     yes     yes  yes   
santali                      OL            310/310    yes  yes     yes     no   no    
saraiki                      ARABIC        310/310    yes  yes     yes     yes  yes   
serbian                      CYRILLIC      310/310    yes  yes     yes     no   no    
shan                         MYANMAR       310/310    yes  yes     yes     no   no    
sindhi                       ARABIC        310/310    yes  yes     yes     yes  yes   
sindhi_dev                   DEVANAGARI    310/310    yes  yes     yes     yes  yes   
sinhala                      SINHALA       310/310    yes  yes     yes     no   no    
sundanese                    SUNDANESE     310/310    yes  yes     yes     no   no    
syriac                       ARABIC        310/310    yes  yes     yes     no   yes   
tagalog                      DEVANAGARI    309/310    yes  yes     yes     yes  yes   
tamil                        TAMIL         310/310    yes  yes     yes     yes  yes   
telugu                       TELUGU        310/310    yes  yes     yes     yes  yes   
thai                         THAI          310/310    yes  yes     yes     no   no    
tibetan                      TIBETAN       310/310    yes  yes     yes     no   no    
tulu                         KANNADA       310/310    yes  yes     yes     yes  yes   
ukrainian                    CYRILLIC      310/310    yes  yes     yes     no   no    
urdu                         ARABIC        310/310    yes  yes     yes     yes  yes   
uyghur                       ARABIC        310/310    yes  yes     yes     yes  yes   
vietnamese                   LATIN         310/310    yes  yes     yes     no   no    
```

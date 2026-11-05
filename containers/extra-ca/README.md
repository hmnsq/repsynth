<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->
Optional build-machine hook. Empty on the author's machine. When REPSYNTH_EXTRA_CA names a certificate
bundle (a build machine behind an intercepting proxy), `repsynth doctor --build` copies it here as
extra.crt (git-ignored) and the containers trust it during their build.

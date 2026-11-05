<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Contract overlay

A thin overlay on the author's master contract. It adds constraints and relaxes none.

- Legacy implementations and the author's repositories are read-only oracles; derived builds live in this tree (GOV-03, GOV-04).
- Done means executed: a packet is done only when its acceptance command ran and passed; RESUME.md is generated, never edited.
- Nothing pretends: unimplemented functions raise; every gate is shown refusing a planted defect before it is trusted.
- Nothing is installed on the host: tools run in kept containers (ops/run.sh); --native is for build machines only.
- The implementer never pushes, publishes, mints or creates repositories (GOV-12).

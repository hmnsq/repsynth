# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recording accessor (DEP-01, P3.1): generators read specifications only through it; a read outside
the generator's declaration fails, naming the path."""
from __future__ import annotations

from .spec import consume


class UndeclaredRead(Exception):
    pass


def _covered(ptr: str, declared) -> bool:
    return any(ptr == d or ptr.startswith(d.rstrip("/") + "/") for d in declared)


class Accessor:
    def __init__(self, spec: dict, declared, generator: str):
        self.spec = spec
        self.declared = list(declared)
        self.generator = generator
        self.reads: list[str] = []

    def __call__(self, pointer: str):
        if not _covered(pointer, self.declared):
            raise UndeclaredRead(f"{self.generator} read {self.spec['identity']['id']}#{pointer}, "
                                 f"which it does not declare (declared: {self.declared})")
        self.reads.append(pointer)
        return consume(self.spec, pointer)

# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Specification store (component H1): loading, validation, canonical form, paths and slice hashes.

Requirements: SPC-01, SPC-02, SPC-03, SPC-04, SPC-05; packets P1.1 and P1.2.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .records import ROOT

SCHEMA_PATH = ROOT / "spec" / "schema" / "representation.schema.json"


class SpecError(Exception):
    """A refusal, carrying the JSON Pointer path of the offending field."""

    def __init__(self, path: str, message: str):
        super().__init__(f"{path or '/'}: {message}")
        self.path = path or "/"
        self.message = message


# ---------------------------------------------------------------- loading


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise SpecError("", f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_spec(path) -> dict:
    """Load a YAML (or JSON) specification. Duplicate keys are refused."""
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.load(text, Loader=_UniqueKeyLoader)
    if not isinstance(data, dict):
        raise SpecError("", "a specification is a mapping")
    return data


# ---------------------------------------------------------------- canonical form, paths, hashes


def canonical(value) -> bytes:
    """Canonical serialisation: JSON, keys sorted, no insignificant whitespace, UTF-8.

    Key order and YAML whitespace never change it; any change of value does (P1.2).
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spec_sha256(spec: dict) -> str:
    """Hash of the whole specification's canonical form (notice key excluded)."""
    return sha256_hex(canonical({k: v for k, v in spec.items() if k != "_notice"}))


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def resolve(spec, pointer: str):
    """Resolve an RFC 6901 JSON Pointer."""
    if pointer in ("", "/"):
        return spec
    if not pointer.startswith("/"):
        raise SpecError(pointer, "a JSON Pointer starts with /")
    node = spec
    for raw in pointer[1:].split("/"):
        tok = _unescape(raw)
        if isinstance(node, list):
            if not tok.isdigit() or int(tok) >= len(node):
                raise SpecError(pointer, f"no index {tok}")
            node = node[int(tok)]
        elif isinstance(node, dict):
            if tok not in node:
                raise SpecError(pointer, f"no key {tok!r}")
            node = node[tok]
        else:
            raise SpecError(pointer, "path goes through a scalar")
    return node


def slice_hash(spec: dict, pointer: str) -> str:
    """Hash of the canonical form of the value at a path (SPC-04)."""
    return sha256_hex(canonical(resolve(spec, pointer)))


def stable_path(spec: dict, pointer: str) -> str:
    return f"{spec['identity']['id']}#{pointer}"


def walk(value, pointer=""):
    """Yield (pointer, value) for every node."""
    yield pointer, value
    if isinstance(value, dict):
        for k in value:
            yield from walk(value[k], f"{pointer}/{_escape(str(k))}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, f"{pointer}/{i}")


# ---------------------------------------------------------------- validation (P1.1)


def _schema_errors(spec: dict):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    out = []
    for e in sorted(v.iter_errors(spec), key=lambda e: list(e.absolute_path)):
        ptr = "".join(f"/{_escape(str(p))}" for p in e.absolute_path)
        msg = e.message
        if e.validator == "oneOf" and e.context:
            best = min(e.context, key=lambda c: len(list(c.absolute_path)))
            msg = f"{e.message[:120]} (closest: {best.message[:160]})"
        out.append(SpecError(ptr, msg))
    return out


def _not_established_errors(spec: dict):
    """A bare 'not_established' string (no reason) or a guessed marker is refused (SPC-05)."""
    out = []
    for ptr, val in walk(spec):
        if isinstance(val, str) and val.strip().lower() in ("not_established", "unknown", "tbd", "todo", "guess", "guessed"):
            out.append(SpecError(ptr, f"value {val!r} is not allowed: write {{not_established: <reason>}}"))
    return out


_DEF_RE = r"^\s*(?:static\s+inline\s+)?uint64_t\s+{name}\s*\("


def reference_symbols(spec: dict, spec_dir: Path):
    """Return list of (pointer, symbol, found_in or None)."""
    sources = []
    for i, rel in enumerate(spec.get("semantics", {}).get("reference_sources", []) or []):
        p = (ROOT / rel) if not Path(rel).is_absolute() else Path(rel)
        sources.append((f"/semantics/reference_sources/{i}", p))
    widths = [w["digits"] for w in spec.get("domain", {}).get("widths", []) if isinstance(w, dict)]
    out = []
    for i, op in enumerate(spec.get("operations", []) or []):
        pat = (op.get("reference") or {}).get("symbol_pattern")
        if not pat:
            continue
        for w in widths:
            sym = pat.replace("{width}", str(w))
            found = None
            for _, p in sources:
                if p.is_file() and re.search(_DEF_RE.format(name=re.escape(sym)), p.read_text(encoding="utf-8"), re.M):
                    found = p
                    break
            out.append((f"/operations/{i}/reference/symbol_pattern", sym, found))
    return out, sources


def check(spec: dict, spec_path: Path | None = None) -> list[SpecError]:
    """All refusals for a specification; an empty list means it validates."""
    errors = _schema_errors(spec)
    errors += _not_established_errors(spec)
    if not errors:
        refs, sources = reference_symbols(spec, spec_path.parent if spec_path else ROOT)
        for ptr, p in sources:
            if not p.is_file():
                errors.append(SpecError(ptr, f"reference source {p} does not exist"))
        for ptr, sym, found in refs:
            if found is None:
                errors.append(SpecError(ptr, f"reference function {sym} is not defined in any reference source"))
        names = [op["name"] for op in spec["operations"]]
        dup = {n for n in names if names.count(n) > 1}
        for n in sorted(dup):
            errors.append(SpecError("/operations", f"operation {n} is defined twice"))
    return errors


def consume(spec: dict, pointer: str):
    """What a generator calls to read a value: refuses not_established and names it (SPC-05)."""
    val = resolve(spec, pointer)
    for p, v in walk(val, pointer):
        if isinstance(v, dict) and "not_established" in v:
            raise SpecError(p, f"not established ({v['not_established']}); a generator may not consume it")
    return val

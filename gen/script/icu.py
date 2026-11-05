# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ICU 74.2 through its C API (libicuuc.so.74), with signatures read from the pinned libicu-dev headers
(unicode/uset.h: uset_openPattern, uset_getItemCount, uset_getItem, uset_close; unicode/ubrk.h: ubrk_open
with UBRK_CHARACTER = 0, ubrk_first, ubrk_next returning UBRK_DONE = -1, ubrk_close).

Two uses: parsing CLDR exemplar sets (UnicodeSet patterns) and Unicode extended grapheme clusters
(UAX #29 as ICU implements it for its Unicode version)."""
from __future__ import annotations

import ctypes

from .refs import ICU_SUFFIX, icu_libs

UBRK_CHARACTER = 0
UBRK_DONE = -1


def _f(name, restype, argtypes):
    fn = getattr(icu_libs(), name + ICU_SUFFIX)
    fn.restype, fn.argtypes = restype, argtypes
    return fn


def _u16(s: str):
    b = s.encode("utf-16-le")
    n = len(b) // 2
    return (ctypes.c_uint16 * max(n, 1)).from_buffer_copy(b or b"\0\0"), n


def unicode_set(pattern: str) -> list[str]:
    """Items of a UnicodeSet pattern, each a single code point or a multi-character string, in ICU's order."""
    open_ = _f("uset_openPattern", ctypes.c_void_p, [ctypes.POINTER(ctypes.c_uint16), ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)])
    count = _f("uset_getItemCount", ctypes.c_int32, [ctypes.c_void_p])
    item = _f("uset_getItem", ctypes.c_int32, [ctypes.c_void_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32),
                                               ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint16),
                                               ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)])
    close = _f("uset_close", None, [ctypes.c_void_p])
    buf, n = _u16(pattern)
    ec = ctypes.c_int32(0)
    s = open_(buf, n, ctypes.byref(ec))
    if ec.value > 0 or not s:
        raise ValueError(f"ICU refused UnicodeSet pattern (UErrorCode {ec.value}): {pattern[:80]}")
    out = []
    try:
        for i in range(count(s)):
            a, b = ctypes.c_int32(), ctypes.c_int32()
            sb = (ctypes.c_uint16 * 64)()
            ec = ctypes.c_int32(0)
            ln = item(s, i, ctypes.byref(a), ctypes.byref(b), sb, 64, ctypes.byref(ec))
            if ec.value > 0:
                raise ValueError(f"uset_getItem error {ec.value}")
            if ln == 0:
                out += [chr(c) for c in range(a.value, b.value + 1)]
            else:
                out.append(bytes(sb)[: 2 * ln].decode("utf-16-le"))
    finally:
        close(s)
    return out


def grapheme_boundaries(text: str) -> list[int]:
    """Extended grapheme cluster boundaries as code point indices, 0 and len(text) included."""
    open_ = _f("ubrk_open", ctypes.c_void_p, [ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint16),
                                              ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)])
    first = _f("ubrk_first", ctypes.c_int32, [ctypes.c_void_p])
    nxt = _f("ubrk_next", ctypes.c_int32, [ctypes.c_void_p])
    close = _f("ubrk_close", None, [ctypes.c_void_p])
    buf, n = _u16(text)
    ec = ctypes.c_int32(0)
    bi = open_(UBRK_CHARACTER, b"", buf, n, ctypes.byref(ec))
    if ec.value > 0 or not bi:
        raise RuntimeError(f"ubrk_open failed (UErrorCode {ec.value})")
    # map UTF-16 offsets to code point indices
    u16_to_cp, k = {}, 0
    for i, ch in enumerate(text):
        u16_to_cp[k] = i
        k += 2 if ord(ch) > 0xFFFF else 1
    u16_to_cp[k] = len(text)
    out = []
    try:
        b = first(bi)
        while b != UBRK_DONE:
            out.append(u16_to_cp[b])
            b = nxt(bi)
    finally:
        close(bi)
    return out

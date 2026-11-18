# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Digests the test ledger records: sha256 over bytes, over a Python
object's source, and over a canonical text encoding of parametrize values.

The canonical encoding is what makes two runs of a test with the same
values compare equal across processes: it never uses `hash()` or `repr()`
of arbitrary objects (both can vary per process). A value the encoder
cannot read exactly (an object of a user class, an oversized container)
is encoded by its type alone, so distinct values of such a type encode
alike.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any

MAX_DEPTH = 4
MAX_ITEMS = 64


def sha256_hex(data: bytes) -> str:
    """Intent:
        The sha256 of `data` as 64 lowercase hex digits.
    """
    return hashlib.sha256(data).hexdigest()


def text_digest(text: str) -> str:
    """Intent:
        The sha256 of `text` encoded as UTF-8.
    """
    return sha256_hex(text.encode("utf-8"))


def json_digest(value: Any) -> str:
    """Intent:
        The sha256 of `value` as compact JSON with sorted keys, the form
        every composite digest in the ledger is taken over.
    """
    return text_digest(json.dumps(value, sort_keys=True,
                                  separators=(",", ":")))


def source_digest(obj: Any) -> str | None:
    """Intent:
        The sha256 of `obj`'s source text as `inspect.getsource` returns
        it (whole lines, decorators included), or None when the source
        cannot be read.
    """
    try:
        return text_digest(inspect.getsource(obj))
    except (OSError, TypeError):
        return None


def _type_name(value: Any) -> str:
    t = type(value)
    return f"{t.__module__}.{t.__qualname__}"


def _prefixed(value: Any, exact: type, body: str) -> str:
    """Intent:
        `body`, prefixed by the value's type name when the value is an
        instance of a subclass of `exact` (an IntEnum, a numpy float),
        so a subclass value never collides with the plain one.
    """
    if type(value) is exact:
        return body
    return _type_name(value) + ":" + body


def type_only(value: Any) -> str:
    """Intent:
        The canonical form of a value that cannot be read: its type name.
    """
    return "o" + _type_name(value)


def encode(value: Any, depth: int = 0) -> str:
    """Intent:
        A canonical text form of `value`: equal for equal values of the
        readable kinds (None, bool, int, float, complex, str, bytes, and
        tuples, lists, dicts, sets of them), stable across processes.
        Every NaN encodes alike. Anything else, or a container deeper
        than `MAX_DEPTH` or longer than `MAX_ITEMS`, encodes as its type
        name only.
    """
    if value is None:
        return "N"
    if isinstance(value, bool):
        return _prefixed(value, bool, "T" if value else "F")
    if isinstance(value, int):
        return _prefixed(value, int, "i" + hex(value))
    if isinstance(value, float):
        return _prefixed(value, float,
                         "f" + ("nan" if value != value else value.hex()))
    if isinstance(value, complex):
        return _prefixed(value, complex, "c" + encode(value.real)
                         + encode(value.imag))
    if isinstance(value, str):
        return _prefixed(value, str, "s" + json.dumps(value))
    if isinstance(value, bytes):
        return _prefixed(value, bytes, "y" + value.hex())
    if isinstance(value, (tuple, list, dict, set, frozenset)):
        if depth >= MAX_DEPTH or len(value) > MAX_ITEMS:
            return "o" + _type_name(value)
        if isinstance(value, dict):
            pairs = sorted(encode(k, depth + 1) + ":" + encode(v, depth + 1)
                           for k, v in value.items())
            return _type_name(value) + "{" + ",".join(pairs) + "}"
        parts = [encode(v, depth + 1) for v in value]
        if isinstance(value, (set, frozenset)):
            parts.sort()
        return _type_name(value) + "(" + ",".join(parts) + ")"
    return "o" + _type_name(value)

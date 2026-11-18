# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Which functions a change touches, from a unified diff and the source
on each side.

A function is keyed as mathema keys it, `module.name` for a module-level
function (an `async def` and a lambda bound to a module-level name
included) and `module.Class.name` for a method of a module-level class.
Its span runs from its first decorator to its last line. A function is
changed when its span on the head side overlaps a line the diff adds or
changes, or holds the line just before a deletion. It is `new` when the
base defines no function of that key, which is so for a function whose
module was renamed or moved, and `edited` otherwise. A function the
change deleted has no head span, so it is not changed.

Every function here is pure: the diff text and the sources come in as
arguments.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

__all__ = ["FileChange", "changed_functions", "function_spans", "module_of", "parse_diff"]


@dataclass(frozen=True)
class FileChange:
    """One file's part of a diff: its path on the head side, its path on
    the base side (the same unless renamed, None for a new file), and the
    head-side line ranges the diff touches, each `(first, last)`."""

    path: str
    base_path: str | None
    lines: tuple[tuple[int, int], ...]


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _strip(name: str) -> str | None:
    """Intent:
        The path a `---` or `+++` header names, without its `a/` or `b/`
        prefix, or None for `/dev/null`.
    """
    name = name.split("\t", 1)[0]
    if name == "/dev/null":
        return None
    return name[2:] if name[:2] in ("a/", "b/") else name


def parse_diff(text: str) -> list[FileChange]:
    """The files a unified diff (`git diff --unified=0`) changes on the
    head side, each with the line ranges it touches there. A hunk that
    adds or changes lines touches them; a hunk that only deletes touches
    the head-side line just before the deletion (line 1 at the top of the
    file). A file deleted on the head side is left out."""
    out: list[FileChange] = []
    base_path: str | None = None
    path: str | None = None
    lines: list[tuple[int, int]] = []

    def flush():
        if path is not None:
            out.append(FileChange(path, base_path, tuple(lines)))

    for line in text.splitlines():
        if line.startswith("diff --git "):
            flush()
            base_path = path = None
            lines = []
        elif line.startswith("--- "):
            base_path = _strip(line[4:])
        elif line.startswith("+++ "):
            path = _strip(line[4:])
        else:
            match = _HUNK.match(line)
            if match and path is not None:
                start = int(match.group(1))
                count = 1 if match.group(2) is None else int(match.group(2))
                if count == 0:
                    lines.append((max(start, 1), max(start, 1)))
                else:
                    lines.append((start, start + count - 1))
    flush()
    return out


def module_of(path: str) -> str | None:
    """The dotted module of a project Python file, a leading `src/`
    dropped, or None for a file that is not one: not `.py`, a test file,
    or a path that does not spell a module."""
    p = PurePosixPath(path.replace("\\", "/"))
    if p.suffix != ".py" or p.is_absolute() or ".." in p.parts:
        return None
    parts = list(p.parts)
    if parts[0] == "src":
        parts = parts[1:]
    parts[-1] = p.stem
    if (any(part in ("test", "tests") for part in parts[:-1]) or p.stem == "conftest"
            or p.stem.startswith("test_") or p.stem.endswith("_test")):
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and all(part.isidentifier() for part in parts):
        return ".".join(parts)
    return None


def _span(node: ast.stmt) -> tuple[int, int]:
    """Intent:
        A definition's lines, from its first decorator to its last line.
    """
    first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return first, node.end_lineno or node.lineno


def function_spans(source: str, module: str) -> dict[str, tuple[int, int]]:
    """`{key: (first, last)}` for every function `source` defines at the
    levels mathema keys: module-level functions, lambdas bound to a
    module-level name, and the methods of module-level classes. Nested
    functions and nested classes are part of the definition holding
    them. Source that does not parse defines nothing."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    spans: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans[f"{module}.{node.name}"] = _span(node)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    spans[f"{module}.{node.name}.{item.name}"] = _span(item)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    spans[f"{module}.{target.id}"] = _span(node)
    return spans


def _overlaps(span: tuple[int, int], lines: tuple[tuple[int, int], ...]) -> bool:
    """Intent:
        Whether `span` shares a line with any range in `lines`.
    """
    first, last = span
    return any(a <= last and first <= b for a, b in lines)


def changed_functions(changes: list[FileChange], head_sources: Mapping[str, str],
                      base_sources: Mapping[str, str]) -> dict[str, str]:
    """`{key: "edited" | "new"}` for every function the diff touches on
    the head side. `head_sources` maps a head-side path to its text and
    `base_sources` a base-side path to its text; a path missing from
    either reads as defining nothing there."""
    out: dict[str, str] = {}
    for change in changes:
        module = module_of(change.path)
        if module is None or not change.lines:
            continue
        head = function_spans(head_sources.get(change.path, ""), module)
        base_module = module_of(change.base_path) if change.base_path else None
        base = (function_spans(base_sources.get(change.base_path or "", ""), base_module)
                if base_module else {})
        for key, span in head.items():
            if _overlaps(span, change.lines):
                out[key] = "edited" if key in base else "new"
    return dict(sorted(out.items()))

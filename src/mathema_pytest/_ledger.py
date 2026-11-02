# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Rows of the test ledger and the file they are written to.

A row is one test in one environment. Its `identity` is the sha256 over
what the test is made of: its own source, the source of every fixture it
uses (transitively, conftest fixtures included) and its parametrize
values. The `fixtures` and `files` lists carry each of those sources'
paths and digests, so a reader can tell which one changed without
running pytest. The full schema is in `docs/test-ledger.md`.
"""
from __future__ import annotations

import inspect
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ._digest import encode, json_digest, sha256_hex, source_digest

SCHEMA = 1
FRAMEWORK = "pytest"


def outcome(reports: Iterable[Any]) -> str:
    """Intent:
        One test's outcome from its setup, call and teardown reports:
        `passed`, `failed`, `skipped`, `error` (setup or teardown
        failed), `xfailed` or `xpassed`.
    """
    result = "passed"
    for report in reports:
        xfail = hasattr(report, "wasxfail")
        if report.when == "setup":
            if report.failed:
                return "error"
            if report.skipped:
                result = "xfailed" if xfail else "skipped"
        elif report.when == "call":
            if report.failed:
                result = "failed"
            elif report.skipped:
                result = "xfailed" if xfail else "skipped"
            elif xfail:
                result = "xpassed"
        elif report.when == "teardown" and report.failed:
            if result != "failed":
                result = "error"
    return result


def relative(path: str | os.PathLike | None, root: Path) -> str | None:
    """Intent:
        `path` relative to `root` in POSIX form, or None when it is
        missing or lies outside `root`.
    """
    if path is None:
        return None
    try:
        return Path(os.path.realpath(path)).relative_to(
            os.path.realpath(root)).as_posix()
    except ValueError:
        return None


class Digests:
    """Intent:
        Per-session memo of file and source digests, so a file or a
        fixture shared by many tests is read once.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._files: dict[str, str | None] = {}
        self._sources: dict[int, tuple[Any, str | None, str | None]] = {}

    def file(self, rel: str) -> str | None:
        if rel not in self._files:
            try:
                self._files[rel] = sha256_hex((self.root / rel).read_bytes())
            except OSError:
                self._files[rel] = None
        return self._files[rel]

    def source(self, func: Any) -> tuple[str | None, str | None]:
        """Intent:
            `(path, digest)` of a function's source, both None when the
            function is defined outside the project root.
        """
        hit = self._sources.get(id(func))
        if hit is not None and hit[0] is func:
            return hit[1], hit[2]
        target = inspect.unwrap(func)
        try:
            src = inspect.getsourcefile(target)
        except TypeError:
            src = None
        rel = relative(src, self.root)
        digest = source_digest(target) if rel is not None else None
        self._sources[id(func)] = (func, rel, digest)
        return rel, digest


def _fixtures(item: Any, params: Mapping[str, Any],
              digests: Digests) -> list[dict]:
    """Intent:
        Every fixture definition `item` uses, transitively, as
        `{name, path, digest}` sorted by name and path. A name with
        several definitions (a conftest override that requests its
        parent) lists each. A direct parametrize argument is not a
        fixture: its value is in the parametrize values.
    """
    info = getattr(item, "_fixtureinfo", None)
    defs_by_name = getattr(info, "name2fixturedefs", {}) or {}
    found = set()
    for name in getattr(item, "fixturenames", ()):
        for fixturedef in defs_by_name.get(name, ()):
            func = getattr(fixturedef, "func", None)
            if func is None:
                continue
            path, digest = digests.source(func)
            if path is None and name in params:
                continue
            found.add((name, path, digest))
    return [{"name": n, "path": p, "digest": d}
            for n, p, d in sorted(found, key=lambda t: (t[0], t[1] or ""))]


def build_row(item: Any, reports: Iterable[Any], environment: str,
              points: set[str] | None, points_digest: str | None,
              digests: Digests) -> dict:
    """Intent:
        The row for one finished test. `class` is left None here and
        filled in once the session knows every distribution it loaded.
    """
    callspec = getattr(item, "callspec", None)
    params = dict(getattr(callspec, "params", {}) or {})
    function = getattr(item, "function", None)
    test_digest = source_digest(function) if function is not None else None
    fixtures = _fixtures(item, params, digests)
    test_path = relative(getattr(item, "path", None), digests.root)
    paths = {f["path"] for f in fixtures if f["path"] is not None}
    if test_path is not None:
        paths.add(test_path)
    identity = json_digest({
        "test": test_digest,
        "fixtures": [[f["name"], f["path"], f["digest"]] for f in fixtures],
        "params": {name: encode(value) for name, value in params.items()},
    })
    return {
        "framework": FRAMEWORK,
        "nodeid": item.nodeid,
        "identity": identity,
        "class": None,
        "environment": environment,
        "outcome": outcome(reports),
        "n": None if points is None else len(points),
        "points": points_digest,
        "fixtures": fixtures,
        "files": [{"path": p, "digest": digests.file(p)}
                  for p in sorted(paths)],
    }


def render(rows: Iterable[dict], env_class: str,
           class_excludes: Iterable[str] = ()) -> str:
    """Intent:
        The ledger file's text: schema 1, the sorted names of the
        distributions left out of the environment class, then the rows
        sorted by nodeid with `class` set, one row per line so a diff
        shows one line per test.
    """
    ordered = sorted(({**row, "class": env_class} for row in rows),
                     key=lambda row: row["nodeid"])
    lines = [json.dumps(row, sort_keys=True) for row in ordered]
    body = ",\n".join(lines)
    excludes = json.dumps(sorted(class_excludes))
    return ('{"schema": %d, "class_excludes": %s, "rows": [\n'
            % (SCHEMA, excludes)
            + (body + "\n" if body else "") + "]}\n")


def write(path: Path, text: str) -> None:
    """Intent:
        Write `text` to `path` through a temporary file in the same
        directory, so a reader never sees a half-written ledger.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

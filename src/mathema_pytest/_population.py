# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Observing calls into the project's population by rebinding.

The population is the set of functions listed in the project's
`.mathema/index.yaml` (`index.modules[].functions[].key`, each key the
module name followed by the function's qualified name). After
collection, each listed function whose module is already imported is
replaced by a thin wrapper, and every reference to the original found in
a loaded module's namespace (a test module's `from m import f`
included) is pointed at the wrapper. No trace function is installed:
coverage owns `sys.settrace`.

The wrapper records a point when a test is in its call phase and the
immediate caller's code lives in a collected test file (a direct call).
Calls from inside the project, or from fixtures during setup, are not
points. Each test keeps at most `POINT_CAP` distinct points; past the
cap the wrapper only forwards the call.
"""
from __future__ import annotations

import functools
import os
import sys
import types
from collections.abc import Iterable
from typing import Any, Callable

from ._digest import json_digest, point

POINT_CAP = 1024
WRAPPED_FLAG = "__mathema_test_ledger__"


def read_population(index_path: str) -> list[tuple[str, str]] | None:
    """Intent:
        The `(module, qualname)` pairs listed in the index at
        `index_path`, or None when there is no index (the run then
        observes no points). A key that does not start with its
        module's name is skipped.

    Raises:
        yaml.YAMLError: the index exists and is not valid YAML.
    """
    if not os.path.isfile(index_path):
        return None
    import yaml

    with open(index_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    pairs: list[tuple[str, str]] = []
    modules = ((data.get("index") or {}).get("modules") or []
               if isinstance(data, dict) else [])
    for module in modules:
        name = (module or {}).get("name")
        if not isinstance(name, str) or not name:
            continue
        for fn in module.get("functions") or []:
            key = (fn or {}).get("key")
            if isinstance(key, str) and key.startswith(name + "."):
                pairs.append((name, key[len(name) + 1:]))
    return pairs


def points_digest(points: Iterable[str]) -> str:
    """Intent:
        The digest of a set of points: sha256 over their sorted list.
    """
    return json_digest(sorted(points))


class Observer:
    """Intent:
        Holds the wrappers installed for one session and the points of
        the test currently in its call phase.

    Notes:
        `points` is None outside a call phase, so a call then costs one
        attribute read. `record` is the one place a call is observed;
        further per-call facts (argument and return classes) attach
        there.
    """

    def __init__(self) -> None:
        self.points: set[str] | None = None
        self.test_files: frozenset[str] = frozenset()
        self._rebound: list[tuple[Any, str, Callable]] = []

    def record(self, key: str, args: tuple, kwargs: dict) -> None:
        points = self.points
        if points is None or len(points) >= POINT_CAP:
            return
        caller = sys._getframe(2).f_code.co_filename
        if caller in self.test_files:
            points.add(key + "(" + point(args, kwargs) + ")")

    def _wrap(self, key: str, original: Callable) -> Callable:
        observer = self

        def observed(*args, **kwargs):
            observer.record(key, args, kwargs)
            return original(*args, **kwargs)

        functools.update_wrapper(observed, original)
        setattr(observed, WRAPPED_FLAG, True)
        return observed

    def install(self, population: list[tuple[str, str]],
                test_files: Iterable[str]) -> int:
        """Intent:
            Wrap every listed function that is a plain function of an
            imported module or class, and repoint every loaded module's
            references to it. Returns how many functions were wrapped.
        """
        files = set()
        for path in test_files:
            files.add(path)
            files.add(os.path.realpath(path))
        self.test_files = frozenset(files)
        wrappers: dict[int, tuple[Any, Callable]] = {}
        for module_name, qualname in population:
            owner: Any = sys.modules.get(module_name)
            parts = qualname.split(".")
            for part in parts[:-1]:
                owner = getattr(owner, part, None)
            if owner is None:
                continue
            original = vars(owner).get(parts[-1])
            if (not isinstance(original, types.FunctionType)
                    or getattr(original, WRAPPED_FLAG, False)
                    or id(original) in wrappers):
                continue
            wrapper = self._wrap(module_name + "." + qualname, original)
            wrappers[id(original)] = (original, wrapper)
            if not isinstance(owner, types.ModuleType):
                self._rebind(owner, parts[-1], original, wrapper)
        if wrappers:
            self._sweep(wrappers)
        return len(wrappers)

    def _rebind(self, target: Any, name: str, original: Callable,
                wrapper: Callable) -> None:
        """Intent:
            Point `name` in `target` (a module namespace dict, or a
            class) at `wrapper`, remembering the original for
            `uninstall`.
        """
        if isinstance(target, dict):
            target[name] = wrapper
        else:
            setattr(target, name, wrapper)
        self._rebound.append((target, name, original))

    def _sweep(self, wrappers: dict[int, tuple[Any, Callable]]) -> None:
        for module in list(sys.modules.values()):
            namespace = getattr(module, "__dict__", None)
            if not isinstance(namespace, dict):
                continue
            for name, value in list(namespace.items()):
                hit = wrappers.get(id(value))
                if hit is not None and hit[0] is value:
                    self._rebind(namespace, name, value, hit[1])

    def uninstall(self) -> None:
        """Intent:
            Put every original back where a wrapper replaced it.
        """
        for where, name, original in reversed(self._rebound):
            if isinstance(where, dict):
                where[name] = original
            else:
                setattr(where, name, original)
        self._rebound.clear()
        self.points = None

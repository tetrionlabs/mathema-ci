# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The environment a test ledger row was written in.

Two things, each with one name. The **environment name** is a label a
person gives the run through `MATHEMA_ENV` (`local` when unset; the CI
templates set `ci`). The **environment class** is computed, never
named: sha256 over the platform (`sys.platform`, `platform.machine()`),
the interpreter's major.minor, and the sorted names and versions of the
distributions the session imported (`sys.modules` mapped through
`importlib.metadata.packages_distributions`), leaving out the
distributions that run the tests rather than the code under test. A
dependency bump makes a new class; a lockfile keeps it stable; a serial
and a parallel run of the same code share one.
"""
from __future__ import annotations

import inspect
import os
import platform
import re
import sys
from collections.abc import Iterable, Mapping
from importlib import metadata

from ._digest import json_digest

ENV_VARIABLE = "MATHEMA_ENV"
DEFAULT_ENVIRONMENT = "local"


def environment_name(environ: dict[str, str] | None = None) -> str:
    """Intent:
        This run's environment name: `MATHEMA_ENV` stripped, or `local`
        when it is unset or empty. Checking the name against the
        project's ranked list is the reader's job, not the writer's.
    """
    env = os.environ if environ is None else environ
    return env.get(ENV_VARIABLE, "").strip() or DEFAULT_ENVIRONMENT


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _top_level_names(dist: metadata.Distribution) -> set[str]:
    """Intent:
        The top-level importable names a distribution provides: those its
        `top_level.txt` lists, else those its installed files show (the
        first directory of a package, or a module file's own name).
    """
    listed = (dist.read_text("top_level.txt") or "").split()
    if listed:
        return set(listed)
    names = set()
    for file in dist.files or ():
        first = file.parts[0]
        if len(file.parts) > 1:
            name = first
        else:
            name = inspect.getmodulename(first) or ""
        if name and "." not in name and name.isidentifier():
            names.add(name)
    return names


def package_providers() -> dict[str, list[str]]:
    """The distributions that provide each top-level importable name, as
    `importlib.metadata.packages_distributions` gives them on Python 3.11
    and later. Python 3.10's own reads `top_level.txt` alone, which
    distributions built without setuptools do not ship, so those would be
    missing from every environment class computed on 3.10."""
    providers: dict[str, list[str]] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        for top in _top_level_names(dist):
            if name not in providers.setdefault(top, []):
                providers[top].append(name)
    return providers


def loaded_distributions(module_names: Iterable[str],
                         providers: Mapping[str, list[str]] | None = None
                         ) -> dict[str, str]:
    """Intent:
        The distributions providing the top-level packages of
        `module_names`, as normalised name to version. Modules no
        installed distribution provides (the standard library, the
        project's own uninstalled code) contribute nothing. `providers`
        is `package_providers()` when the caller has it.
    """
    if providers is None:
        providers = package_providers()
    found: dict[str, str] = {}
    for top in {name.partition(".")[0] for name in module_names}:
        for dist in providers.get(top, ()):
            key = _normalise(dist)
            if key in found:
                continue
            try:
                found[key] = metadata.version(dist)
            except metadata.PackageNotFoundError:
                continue
    return found


# Distributions whose purpose is to run, schedule, observe or measure a
# test session: pytest's own dependencies pluggy and iniconfig, xdist's
# transport execnet, coverage, this ledger writer, and the pytest plugins
# known to do only that. Everything else stays in the class: pytest
# itself, whose `approx`, `raises` and `tmp_path` run inside tests, and
# any other `pytest-*` plugin, so a plugin nobody has listed costs a spare
# class and never a false match.
TEST_RUNNER_DISTRIBUTIONS = frozenset({
    "pluggy", "iniconfig", "execnet", "coverage", "mathema-ci",
    "pytest-xdist", "pytest-cov", "pytest-sugar",
    "pytest-html", "pytest-metadata", "pytest-instafail",
    "pytest-json-report", "pytest-pretty", "pytest-clarity",
    "pytest-github-actions-annotate-failures"})


def is_test_runner(name: str) -> bool:
    """Intent:
        Whether the distribution `name` is listed as running the tests
        rather than being part of what they run on.
    """
    return _normalise(name) in TEST_RUNNER_DISTRIBUTIONS


def class_distributions(
        distributions: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Intent:
        Split the session's `distributions` into those the environment
        class is computed over and the sorted names of the test-runner
        distributions left out of it.
    """
    kept = {name: version for name, version in distributions.items()
            if not is_test_runner(name)}
    excluded = sorted(name for name in distributions if is_test_runner(name))
    return kept, excluded


def environment_class(distributions: dict[str, str]) -> str:
    """Intent:
        The environment class digest for this interpreter and platform
        with `distributions` loaded.
    """
    return json_digest({
        "platform": sys.platform,
        "machine": platform.machine(),
        "python": f"{sys.version_info[0]}.{sys.version_info[1]}",
        "distributions": sorted(distributions.items()),
    })

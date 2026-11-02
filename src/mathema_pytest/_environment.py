# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The environment a test ledger row was written in.

Two things, each with one name. The **environment name** is a label a
person gives the run through `MATHEMA_ENV` (`local` when unset; the CI
templates set `ci`). The **environment class** is computed, never
named: sha256 over the platform (`sys.platform`, `platform.machine()`),
the interpreter's major.minor, and the sorted names and versions of the
distributions the session imported (`sys.modules` mapped through
`importlib.metadata.packages_distributions`). A dependency bump makes a
new class; a lockfile keeps it stable.
"""
from __future__ import annotations

import os
import platform
import re
import sys
from collections.abc import Iterable
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


def loaded_distributions(module_names: Iterable[str]) -> dict[str, str]:
    """Intent:
        The distributions providing the top-level packages of
        `module_names`, as normalised name to version. Modules no
        installed distribution provides (the standard library, the
        project's own uninstalled code) contribute nothing.
    """
    providers = metadata.packages_distributions()
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

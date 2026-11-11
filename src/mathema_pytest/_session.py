# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""What `measure` needs to know about the pytest session it started.

`measure` loads this module with `-p` and names a file in
`MATHEMA_CI_SESSION`. The module then does three things in the session's
controlling process, and nothing at all otherwise:

- it takes the current directory off the front of the import path, where
  `coverage run -m` put it, so tests import what they import under the
  `pytest` command, and removes the variable from the environment the tests
  see;
- it holds pytest's junit report in a temporary file and moves it into place
  only when tests ran and the run completed, so an incomplete run leaves the
  last report as it was;
- it writes one JSON file when pytest finishes: how many tests reported,
  whether the run completed, what became of the test ledger, and the file
  each of the project's packages (named in `MATHEMA_CI_PACKAGES`) was
  imported from.

A process with no such file named (an xdist worker, whose environment comes
after the variable is removed) has no state and every hook returns at once.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from typing import Any

import pytest

from ._atomic import atomic_write

PATH_VARIABLE = "MATHEMA_CI_SESSION"
PACKAGES_VARIABLE = "MATHEMA_CI_PACKAGES"
LEDGER_OPTION = "--mathema-test-ledger"
LEDGER_PLUGIN = "mathema"
LEDGER_WRITER = "mathema-test-ledger"
COV_PLUGIN = "_cov"

# pytest's exit statuses for a run in which every collected test had its turn.
_COMPLETE = (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED)

# The module an import error names.
_MISSING = re.compile(r"No module named '([\w.]+)'")


class _Session:
    """Intent:
        What this session has shown so far, written out at its end.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.nodeids: set[str] = set()
        self.started = False
        self.stopped = False
        self.finished_as: int | None = None
        self.junit: str | None = None
        self.junit_held: str | None = None
        self.no_test_runs = False
        self.missing: list[str] = []
        self.packages: list[str] = []

    def complete(self) -> bool:
        return (not self.stopped and bool(self.nodeids) and not self.no_test_runs
                and self.finished_as in _COMPLETE)


_state: _Session | None = None


def _begin() -> None:
    """Intent:
        Read and remove the variable; when it names a file, start recording
        and take the current directory off the front of the import path.
    """
    global _state
    path = os.environ.pop(PATH_VARIABLE, None)
    packages = os.environ.pop(PACKAGES_VARIABLE, "")
    if not path:
        return
    _state = _Session(path)
    _state.packages = [name for name in packages.split(",") if name]
    if sys.path and os.path.abspath(sys.path[0] or ".") == os.getcwd():
        del sys.path[0]


_begin()


@pytest.hookimpl(hookwrapper=True)
def pytest_load_initial_conftests(early_config, parser, args):
    """Intent:
        Once the plugins and initial conftests have declared their options,
        accept the ledger option if none of them did, as when its plugin is
        turned off, so that the run goes on and simply writes no ledger.
    """
    yield
    if _state is None:
        return
    try:
        parser.addoption(LEDGER_OPTION, action="store", default=None,
                         help="the test ledger's path; its plugin is off in this run")
    except ValueError:
        pass


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config) -> None:
    if _state is None or hasattr(config, "workerinput"):
        return
    _state.no_test_runs = bool(getattr(config.option, "setuponly", False)
                               or getattr(config.option, "setupplan", False))
    xml = getattr(config.option, "xmlpath", None)
    if xml:
        _state.junit = os.path.normpath(os.path.abspath(
            os.path.expanduser(os.path.expandvars(xml))))
        _state.junit_held = _state.path + ".junit.xml"
        config.option.xmlpath = _state.junit_held


def pytest_sessionstart(session) -> None:
    if _state is not None:
        _state.started = True


def pytest_runtest_logreport(report) -> None:
    if _state is not None:
        _state.nodeids.add(report.nodeid)


def pytest_collectreport(report) -> None:
    """Intent:
        Keep the name of each module a collection error could not import,
        so measure can say when the project's own layout is the cause.
    """
    if _state is None or not report.failed:
        return
    for name in _MISSING.findall(str(report.longrepr)):
        if name not in _state.missing:
            _state.missing.append(name)


def pytest_keyboard_interrupt(excinfo) -> None:
    if _state is not None:
        _state.stopped = True


def pytest_internalerror(excrepr, excinfo) -> None:
    if _state is not None:
        _state.stopped = True


def _settle_junit(config) -> None:
    """Intent:
        Move the held junit report into place when the run completed, or
        drop it, and show pytest's own report line the real path.
    """
    assert _state is not None
    if _state.junit is None or _state.junit_held is None:
        return
    try:
        from _pytest.junitxml import xml_key

        config.stash[xml_key].logfile = _state.junit
    except (ImportError, KeyError, AttributeError):
        pass
    if not os.path.exists(_state.junit_held):
        return
    if _state.complete():
        os.makedirs(os.path.dirname(_state.junit), exist_ok=True)
        shutil.move(_state.junit_held, _state.junit)
    else:
        os.remove(_state.junit_held)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
    if _state is None:
        return
    _state.finished_as = int(exitstatus)
    try:
        _settle_junit(session.config)
    except OSError as exc:
        print(f"mathema: the junit report could not be kept ({exc})", file=sys.stderr)


def _ledger_state(config) -> dict[str, Any]:
    """Intent:
        What became of the test ledger: `off` when its plugin is not loaded,
        or the writer's own account of itself.
    """
    if not config.pluginmanager.hasplugin(LEDGER_PLUGIN):
        return {"state": "off"}
    writer = config.pluginmanager.get_plugin(LEDGER_WRITER)
    if writer is None:
        return {"state": "off"}
    return {"state": "failed" if writer.write_problem else "written",
            "problem": writer.write_problem}


def _copy_of(name: str) -> str | None:
    """Intent:
        The file the module `name` was imported from in this process, or,
        when it was not imported here (under xdist the workers import the
        project), the file importing it here would load; None for neither.
    """
    import importlib.util

    module = sys.modules.get(name)
    if module is not None:
        return getattr(module, "__file__", None)
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    return spec.origin if spec is not None and spec.has_location else None


def pytest_unconfigure(config) -> None:
    if _state is None or hasattr(config, "workerinput"):
        return
    record = {"started": _state.started, "complete": _state.complete(),
              "tests": 0 if _state.no_test_runs else len(_state.nodeids), "ledger": _ledger_state(config),
              "missing": _state.missing,
              "coverage_taken": (config.pluginmanager.hasplugin(COV_PLUGIN)
                                 and not getattr(config.option, "no_cov", False)),
              "imported": {name: _copy_of(name) for name in _state.packages}}
    try:
        atomic_write(_state.path, json.dumps(record))
    except OSError as exc:
        print(f"mathema: the session record could not be written ({exc})", file=sys.stderr)

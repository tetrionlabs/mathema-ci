# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""pytest hooks for the test ledger.

The test ledger is one JSON file, schema 1, with one row per test: the
test's nodeid, its outcome, the environment it ran in, a digest of what
the test is made of (its source, its fixtures transitively, its
parametrize values) with the path and digest of each part, and, when
the project has a population in `.mathema/index.yaml`, how many distinct
points the test called those functions at directly and a digest of
them. `mathema` reads it to decide claims that depend on a test. The
schema is documented in `docs/test-ledger.md`.

The plugin is active only when the run passes `--mathema-test-ledger
PATH` or sets `MATHEMA_TEST_LEDGER` (`1` for the default path
`.mathema/tests/ledger.json` under the rootdir, any other value except
`0` as the path). Otherwise no hook does anything.

Under pytest-xdist each worker builds the rows of the tests it ran and
hands them to the controller, which merges them and writes the file.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from . import _environment, _ledger, _population

OPTION = "--mathema-test-ledger"
ENV = "MATHEMA_TEST_LEDGER"
DEFAULT_PATH = os.path.join(".mathema", "tests", "ledger.json")
INDEX_PATH = os.path.join(".mathema", "index.yaml")
PLUGIN_NAME = "mathema-test-ledger"
WORKER_KEY = "mathema_test_ledger"


def pytest_addoption(parser) -> None:
    group = parser.getgroup("mathema")
    group.addoption(
        OPTION, action="store", default=None, metavar="PATH",
        help="write mathema's test ledger to PATH (also enabled by "
             "MATHEMA_TEST_LEDGER: 1 for .mathema/tests/ledger.json, or "
             "a path)")


def ledger_path(config) -> Path | None:
    """Intent:
        Where this run writes the ledger, or None when it writes none.
        The option wins over the environment variable; a relative path
        is taken from the directory pytest was invoked in, and
        `MATHEMA_TEST_LEDGER=1` means the default path under the rootdir.
    """
    option = config.getoption(OPTION, default=None)
    if option:
        return Path(config.invocation_params.dir) / option
    value = os.environ.get(ENV, "").strip()
    if value in ("", "0"):
        return None
    if value == "1":
        return Path(config.rootpath) / DEFAULT_PATH
    return Path(config.invocation_params.dir) / value


def enabled(config) -> bool:
    """Intent:
        Whether this run writes the test ledger.
    """
    return ledger_path(config) is not None


def pytest_configure(config) -> None:
    path = ledger_path(config)
    if path is None:
        return
    config.addinivalue_line(
        "markers",
        "mathema_test_ledger: internal, set when the test ledger is on")
    config.pluginmanager.register(TestLedger(config, path), PLUGIN_NAME)


class TestLedger:
    """Intent:
        The session's ledger writer, registered only when the ledger is
        on. In a single process it observes, builds and writes; in an
        xdist worker it observes and builds; in the xdist controller it
        merges and writes.
    """

    __test__ = False

    def __init__(self, config, path: Path) -> None:
        self.config = config
        self.path = path
        self.root = Path(config.rootpath)
        self.is_worker = hasattr(config, "workerinput")
        self.environment = _environment.environment_name()
        self.digests = _ledger.Digests(self.root)
        self.observer = _population.Observer()
        self.population = _population.read_population(
            str(self.root / INDEX_PATH))
        self.rows: list[dict] = []
        self.distributions: dict[str, str] = {}
        self._reports: dict[str, list[Any]] = {}
        self._points: dict[str, set[str]] = {}

    def _controller(self) -> bool:
        """Intent:
            Whether this process is an xdist controller, which runs no
            tests itself and receives its rows from the workers.
        """
        return (not self.is_worker
                and self.config.pluginmanager.hasplugin("dsession"))

    def pytest_collection_finish(self, session) -> None:
        if self.population is None:
            return
        files = {str(item.path) for item in session.items
                 if getattr(item, "path", None) is not None}
        self.observer.install(self.population, files)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item: Any) -> Iterator[None]:
        points: set[str] | None = (
            set() if self.population is not None else None)
        self.observer.points = points
        try:
            yield
        finally:
            self.observer.points = None
            if points is not None:
                self._points[item.nodeid] = points

    def pytest_runtest_logreport(self, report) -> None:
        if self._controller():
            return
        self._reports.setdefault(report.nodeid, []).append(report)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        yield
        reports = self._reports.pop(item.nodeid, [])
        if self.population is None:
            points, digest = None, None
        else:
            points = self._points.pop(item.nodeid, set())
            digest = _population.points_digest(points)
        self.rows.append(_ledger.build_row(
            item, reports, self.environment, points, digest, self.digests))

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error) -> None:
        output = getattr(node, "workeroutput", None) or {}
        payload = output.get(WORKER_KEY)
        if not payload:
            return
        part = json.loads(payload)
        self.rows.extend(part["rows"])
        self.distributions.update(part["distributions"])

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus) -> None:
        self.distributions.update(
            _environment.loaded_distributions(list(sys.modules)))
        if self.is_worker:
            self.config.workeroutput[WORKER_KEY] = json.dumps(
                {"rows": self.rows, "distributions": self.distributions})
            return
        kept, excluded = _environment.class_distributions(self.distributions)
        env_class = _environment.environment_class(kept)
        _ledger.write(self.path,
                      _ledger.render(self.rows, env_class, excluded))

    def pytest_unconfigure(self, config) -> None:
        self.observer.uninstall()

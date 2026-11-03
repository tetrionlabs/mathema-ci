# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""pytest hooks for the test ledger.

The test ledger is one JSON file, schema 1, with one row per test: the
test's nodeid, its outcome, the environment it ran in, a digest of what
the test is made of (its source, its fixtures transitively, its
parametrize values) with the path and digest of each part. `mathema`
reads it to decide claims that depend on a test. The schema is
documented in `docs/test-ledger.md`.

The plugin only records. It never replaces a function, so a test sees
the same objects and reaches the same outcome as on a run without it.

The plugin is active only when the run passes `--mathema-test-ledger
PATH` or sets `MATHEMA_TEST_LEDGER` (`1` for the default path
`.mathema/tests/ledger.json` under the rootdir, any other value except
`0` as the path). Otherwise no hook does anything.

Under pytest-xdist each worker builds a test's row as the test ends and
hands it to the controller on the test's last report, so the rows of a worker
that later crashes are kept; the controller merges them and writes the file.

The file is written only for a run that completed with at least one test, and
a run that did not leaves the last file as it was. A file that cannot be
written, or a row that cannot be built, is said on stderr and never changes
the run's exit status.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from . import _environment, _ledger

OPTION = "--mathema-test-ledger"
ENV = "MATHEMA_TEST_LEDGER"
DEFAULT_PATH = os.path.join(".mathema", "tests", "ledger.json")
PLUGIN_NAME = "mathema-test-ledger"
REPORT_KEY = "mathema_test_ledger"
# The exit statuses of a run in which every test collected had its turn.
_COMPLETE = (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED)


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
        on. In a single process it builds and writes; in an xdist worker
        it builds; in the xdist controller it merges and writes.
    """

    __test__ = False

    def __init__(self, config, path: Path) -> None:
        self.config = config
        self.path = path
        self.root = Path(config.rootpath)
        self.is_worker = hasattr(config, "workerinput")
        self.environment = _environment.environment_name()
        self.digests = _ledger.Digests(self.root)
        self.rows: dict[tuple[str | None, str], dict] = {}
        self.distributions: dict[str, str] = {}
        self.write_problem: str | None = None
        self._reports: dict[str, list[Any]] = {}
        self._item: Any = None
        self._stopped = False
        self._tops_seen: set[str] = set()
        self._providers: Any = None

    def _controller(self) -> bool:
        """Intent:
            Whether this process is an xdist controller, which runs no
            tests itself and receives its rows from the workers.
        """
        return (not self.is_worker
                and self.config.pluginmanager.hasplugin("dsession"))

    def _new_distributions(self) -> dict[str, str]:
        """Intent:
            The distributions of the top-level modules this process loaded
            since it last looked.
        """
        tops = {name.partition(".")[0] for name in list(sys.modules)} - self._tops_seen
        if not tops:
            return {}
        self._tops_seen |= tops
        if self._providers is None:
            self._providers = _environment.metadata.packages_distributions()
        return _environment.loaded_distributions(tops, self._providers)

    def _receive(self, report) -> None:
        """Intent:
            In the controller: take the row a worker put on a test's last
            report, or write one for a test whose worker crashed, which
            pytest-xdist reports as failed with no phase of its own.
        """
        part = getattr(report, REPORT_KEY, None)
        worker = getattr(report, "worker_id", None)
        if part is not None:
            self.rows[(worker, report.nodeid)] = part["row"]
            self.distributions.update(part["distributions"])
        elif report.failed and report.when not in ("setup", "call", "teardown"):
            self.rows[(worker, report.nodeid)] = _ledger.unread_row(
                report.nodeid, "failed", self.environment)

    def _finish_test(self, report) -> None:
        """Intent:
            On a test's teardown report: build its row, and in a worker put
            the row on the report, which pytest-xdist carries to the
            controller as soon as this hook returns.
        """
        item = self._item
        if item is None or item.nodeid != report.nodeid:
            return
        reports = self._reports.pop(item.nodeid, [])
        row = _ledger.build_row(item, reports, self.environment, self.digests)
        if self.is_worker:
            setattr(report, REPORT_KEY,
                    {"row": row, "distributions": self._new_distributions()})
        else:
            self.rows[(None, report.nodeid)] = row

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(self, report) -> None:
        if self._controller():
            self._receive(report)
            return
        self._reports.setdefault(report.nodeid, []).append(report)
        if report.when == "teardown":
            self._finish_test(report)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        self._item = item
        yield
        self._item = None

    def pytest_keyboard_interrupt(self, excinfo) -> None:
        self._stopped = True

    def pytest_internalerror(self, excrepr, excinfo) -> None:
        self._stopped = True

    def _completed(self, exitstatus) -> bool:
        """Intent:
            Whether this run may replace the last ledger: it ended by itself
            as a complete run, some test ran, and every row reached an
            outcome.
        """
        option = self.config.option
        return (not self._stopped and exitstatus in _COMPLETE and bool(self.rows)
                and not getattr(option, "collectonly", False)
                and not getattr(option, "setuponly", False)
                and not getattr(option, "setupplan", False)
                and all(row["outcome"] != _ledger.INCOMPLETE
                        for row in self.rows.values()))

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if self.is_worker or not self._completed(exitstatus):
            return
        try:
            self.distributions.update(self._new_distributions())
            kept, excluded = _environment.class_distributions(self.distributions)
            env_class = _environment.environment_class(kept)
        except Exception as exc:
            self.write_problem = f"{type(exc).__name__}: {exc}"
            sys.stderr.write(f"mathema: the test ledger could not be written ({exc})\n")
            return
        try:
            _ledger.write(self.path,
                          _ledger.render(self.rows.values(), env_class, excluded))
        except (OSError, ValueError) as exc:
            self.write_problem = f"{type(exc).__name__}: {exc}"
            sys.stderr.write(f"mathema: the test ledger could not be written to "
                             f"{self.path} ({self.write_problem}); the last one stays\n")
